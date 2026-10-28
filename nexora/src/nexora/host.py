"""The host of a program that runs on the machine of whoever started it.

This is the only module of the language that touches the file system: the interpreter asks
the host, and the host decides with the three rules of decision 0015 — what the program
declared, what the user allowed, and what the environment permits. The interpreter never
imports this module, so the stages of the language stay away from the operating system
(tests/test_security.py).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .capabilities import NETWORK, READ, WRITE, Capabilities, Grants, NotAllowed, is_inside

_NETWORK_TIMEOUT_SECONDS = 5
_NETWORK_MAX_BYTES = 1_048_576
_PROCESS_TIMEOUT_SECONDS = 5
_PROCESS_MAX_BYTES = 1_048_576


def read_standard_input() -> str:
    """One line of the standard input, without its terminator.

    Raises EOFError when the input has ended: the program has to know that there is
    nothing more to read (decision 0015, 7).
    """
    line = sys.stdin.readline()
    if line == "":
        raise EOFError("the standard input ended")
    return line.removesuffix("\n").removesuffix("\r")


# The defaults of the host: nothing allowed, nothing declared.
NO_GRANTS = Grants()
NO_CAPABILITIES = Capabilities()


class LocalHost:
    """What a program may do besides computing: its arguments, its input and its files.

    `arguments` are the ones the program was run with. `read_line` reads the standard
    input. `grants` are the capabilities the user allowed, `declarations` the ones the
    program declared, and the `*_allowed` switches whether this environment admits them.
    """

    def __init__(self, *, arguments: tuple[str, ...] = (),
                 read_line: Callable[[], str] | None = None,
                 grants: Grants = NO_GRANTS, declarations: Capabilities = NO_CAPABILITIES,
                 files_allowed: bool = True, network_allowed: bool = False,
                 processes_allowed: bool = False) -> None:
        self._arguments = arguments
        self._read_line = read_line if read_line is not None else read_standard_input
        self._grants = grants
        self._declarations = declarations
        self._files_allowed = files_allowed
        self._network_allowed = network_allowed
        self._processes_allowed = processes_allowed

    def arguments(self) -> tuple[str, ...]:
        """The arguments the program was run with."""
        return self._arguments

    def read_line(self) -> str:
        """One line of the standard input, without its terminator."""
        return self._read_line()

    def read_file(self, path: str) -> str:
        """The contents of a file the program is allowed to read."""
        return Path(self._allowed(path, READ)).read_text(encoding="utf-8")

    def write_file(self, path: str, text: str) -> None:
        """Writes a file the program is allowed to write."""
        Path(self._allowed(path, WRITE)).write_text(text, encoding="utf-8")

    def get_url(self, url: str) -> str:
        """Fetches at most one MiB of UTF-8 text from an explicitly allowed HTTPS origin."""
        origin = _https_origin(url)
        if origin is None:
            raise OSError("only HTTPS URLs without credentials and on port 443 are allowed")
        if not self._network_allowed:
            raise NotAllowed("this environment does not allow network access")
        if not self._declarations.covers(NETWORK, origin):
            raise NotAllowed(f"this program does not declare network access to '{origin}'")
        if not Capabilities(network=self._grants.network).covers(NETWORK, origin):
            raise NotAllowed(f"'{origin}' is not among the network origins the user allowed")

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = build_opener(ProxyHandler({}), NoRedirect())
        request = Request(url, headers={"Accept": "text/plain, */*", "Accept-Encoding": "identity"})
        try:
            with opener.open(request, timeout=_NETWORK_TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise OSError(f"HTTPS request returned status {response.status}")
                data = response.read(_NETWORK_MAX_BYTES + 1)
                if len(data) > _NETWORK_MAX_BYTES:
                    raise OSError(f"HTTPS response exceeds {_NETWORK_MAX_BYTES} bytes")
            return data.decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as error:
            raise OSError(f"HTTPS request failed: {error}") from None

    def run_process(self, command: str, arguments: tuple[str, ...]) -> str:
        """Runs an explicitly allowed command, without a shell or inherited standard input."""
        if not self._processes_allowed:
            raise NotAllowed("this environment does not allow external processes")
        if command not in self._declarations.process:
            raise NotAllowed(f"this program does not declare permission to run '{command}'")
        if command not in self._grants.process:
            raise NotAllowed(f"'{command}' is not among the commands the user allowed")
        try:
            executable = shutil.which(command)
            if executable is None:
                raise OSError(f"process '{command}' is not available on PATH")
            child_env = {"PATH": os.defpath}
            if os.name == "nt":
                for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
                    if name in os.environ:
                        child_env[name] = os.environ[name]
            process = subprocess.Popen(
                [executable, *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, shell=False, text=False,
                env=child_env,
                start_new_session=(os.name == "posix"),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        except OSError as error:
            raise OSError(f"process '{command}' could not start: {error}") from None

        output = {"stdout": bytearray(), "stderr": bytearray()}
        too_large = threading.Event()

        def drain(stream, name: str) -> None:
            try:
                while chunk := stream.read(8192):
                    if len(output[name]) + len(chunk) > _PROCESS_MAX_BYTES:
                        too_large.set()
                        _kill_process_tree(process)
                    elif not too_large.is_set():
                        output[name].extend(chunk)
            except OSError:
                pass

        readers = [
            threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            try:
                process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_tree(process)
                process.wait()
        finally:
            # A CLI deadline or Ctrl+C can interrupt wait() before its own timeout fires.
            # Do not leave the capability's child running after its parent execution stops.
            if process.poll() is None:
                _kill_process_tree(process)
                process.wait()
            for reader in readers:
                reader.join(timeout=1)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if timed_out:
            raise OSError(f"process '{command}' exceeded {_PROCESS_TIMEOUT_SECONDS} seconds")
        if too_large.is_set():
            raise OSError(f"process output exceeds {_PROCESS_MAX_BYTES} bytes")
        if process.returncode != 0:
            detail = bytes(output["stderr"]).decode("utf-8", "replace").strip()
            suffix = f": {detail}" if detail else ""
            raise OSError(f"process '{command}' exited with status {process.returncode}{suffix}")
        try:
            return bytes(output["stdout"]).decode("utf-8")
        except UnicodeDecodeError:
            raise OSError(f"process '{command}' wrote output that is not UTF-8") from None

    def _allowed(self, path: str, capability: str) -> str:
        """The path the program may use, after checking the three rules.

        The paths are compared once resolved, so that a `..` that leaves the scope and a
        symbolic link that points outside it do not slip through (decision 0015, 4).
        """
        if not self._files_allowed:
            raise NotAllowed(f"this environment does not allow files, so '{path}' cannot be used")
        target = _resolve(path)
        if not any(is_inside(_resolve(scope), target) for scope in self._declarations.of(capability)):
            raise NotAllowed(f"this program does not declare that it needs to {capability} '{path}'")
        if not any(is_inside(_resolve(grant), target) for grant in self._grants.of(capability)):
            raise NotAllowed(f"'{path}' is not among the paths the user allowed to {capability}")
        return target


def _https_origin(value: str) -> str | None:
    """Canonical origin for the deliberately narrow HTTPS capability."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.port not in (None, 443):
            return None
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        return f"https://{host}"
    except (UnicodeError, ValueError):
        return None


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Stops the allowed command, and its group on POSIX, after a resource limit trips."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def _resolve(path: str) -> str:
    """The path as the file system sees it: absolute, with the symbolic links followed.

    A path that does not exist yet is resolved over the part that does, so that a file
    that is going to be created is checked in the place it will live.
    """
    return os.path.realpath(path)

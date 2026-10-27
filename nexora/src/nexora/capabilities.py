"""What a program declares it needs, and how two paths are compared.

The permission model of decision 0015: the effective capability is the intersection of what
the program declares, what the user grants and what the environment allows. This module
holds the parts that need no operating system: the data model and the comparison of two
paths. The file system is only touched by `host.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# The capabilities a program can declare with `uses`.
READ = "read"
WRITE = "write"
NETWORK = "network"
PROCESS = "process"
CAPABILITIES = (READ, WRITE, NETWORK, PROCESS)


@dataclass(frozen=True)
class Capabilities:
    """The scopes a program declared, by capability.

    File paths and process names are kept as written; network scopes are HTTPS origins.
    File paths are resolved when used, not here. A program that declares nothing has no
    capability at all.
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    network: tuple[str, ...] = ()
    process: tuple[str, ...] = ()

    def of(self, capability: str) -> tuple[str, ...]:
        """The paths declared for a capability."""
        return {
            READ: self.read,
            WRITE: self.write,
            NETWORK: self.network,
            PROCESS: self.process,
        }.get(capability, ())

    def covers(self, capability: str, path: str) -> bool:
        """Whether a declaration covers a file path, HTTPS origin or executable.

        The paths are compared as they were written: a path that is not a literal cannot
        be checked here, and the interpreter decides at run time.
        """
        if capability == NETWORK:
            from urllib.parse import urlsplit

            def origin(value: str) -> tuple[str, str, int] | None:
                try:
                    parsed = urlsplit(value)
                    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                        return None
                    return parsed.scheme, parsed.hostname.encode("idna").decode("ascii").lower(), parsed.port or 443
                except (UnicodeError, ValueError):
                    return None

            target = origin(path)
            return target is not None and any(origin(scope) == target for scope in self.network)
        if capability == PROCESS:
            return bool(path) and path in self.process
        return any(is_inside(scope, path) for scope in self.of(capability))

    def comparable(self, capability: str, path: str) -> bool:
        """Whether a declared path and `path` can be compared at all.

        With nothing declared the answer is that the path is not covered. With a
        declaration of another root (one relative and the other absolute) they cannot
        be compared without the working directory, and saying that they do not match
        would be guessing: guessing wrong here would reject a program that the
        interpreter would run.
        """
        if capability in (NETWORK, PROCESS):
            return True
        scopes = self.of(capability)
        if not scopes:
            return True
        return any(same_root(scope, path) for scope in scopes)


@dataclass(frozen=True)
class Grants:
    """What the user allowed on the command line, by capability.

    The scopes are the values written in the corresponding `--allow-*` options. File
    paths are resolved when they are used.
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    network: tuple[str, ...] = ()
    process: tuple[str, ...] = ()

    def of(self, capability: str) -> tuple[str, ...]:
        """The paths allowed for a capability."""
        return {
            READ: self.read,
            WRITE: self.write,
            NETWORK: self.network,
            PROCESS: self.process,
        }.get(capability, ())


class NotAllowed(Exception):
    """The program asked for something the environment does not allow it to do.

    It is not an `OSError`: the operating system refusing a file is a different
    thing, and the two are reported with different diagnostics (decision 0015, 4).
    """


class Host(Protocol):
    """What the environment lets a program do besides computing.

    The interpreter never touches the operating system: it asks the host, which the
    entry point built with what the user granted. A host that does not allow something
    says so with `NotAllowed`; a host with nothing left to read says so with
    `EOFError`.
    """

    def arguments(self) -> tuple[str, ...]:
        """The arguments the program was run with."""

    def read_line(self) -> str:
        """One line of the standard input, without its terminator.

        Raises `EOFError` when there is nothing left to read.
        """

    def read_file(self, path: str) -> str:
        """The contents of a file the program is allowed to read.

        Raises `NotAllowed` when the program is not allowed to read it, and
        `OSError` when the file itself cannot be read.
        """

    def write_file(self, path: str, text: str) -> None:
        """Writes a file the program is allowed to write.

        Raises `NotAllowed` when the program is not allowed to write it, and
        `OSError` when the file itself cannot be written.
        """

    def get_url(self, url: str) -> str:
        """Fetches a bounded HTTPS text response from an explicitly allowed origin."""

    def run_process(self, command: str, arguments: tuple[str, ...]) -> str:
        """Runs one explicitly allowed executable without a shell and returns its stdout."""


class NoHost:
    """The host of a program that runs with nothing: no arguments, no input, no files.

    It is what the interpreter uses when the environment gives it no host, so that a
    program that asks for something it cannot have fails with a clear diagnostic
    instead of reading anything (decision 0015, 6).
    """

    def arguments(self) -> tuple[str, ...]:
        return ()

    def read_line(self) -> str:
        raise EOFError("there is no input to read")

    def read_file(self, path: str) -> str:
        raise NotAllowed(f"this environment does not allow reading files, so '{path}' cannot be read")

    def write_file(self, path: str, text: str) -> None:
        raise NotAllowed(f"this environment does not allow writing files, so '{path}' cannot be written")

    def get_url(self, url: str) -> str:
        raise NotAllowed("this environment does not allow network access")

    def run_process(self, command: str, arguments: tuple[str, ...]) -> str:
        raise NotAllowed("this environment does not allow external processes")


def _split(path: str) -> tuple[str, list[str]]:
    """The root of a path and its segments, with `.` and `..` resolved.

    Without touching the file system: only the file system knows what a symbolic link
    means. A `..` that would leave a relative path is kept, and one that would leave
    the root is dropped, as the file system does.
    """
    text = path.replace("\\", "/")
    root = ""
    if text.startswith("/"):
        root = "/"
        text = text[1:]
    elif len(text) > 1 and text[1] == ":":
        root = text[:2].upper()
        text = text[2:]
    segments: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if segments and segments[-1] != "..":
                segments.pop()
            elif not root:
                segments.append("..")
            continue
        segments.append(part)
    return root, segments


def same_root(first: str, second: str) -> bool:
    """Whether two paths can be compared: they need the same root.

    A relative path and an absolute one are not comparable without the working
    directory.
    """
    return _split(first)[0] == _split(second)[0]


def is_inside(scope: str, path: str) -> bool:
    """Whether `path` is `scope` itself or is inside it.

    Both paths are compared by segments, and their roots have to be the same: `datos2` is
    not inside `datos`, and a relative path is never inside an absolute one. An empty
    scope covers nothing: it would cover everything.
    """
    if not scope:
        return False
    scope_root, scope_segments = _split(scope)
    path_root, path_segments = _split(path)
    if scope_root != path_root:
        return False
    if len(path_segments) < len(scope_segments):
        return False
    return path_segments[:len(scope_segments)] == scope_segments

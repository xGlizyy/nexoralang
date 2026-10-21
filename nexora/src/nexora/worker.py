"""One-shot worker process: answers a single request and exits.

A host (the web server of the playground) starts `python -I -m nexora.worker` for each
request, writes one JSON document to its standard input and reads one JSON document
from its standard output. Running the program in a separate, short-lived process means
that the host can kill it, and that a program that exhausts time or memory cannot take
the host down with it.

Request:

    {"action": "check" | "run" | "info",
     "code": "<source>", "filename": "playground.nex",
     "limits": {"output_bytes": 65536, "text_chars": 262144,
                "memory_bytes": 536870912, "cpu_seconds": 2, "wall_seconds": 3}}

Response: the dictionary returned by `nexora.api`, plus "duration_ms" and "version".

The limits come from the host, never from the visitor. On POSIX systems the CPU and
wall-clock limits are enforced by the operating system (`resource`, `signal`), and so are the
limits of files and processes. The limit of memory is the address space of the process
(RLIMIT_AS): the kernel of Linux enforces it, the one of macOS accepts it and does not apply
it. On Windows none of those are available and are ignored: there the only protections are the
ones the host applies from outside (killing the process on timeout). See docs/playground.md for
what this does and does not guarantee.

This process is not a sandbox by itself. It runs with the permissions of whoever starts it.
"""

from __future__ import annotations

import json
import sys
import time

from . import api
from .host import LocalHost
from .version import __version__

# Hard cap on the request this process is willing to read, whatever the host says.
MAX_REQUEST_BYTES = 1_048_576

INTERNAL_ERROR = "internal_error"


def _apply_os_limits(limits: dict) -> list[str]:
    """Asks the operating system to enforce the limits. Returns the names of those applied."""
    applied: list[str] = []
    try:
        import resource
        import signal
    except ImportError:
        # Windows: no `resource` module. Nothing is enforced from inside the process.
        return applied

    def limit(name: str, kind: int, value: int) -> None:
        try:
            resource.setrlimit(kind, (value, value))
            applied.append(name)
        except (ValueError, OSError):
            pass

    memory = limits.get("memory_bytes")
    if isinstance(memory, int) and memory > 0:
        limit("memory", resource.RLIMIT_AS, memory)
    cpu = limits.get("cpu_seconds")
    if isinstance(cpu, int) and cpu > 0:
        limit("cpu", resource.RLIMIT_CPU, cpu)
    # A program has no way to create files or processes; these make that an OS-level fact too.
    limit("no_files", resource.RLIMIT_FSIZE, 0)
    limit("no_core", resource.RLIMIT_CORE, 0)
    if hasattr(resource, "RLIMIT_NPROC"):
        limit("no_processes", resource.RLIMIT_NPROC, 0)

    wall = limits.get("wall_seconds")
    if isinstance(wall, (int, float)) and wall > 0 and hasattr(signal, "setitimer"):
        # SIGALRM's default action ends the process: a last resort if the host does not kill it.
        signal.setitimer(signal.ITIMER_REAL, float(wall))
        applied.append("wall_clock")
    return applied


def handle(request: dict) -> dict:
    """Answers one request. Raises ValueError if the request itself is malformed."""
    action = request.get("action")
    if action == "info":
        return {"schema": api.RESULT_SCHEMA, "action": "info", "status": api.SUCCESS, **api.language_info()}

    code = request.get("code")
    filename = request.get("filename", api.DEFAULT_FILENAME)
    limits = request.get("limits") or {}
    if not isinstance(code, str) or not isinstance(filename, str) or not isinstance(limits, dict):
        raise ValueError("malformed request")

    started = time.perf_counter()
    if action == "check":
        result = api.check_source(code, filename)
    elif action == "run":
        # The worker never allows files, and its protocol has no field to ask for them: a
        # program that reads or writes a file stops with E3008 (decision 0015, 6).
        host = LocalHost(files_allowed=False)
        result = api.run_source(code, filename, limits=api.Limits(
            output_bytes=limits.get("output_bytes"),
            text_chars=limits.get("text_chars"),
        ), host=host)
    else:
        raise ValueError("unknown action")
    result["duration_ms"] = round((time.perf_counter() - started) * 1000)
    result["version"] = __version__
    return result


def main() -> int:
    # Bytes in, bytes out, always UTF-8: no dependence on the locale of the host.
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("request too large")
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("malformed request")
        _apply_os_limits(request.get("limits") or {})
        response = handle(request)
        code = 0
    except MemoryError:
        # The memory limit was hit outside a running program (while analysing a huge one, say).
        response = {
            "schema": api.RESULT_SCHEMA, "action": "run", "status": api.MEMORY_LIMIT, "output": "",
            "diagnostics": [], "message": "The program needed more memory than this environment allows.",
            "duration_ms": 0, "version": __version__,
        }
        code = 0
    except Exception as error:  # the host must always get a well-formed answer
        # Only the kind of failure is reported: no message, no traceback, no source code.
        print(f"nexora worker failed: {type(error).__name__}", file=sys.stderr)
        response = {"schema": api.RESULT_SCHEMA, "status": INTERNAL_ERROR}
        code = 1

    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())

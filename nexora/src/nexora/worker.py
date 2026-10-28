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
import posixpath
import sys
import time

from . import api
from .capabilities import NoHost
from .debugging import DebugEvent, format_debug_value
from .diagnostics import CONTRACT, NexoraRuntimeError, Source
from .interpreter import run
from .host import LocalHost
from .pipeline import analyze
from .version import __version__

# Hard cap on the request this process is willing to read, whatever the host says.
MAX_REQUEST_BYTES = 1_048_576

INTERNAL_ERROR = "internal_error"
DEBUG_SCHEMA = "nexora.debug/1"
DEBUG_MAX_STEPS = 10_000
DEBUG_MAX_BREAKPOINTS = 256
DEBUG_MAX_COMMAND_BYTES = 8192


def _apply_os_limits(limits: dict, *, debug_session: bool = False) -> list[str]:
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

    # Debug sessions pause while waiting for a browser command. The server applies a fresh wall
    # timeout to every command and expires idle sessions; a process-wide alarm would kill a normal
    # pause before the person had time to inspect it.
    wall = None if debug_session else limits.get("wall_seconds")
    if isinstance(wall, (int, float)) and wall > 0 and hasattr(signal, "setitimer"):
        # SIGALRM's default action ends the process: a last resort if the host does not kill it.
        signal.setitimer(signal.ITIMER_REAL, float(wall))
        applied.append("wall_clock")
    return applied


def _project_analysis(code: str, filename: str, files: object = None):
    """Analyse one source or a bounded virtual project, with per-function file ownership."""
    if files is None:
        analysis = analyze(Source(filename, code))
    else:
        if not isinstance(files, dict) or not 1 <= len(files) <= 32:
            raise ValueError("malformed project")
        normalized: dict[str, str] = {}
        for path, text in files.items():
            if not isinstance(path, str) or not isinstance(text, str):
                raise ValueError("malformed project")
            safe = path.replace("\\", "/")
            parts = safe.split("/")
            if (len(safe) > 256 or len(parts) > 8 or safe.startswith("/") or ":" in safe
                    or any(part in {"", ".", ".."} for part in parts) or not safe.endswith(".nex")
                    or any(len(part.removesuffix(".nex")) > 64 or not part.removesuffix(".nex").replace("_", "a").replace("-", "a").isalnum() for part in parts)):
                raise ValueError("invalid project path")
            normalized[safe] = text
        entry = filename.replace("\\", "/")
        if entry not in normalized:
            raise ValueError("missing project entry")

        def read_import(declaration, importing_file):
            joined = posixpath.normpath(posixpath.join(posixpath.dirname(importing_file), declaration.path))
            if joined.startswith("../") or joined == ".." or joined.startswith("/") or joined not in normalized:
                from .diagnostics import Diagnostic
                return Diagnostic("E0001", f"Module '{declaration.path}' is not part of this project",
                                  declaration.path_span, hint="Add the imported .nex file to this project.")
            return joined, joined.rsplit("/", 1)[-1][:-4], Source(joined, normalized[joined])

        analysis = analyze(Source(entry, normalized[entry]), read=read_import)
    source_files = {}
    if analysis.project:
        source_files = {id(function): module.source.name
                        for module in analysis.project.modules if module.program
                        for function in module.program.functions}
    return analysis, source_files


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
    files = request.get("files")
    if files is not None:
        if action not in {"check", "run"}:
            raise ValueError("malformed project")
        from .diagnostics import CONTRACT, NexoraRuntimeError
        from .interpreter import run as interpret
        analysis, source_files = _project_analysis(code, filename, files)
        reports = analysis.project.reports() if analysis.project else tuple((d, analysis.source) for d in analysis.diagnostics)
        diagnostics = [diagnostic.to_dict(source.name) for diagnostic, source in reports]
        if analysis.checked is None:
            result = {"schema": api.RESULT_SCHEMA, "action": action, "status": api.INVALID,
                      "output": "", "diagnostics": diagnostics, "message": None}
        elif action == "check":
            result = {"schema": api.RESULT_SCHEMA, "action": action, "status": api.SUCCESS,
                      "output": "", "diagnostics": diagnostics, "message": None}
        else:
            output = api._Output(limits.get("output_bytes"))
            try:
                interpret(analysis.checked, output.write, text_limit=limits.get("text_chars"),
                          host=LocalHost(files_allowed=False), source_files=source_files)
                result = {"schema": api.RESULT_SCHEMA, "action": action, "status": api.SUCCESS,
                          "output": output.text(), "diagnostics": [], "message": None}
            except NexoraRuntimeError as error:
                status = api.CONTRACT_VIOLATION if error.diagnostic.category == CONTRACT else api.RUNTIME_ERROR
                result = {"schema": api.RESULT_SCHEMA, "action": action, "status": status,
                          "output": output.text(), "diagnostics": [error.diagnostic.to_dict(error.file or entry)], "message": None}
            except api._OutputLimitReached:
                result = {"schema": api.RESULT_SCHEMA, "action": action, "status": api.OUTPUT_LIMIT,
                          "output": output.text(), "diagnostics": [],
                          "message": f"The program printed more than {limits.get('output_bytes')} bytes and was stopped."}
            except MemoryError:
                result = {"schema": api.RESULT_SCHEMA, "action": action, "status": api.MEMORY_LIMIT,
                          "output": output.text(), "diagnostics": [], "message": api._MEMORY_MESSAGE}
        result["duration_ms"] = round((time.perf_counter() - started) * 1000)
        result["version"] = __version__
        return result
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


def _debug_line(response: dict) -> None:
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _debug_snapshot(event: DebugEvent, output_delta: str) -> dict:
    frames = [
        {
            "function": frame.function,
            "file": frame.file,
            "call_site": None if frame.call_site is None else {
                "line": frame.call_site.line,
                "column": frame.call_site.column,
            },
        }
        for frame in event.call_stack[:64]
    ]
    variables = [
        {"name": name, "value": format_debug_value(value)}
        for name, value in event.variables[:64]
    ]
    if len(event.call_stack) > len(frames):
        frames.append({"function": "…", "call_site": None})
    if len(event.variables) > len(variables):
        variables.append({"name": "…", "value": "additional variables omitted"})
    return {
        "step": event.step,
        "line": event.span.line,
        "column": event.span.column,
        "function": event.function,
        "file": event.file,
        "call_stack": frames,
        "variables": variables,
        "output": output_delta,
    }


def _valid_breakpoints(value, line_count: int) -> set[int]:
    if not isinstance(value, list) or len(value) > DEBUG_MAX_BREAKPOINTS:
        raise ValueError("invalid breakpoints")
    if any(type(line) is not int or not 1 <= line <= line_count for line in value):
        raise ValueError("invalid breakpoints")
    return set(value)


def _debug_session(request: dict) -> int:
    """Keep one interpreter alive while its controller inspects and advances the program."""
    code = request.get("code")
    filename = request.get("filename", api.DEFAULT_FILENAME)
    limits = request.get("limits") or {}
    if not isinstance(code, str) or not isinstance(filename, str) or not isinstance(limits, dict):
        raise ValueError("malformed debug request")
    files = request.get("files")
    analysis, source_files = _project_analysis(code, filename, files)
    line_counts = {filename: code.count("\n") + 1}
    if isinstance(files, dict):
        line_counts = {path.replace("\\", "/"): text.count("\n") + 1 for path, text in files.items()}
    requested_breakpoints = request.get("breakpoints", [])
    if isinstance(requested_breakpoints, list):
        requested_breakpoints = {filename: requested_breakpoints}
    if not isinstance(requested_breakpoints, dict) or len(requested_breakpoints) > 32:
        raise ValueError("invalid breakpoints")
    breakpoints: dict[str, set[int]] = {}
    count = 0
    for path, lines in requested_breakpoints.items():
        if path not in line_counts:
            raise ValueError("invalid breakpoints")
        breakpoints[path] = _valid_breakpoints(lines, line_counts[path])
        count += len(breakpoints[path])
    if count > DEBUG_MAX_BREAKPOINTS:
        raise ValueError("invalid breakpoints")
    if analysis.checked is None:
        _debug_line({
            "schema": DEBUG_SCHEMA,
            "state": "invalid",
            "diagnostics": [diagnostic.to_dict(source.name) for diagnostic, source in analysis.project.reports()],
            "version": __version__,
        })
        return 0

    output = api._Output(limits.get("output_bytes"))
    state = {"mode": "step", "terminal": None, "output_length": 0}

    def output_delta() -> str:
        text = output.text()
        start = state["output_length"]
        state["output_length"] = len(text)
        return text[start:]

    def observe(event: DebugEvent) -> bool:
        if event.step > DEBUG_MAX_STEPS:
            state["terminal"] = "limit"
            _debug_line({
                "schema": DEBUG_SCHEMA,
                "state": "limit",
                "message": f"A debug session can inspect at most {DEBUG_MAX_STEPS} statements.",
                "snapshot": _debug_snapshot(event, output_delta()),
                "version": __version__,
            })
            return True
        event_file = event.file or filename
        if state["mode"] == "continue" and event.span.line not in breakpoints.get(event_file, set()):
            return False

        while True:
            _debug_line({
                "schema": DEBUG_SCHEMA,
                "state": "paused",
                "snapshot": _debug_snapshot(event, output_delta()),
                "version": __version__,
            })
            raw = sys.stdin.buffer.readline(DEBUG_MAX_COMMAND_BYTES + 1)
            if not raw:
                state["terminal"] = "disconnected"
                return True
            if len(raw) > DEBUG_MAX_COMMAND_BYTES or not raw.endswith(b"\n"):
                _debug_line({"schema": DEBUG_SCHEMA, "state": "command_error", "message": "The command is too large."})
                continue
            try:
                command = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _debug_line(
                    {"schema": DEBUG_SCHEMA, "state": "command_error", "message": "The command is not valid JSON."}
                )
                continue
            if not isinstance(command, dict):
                _debug_line(
                    {"schema": DEBUG_SCHEMA, "state": "command_error", "message": "The command must be an object."}
                )
                continue
            action = command.get("command")
            if action == "step":
                state["mode"] = "step"
                return False
            if action == "continue":
                state["mode"] = "continue"
                return False
            if action == "stop":
                state["terminal"] = "stopped"
                _debug_line({
                    "schema": DEBUG_SCHEMA,
                    "state": "stopped",
                    "snapshot": _debug_snapshot(event, output_delta()),
                    "version": __version__,
                })
                return True
            if action == "set_breakpoints":
                path = command.get("file", filename)
                try:
                    if path not in line_counts:
                        raise ValueError("invalid file")
                    replacement = _valid_breakpoints(command.get("lines"), line_counts[path])
                except (ValueError, TypeError):
                    _debug_line(
                        {"schema": DEBUG_SCHEMA, "state": "command_error", "message": "Invalid breakpoint lines."}
                    )
                    continue
                breakpoints[path] = replacement
                continue
            _debug_line({"schema": DEBUG_SCHEMA, "state": "command_error", "message": "Unknown debug command."})

    try:
        run(
            analysis.checked,
            output.write,
            text_limit=limits.get("text_chars"),
            host=NoHost(),
            debug_observer=observe,
            source_files=source_files,
        )
    except NexoraRuntimeError as error:
        status = "contract_violation" if error.diagnostic.category == CONTRACT else "runtime_error"
        _debug_line({
            "schema": DEBUG_SCHEMA,
            "state": status,
            "diagnostics": [error.diagnostic.to_dict(error.file or filename)],
            "output": output_delta(),
            "version": __version__,
        })
        return 0
    except api._OutputLimitReached:
        _debug_line({
            "schema": DEBUG_SCHEMA,
            "state": "output_limit",
            "message": f"The program printed more than {limits.get('output_bytes')} bytes and was stopped.",
            "output": output_delta(),
            "version": __version__,
        })
        return 0
    except MemoryError:
        _debug_line({
            "schema": DEBUG_SCHEMA,
            "state": "memory_limit",
            "message": "The program needed more memory than this environment allows.",
            "output": output_delta(),
            "version": __version__,
        })
        return 0
    if state["terminal"] == "limit":
        return 0
    if state["terminal"] == "stopped":
        return 0
    if state["terminal"] == "disconnected":
        return 0
    _debug_line({
        "schema": DEBUG_SCHEMA,
        "state": "completed",
        "output": output_delta(),
        "version": __version__,
    })
    return 0


def main() -> int:
    # Bytes in, bytes out, always UTF-8: no dependence on the locale of the host.
    is_debug = False
    try:
        raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("request too large")
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("malformed request")
        is_debug = request.get("action") == "debug"
        _apply_os_limits(request.get("limits") or {}, debug_session=is_debug)
        if is_debug:
            return _debug_session(request)
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
        if is_debug:
            _debug_line({"schema": DEBUG_SCHEMA, "state": INTERNAL_ERROR})
            return 1
        response = {"schema": api.RESULT_SCHEMA, "status": INTERNAL_ERROR}
        code = 1

    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())

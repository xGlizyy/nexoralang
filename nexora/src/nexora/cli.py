"""The `nex` command-line interface."""

from __future__ import annotations

import argparse
import errno
import io
import json
import math
import os
import signal
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from . import api, migrate, migrate_files, tooling
from .capabilities import Capabilities, Grants, TextLimitExceeded
from .debugging import DebugEvent, format_debug_value
from .diagnostics import CONTRACT, ERROR, MAX_DIAGNOSTICS, Diagnostic, NexoraRuntimeError, Source, render
from .host import LocalHost
from .interpreter import run
from .pipeline import Analysis, analyze
from .version import __version__

# Exit codes (documented in docs/language-spec.md and the README).
EXIT_OK = 0
EXIT_INVALID_PROGRAM = 1     # lexical, syntax, semantic or type errors, found without running
EXIT_USAGE = 2               # wrong command-line arguments (argparse's own convention)
EXIT_RUNTIME_ERROR = 3       # the program started and then failed
EXIT_UNREADABLE_FILE = 4     # the file does not exist or cannot be read as UTF-8
EXIT_CONTRACT_VIOLATION = 5  # a rule the program declares was broken while running
EXIT_TEST_FAILED = 6         # nex test: an example did not pass, or there was no example to run
EXIT_INTERNAL_ERROR = 70     # a bug in NEXORA itself
EXIT_INTERRUPTED = 130       # stopped by the user with Ctrl+C

_EPILOG = """\
exit codes:
  0   success
  1   the program has lexical, syntax, semantic or type errors
  2   wrong command-line usage
  3   the program failed while running
  4   the file could not be read; nex migrate --write: a file could not be written
  5   the program broke a rule it declares while running: a contract
      ('needs', 'promises') or the condition of a refined type
  6   nex test: an example did not pass, or there was no example to run
  70  internal error in NEXORA (a bug, please report it)
  130 interrupted with Ctrl+C
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nex",
        description="NEXORA: run, debug, check and analyse programs written in the NEXORA language.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"NEXORA {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    run_parser = commands.add_parser(
        "run",
        help="check a .nex file and run it",
        description=(
            "Check a NEXORA program and, if it is valid, run its main function. "
            "A program with static errors is never started."
        ),
    )
    run_parser.add_argument("file", help="path to the .nex file to run")
    run_parser.add_argument("--timeout", type=float, metavar="SECONDS", help="stop the program after this many seconds")
    run_parser.add_argument("--max-output", type=int, metavar="BYTES", help="maximum UTF-8 bytes the program may print")
    run_parser.add_argument(
        "--max-text", type=int, metavar="CHARS", help="maximum characters in a constructed Text value",
    )
    run_parser.add_argument("--max-source", type=int, metavar="BYTES", help="maximum source-file size")
    run_parser.add_argument(
        "--max-input", type=int, metavar="BYTES", help="maximum bytes the program may read from standard input",
    )
    run_parser.add_argument(
        "--max-memory", type=int, metavar="BYTES", help="maximum process address space (Linux; includes Python)",
    )
    run_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to report errors (default: text). 'json' writes one JSON document to standard error "
             "if the program is invalid or fails; the program's own output is not affected",
    )
    run_parser.add_argument(
        "--allow-read", action="append", default=[], metavar="RUTA",
        help="allow the program to read the files under this path (can be repeated). A program also "
             "has to declare it with 'uses read'",
    )
    run_parser.add_argument(
        "--allow-write", action="append", default=[], metavar="RUTA",
        help="allow the program to write the files under this path (can be repeated). A program also "
             "has to declare it with 'uses write'",
    )
    run_parser.add_argument(
        "--allow-network", action="append", default=[], metavar="ORIGIN",
        help="allow HTTPS requests to this origin (repeatable); the program must declare 'uses network'",
    )
    run_parser.add_argument(
        "--allow-process", action="append", default=[], metavar="COMMAND",
        help="allow this executable to run (can be repeated). A program also has to declare it with 'uses process'",
    )
    run_parser.add_argument(
        "args", nargs="*",
        help="the arguments of the program, written after '--'",
    )

    debug_parser = commands.add_parser(
        "debug",
        help="step through a .nex file in a local terminal",
        description=(
            "Check a NEXORA program and run it under the statement debugger. The debugger pauses "
            "before each statement and can show the live variables and call stack. Debug commands "
            "are read from the terminal; the program keeps standard input for input()."
        ),
    )
    debug_parser.add_argument("file", help="path to the .nex file to debug")
    debug_parser.add_argument("--breakpoint", action="append", default=[], type=int, metavar="LINE",
                              help="stop at this line in the entry file when continuing (can be repeated)")
    debug_parser.add_argument("--max-steps", type=int, default=10_000, metavar="COUNT",
                              help="maximum statements inspected (default: 10000)")
    debug_parser.add_argument("--timeout", type=float, metavar="SECONDS",
                              help="limit active program execution time; time at the prompt is excluded")
    debug_parser.add_argument("--max-output", type=int, metavar="BYTES",
                              help="maximum UTF-8 bytes the program may print")
    debug_parser.add_argument("--max-text", type=int, metavar="CHARS",
                              help="maximum characters in a constructed Text value")
    debug_parser.add_argument("--max-source", type=int, metavar="BYTES",
                              help="maximum size of each source file, including imported modules")
    debug_parser.add_argument("--max-input", type=int, metavar="BYTES",
                              help="maximum bytes the program may read from standard input")
    debug_parser.add_argument("--max-memory", type=int, metavar="BYTES",
                              help="maximum process address space (Linux; includes Python)")
    debug_parser.add_argument("--allow-read", action="append", default=[], metavar="PATH",
                              help="allow the program to read files under this path (repeatable)")
    debug_parser.add_argument("--allow-write", action="append", default=[], metavar="PATH",
                              help="allow the program to write files under this path (repeatable)")
    debug_parser.add_argument("--allow-network", action="append", default=[], metavar="ORIGIN",
                              help="allow HTTPS access to this origin (repeatable)")
    debug_parser.add_argument("--allow-process", action="append", default=[], metavar="COMMAND",
                              help="allow this executable to run (repeatable)")
    debug_parser.add_argument("--format", choices=("text", "json"), default="text",
                              help="how to report program errors (default: text)")
    debug_parser.add_argument("args", nargs="*", help="program arguments, written after '--'")

    check_parser = commands.add_parser(
        "check",
        help="check a .nex file without running it",
        description=(
            "Check the syntax, names and types of a NEXORA program, including the expressions of its "
            "contracts. The program is not executed: nothing is printed by it."
        ),
    )
    check_parser.add_argument("file", help="path to the .nex file to check")
    check_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to report the result (default: text). 'json' writes one JSON document to standard output",
    )
    check_parser.add_argument(
        "--evidence",
        action="store_true",
        help="also report what backs every needs, promises, trust, keeps and shrinks of the program "
             "(nexora.evidence/1 with --format json). Nothing is run",
    )

    inspect_parser = commands.add_parser(
        "inspect",
        help="print the structure of a .nex file as JSON, without running it",
        description=(
            "Print the syntax tree of a NEXORA program as JSON: functions, parameters, contracts, "
            "statements and expressions, each with its position and, where known, its type. "
            "The program is not executed."
        ),
    )
    inspect_parser.add_argument("file", help="path to the .nex file to inspect")
    inspect_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        help="output format (only 'json' exists, and it is the default)",
    )

    context_parser = commands.add_parser(
        "context",
        help="summarise a .nex file for a person or a tool, without running it",
        description=(
            "Print a compact technical summary of a NEXORA program: its functions and their signatures, "
            "contracts, variables and their types, which function calls which, the language features it "
            "uses and its current diagnostics. Everything comes from static analysis: the program is not "
            "executed and no AI model is involved."
        ),
    )
    context_parser.add_argument("file", help="path to the .nex file to summarise")
    context_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to write the summary (default: text). 'json' writes one JSON document to standard output",
    )

    symbols_parser = commands.add_parser(
        "symbols",
        help="list the functions, parameters and variables of a .nex file, and where each is used",
        description=(
            "List the symbols a NEXORA program declares, with their type, the place of their declaration, "
            "the block where they are visible and every reference the static analysis resolved. "
            "The program is not executed."
        ),
    )
    symbols_parser.add_argument("file", help="path to the .nex file to analyse")
    symbols_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to write the list (default: text). 'json' writes one JSON document to standard output",
    )
    symbols_parser.add_argument("--name", help="only the symbols with this name")
    symbols_parser.add_argument("--function", help="only this function and what is declared inside it")

    test_parser = commands.add_parser(
        "test",
        help="evaluate the 'example' clauses of a .nex file",
        description=(
            "Check a NEXORA program and, if it is valid, evaluate the 'example' clauses of its functions, "
            "each one on its own. 'main' is not required and is never run. The contracts of every "
            "function called while evaluating an example are checked as usual."
        ),
    )
    test_parser.add_argument("file", help="path to the .nex file to test")
    test_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to write the report (default: text). 'json' writes one nexora.test/1 document to standard output",
    )
    migrate_parser = commands.add_parser(
        "migrate",
        help="rewrite a program of NEXORA 0.11 in the syntax of 0.12",
        description=(
            "Check a program and every module it imports with the front ends of 0.11 and of 0.12, and "
            "show the edits that move it to the syntax of 0.12 (decision 0019). Without --write nothing "
            "is written. With --write the files are replaced only if every check passed."
        ),
    )
    migrate_parser.add_argument("file", help="path to the .nex file of the program")
    migrate_parser.add_argument("--write", action="store_true",
                                help="replace the files of the program with their migrated text")

    test_parser.add_argument("--function", help="only the examples declared in this function")
    test_parser.add_argument(
        "--allow-read", action="append", default=[], metavar="RUTA",
        help="allow the examples to read the files under this path (can be repeated)",
    )
    test_parser.add_argument(
        "--allow-write", action="append", default=[], metavar="RUTA",
        help="allow the examples to write the files under this path (can be repeated)",
    )
    test_parser.add_argument(
        "--allow-network", action="append", default=[], metavar="ORIGIN",
        help="allow examples to make HTTPS requests to this origin (can be repeated)",
    )
    test_parser.add_argument(
        "--allow-process", action="append", default=[], metavar="COMMAND",
        help="allow examples to run this executable (can be repeated)",
    )
    return parser


def _load(path: str, *, max_bytes: int | None = None) -> tuple[Source | None, Diagnostic | None]:
    try:
        if max_bytes is None:
            data = Path(path).read_bytes()
        else:
            with Path(path).open("rb") as source_file:
                data = source_file.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise _CliLimit("source", max_bytes, path)
    except OSError as error:
        reason = error.strerror or type(error).__name__
        return None, Diagnostic("E0001", f"{reason}: {path}")
    try:
        # utf-8-sig also accepts files that start with a byte-order mark.
        return Source(path, data.decode("utf-8-sig")), None
    except UnicodeDecodeError:
        return None, Diagnostic("E0002", f"{path} must be saved as UTF-8 text")


def _module_path(declaration, importing_file: str) -> Path:
    """The file an import names, resolved where the file that has the import is, and not
    where the command was run: a program depends on where it is, not on where it is
    started from (decision 0018, 1)."""
    return (Path(importing_file).parent / declaration.path).resolve()


def _shown_path(declaration, importing_shown: str) -> str:
    """The path of a module as a report shows it: the path of the file that imports it,
    joined with the path the import writes, with '/' on every system. It never depends on
    the machine the command runs on, as the absolute path would (decision 0018, 1)."""
    joined = os.path.join(os.path.dirname(importing_shown), declaration.path)
    return os.path.normpath(joined).replace("\\", "/")


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _read_module(declaration, path: Path, key: str, shown: str, source=Source, diagnostic=Diagnostic,
                 read_bytes=_read_bytes, max_bytes: int | None = None):
    """Reads the module an import names (decision 0018, 1).

    This is the one place where the analysis touches the file system: the stages of the
    language never import `os` or `pathlib` (tests/test_security.py), so they ask here.
    `source` and `diagnostic` are the classes of the front end that asks: the frozen 0.11
    front end of `nex migrate` has its own (decision 0019, 8.2). `nex migrate` also reads through
    its own `read_bytes`, so that every file it reads goes through `migrate_files.Files` (8.9.2).
    """
    try:
        if max_bytes is None:
            data = read_bytes(path)
        else:
            with path.open("rb") as source_file:
                data = source_file.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise _CliLimit("source", max_bytes, shown)
    except _CliLimit:
        raise
    except OSError as error:
        return diagnostic(
            "E0001", f"{error.strerror or type(error).__name__}: {shown}", declaration.path_span,
            hint="An import names a file relative to the file that has it: "
                 'import "app/models.nex".',
        )
    try:
        # utf-8-sig also accepts files that start with a byte-order mark.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return diagnostic("E0002", f"{shown} is not valid UTF-8", declaration.path_span)
    return key, path.stem, source(shown, text)


def _module_reader(entry: Source, source=Source, diagnostic=Diagnostic, read_bytes=_read_bytes,
                   max_source: int | None = None):
    """The `Reader` a command analyses with: a file is read once, however many import it.

    The answer is remembered with the path it was resolved to, so two imports that name
    the same file from different files reach it once (decision 0018, 1). That path is only
    the key: a module is shown with its path relative to the program (`_shown_path`).

    The program itself is known to the loader by the path it was given, so an import that
    reaches it answers with that same key: a module that imports the program is a cycle at
    the first step, and the program is never read a second time (decision 0018, 4). Every
    command gets its own reader: nothing is remembered from one command to the next.
    """
    entry_file = Path(entry.name).resolve()
    read_once: dict[str, tuple[str, str, Source] | Diagnostic] = {}
    # The path each key is shown with, so a module imported by a module is shown relative
    # to the program and not to the machine.
    shown = {entry.name: entry.name}

    def read(declaration, importing_file: str):
        path = _module_path(declaration, importing_file)
        if path == entry_file:
            return entry.name, entry_file.stem, entry
        key = str(path)
        if key not in read_once:
            shown[key] = _shown_path(declaration, shown.get(importing_file, importing_file))
            read_once[key] = _read_module(
                declaration, path, key, shown[key], source, diagnostic, read_bytes, max_source,
            )
        return read_once[key]

    return read


def _reports(analysis: Analysis) -> tuple[tuple[Diagnostic, Source], ...]:
    """Every diagnostic of an analysis, each beside the file it belongs to.

    An error in a module the program imports is shown with the text of that module and not
    with the text of the program: its position belongs to the other file (decision 0018).
    """
    if analysis.project is not None:
        return analysis.project.reports()
    return tuple((diagnostic, analysis.source) for diagnostic in analysis.diagnostics)


def _write_reports(reports) -> None:
    for diagnostic, source in reports:
        print(render(diagnostic, source), file=sys.stderr)
        print(file=sys.stderr)


def _document(path: str, reports) -> dict:
    """The diagnostics document for a list of (diagnostic, file) pairs."""
    return tooling.diagnostics_document(
        path, [diagnostic for diagnostic, _ in reports], files=[source.name for _, source in reports])


def _report(diagnostics, source: Source) -> None:
    for diagnostic in diagnostics:
        print(render(diagnostic, source), file=sys.stderr)
        print(file=sys.stderr)


def _print_json(document: dict, stream) -> None:
    print(json.dumps(document, indent=2, ensure_ascii=False), file=stream)


def _plural(count: int) -> str:
    if count >= MAX_DIAGNOSTICS:
        return f"{count} errors (stopped at the limit of {MAX_DIAGNOSTICS}; there may be more)"
    return "1 error" if count == 1 else f"{count} errors"


def _check(path: str, output_format: str, evidence: bool = False) -> int:
    source, failure = _load(path)
    if source is None:
        analysis = Analysis(Source(path, ""), (failure,))
        reports, code = ((failure, Source(path, "")),), EXIT_UNREADABLE_FILE
    else:
        analysis = analyze(source, read=_module_reader(source))
        reports = _reports(analysis)
        code = EXIT_OK if analysis.ok else EXIT_INVALID_PROGRAM

    errors = [diagnostic for diagnostic, _ in reports if diagnostic.severity == ERROR]
    if output_format == "json":
        # With --evidence, nexora.evidence/1 starts with the same fields as nexora.diagnostics/1.
        _print_json(tooling.evidence_document(analysis) if evidence else _document(path, reports), sys.stdout)
    elif errors:
        _write_reports(reports)
        print(f"error: {path}: check failed with {_plural(len(errors))}", file=sys.stderr)
    elif evidence:
        _write_reports(reports)
        print(tooling.render_evidence(tooling.evidence_document(analysis)))
    elif reports:
        _write_reports(reports)
        print(f"✓ Check passed with {_count(len(reports), 'warning')}: {path}")
    else:
        print(f"✓ Check passed: {path}")
    return code


def _analysis_command(path: str, output_format: str, build, render_text=None) -> int:
    """Shared by inspect, context and symbols: analyse the file and write one document.

    `build` turns the analysis into a document (a function of nexora.tooling); `render_text`
    turns that document into text for people. Nothing here runs the program.
    """
    source, failure = _load(path)
    if source is None:
        if output_format == "json":
            _print_json(build(Analysis(Source(path, ""), (failure,))), sys.stdout)
        else:
            _report((failure,), Source(path, ""))
        return EXIT_UNREADABLE_FILE

    analysis = analyze(source, read=_module_reader(source))
    document = build(analysis)
    if output_format == "json":
        _print_json(document, sys.stdout)
    else:
        print(render_text(document))
    return EXIT_OK if analysis.ok else EXIT_INVALID_PROGRAM


def _run(path: str, output_format: str, arguments: tuple[str, ...] = (),
         allow_read: tuple[str, ...] = (), allow_write: tuple[str, ...] = (),
         allow_network: tuple[str, ...] = (), allow_process: tuple[str, ...] = (),
         timeout: float | None = None, max_output: int | None = None,
         max_text: int | None = None, max_source: int | None = None,
         max_memory: int | None = None, max_input: int | None = None) -> int:
    for name, value in (("timeout", timeout), ("max-output", max_output), ("max-text", max_text),
                        ("max-source", max_source), ("max-input", max_input), ("max-memory", max_memory)):
        if value is not None and (value <= 0 or (name == "timeout" and not math.isfinite(value))):
            print(f"error: --{name} must be greater than zero", file=sys.stderr)
            return EXIT_USAGE

    if timeout is not None and (not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer")):
        print("error: --timeout requires a POSIX platform with interval timers", file=sys.stderr)
        return EXIT_USAGE
    if max_memory is not None and not sys.platform.startswith("linux"):
        print("error: --max-memory is enforced only on Linux; use an OS supervisor on this platform",
              file=sys.stderr)
        return EXIT_USAGE

    def limit_failure(error: _CliLimit, source: Source) -> int:
        name = "--max-source" if error.kind == "source" else error.kind
        diagnostic = Diagnostic("E3015", f"{name} limit exceeded ({error.limit})")
        source = Source(error.path, "") if error.path is not None else source
        if output_format == "json":
            _print_json(_document(path, ((diagnostic, source),)), sys.stderr)
        else:
            print(render(diagnostic, source), file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    def fail(reports, summary: str, code: int) -> int:
        # Whatever the program printed before failing is shown first.
        sys.stdout.flush()
        if output_format == "json":
            _print_json(_document(path, reports), sys.stderr)
        else:
            _write_reports(reports)
            print(f"error: {path}: {summary}", file=sys.stderr)
        return code

    try:
        source, failure = _load(path, max_bytes=max_source)
    except _CliLimit as error:
        return limit_failure(error, Source(path, ""))
    if source is None:
        return fail(((failure, Source(path, "")),), "the file could not be read", EXIT_UNREADABLE_FILE)

    source_reader = _module_reader(source, max_source=max_source)
    if max_memory is not None:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
        except (ImportError, AttributeError, OSError, ValueError):
            print("error: --max-memory requires POSIX RLIMIT_AS support", file=sys.stderr)
            return EXIT_USAGE

    try:
        analysis = analyze(source, read=source_reader)
    except _CliLimit as error:
        return limit_failure(error, source)
    except MemoryError:
        if max_memory is None:
            raise
        diagnostic = Diagnostic(
            "E3007", "Process memory limit exceeded while checking this program",
            hint="Increase --max-memory or reduce the size of the source project.",
        )
        return fail(((diagnostic, source),), "the process memory limit was exceeded", EXIT_RUNTIME_ERROR)
    if analysis.checked is None:
        errors = sum(1 for diagnostic in analysis.diagnostics if diagnostic.severity == ERROR)
        summary = f"not run because of {_plural(errors)}"
        return fail(_reports(analysis), summary, EXIT_INVALID_PROGRAM)

    input_bytes = 0

    def read_input() -> str:
        nonlocal input_bytes
        if max_input is None and max_text is None:
            line = sys.stdin.readline()
            if line == "":
                raise EOFError("the standard input ended")
            return line.removesuffix("\n").removesuffix("\r")
        if max_input is None:
            raw_text = sys.stdin.readline(max_text + 2)
            if raw_text == "":
                raise EOFError("the standard input ended")
            text = raw_text.removesuffix("\n").removesuffix("\r")
            if len(text) > max_text:
                raise TextLimitExceeded(max_text)
            return text
        remaining = max_input - input_bytes if max_input is not None else None
        read_size = remaining + 1 if remaining is not None else None
        if max_text is not None:
            text_read_size = 4 * (max_text + 1) + 1
            read_size = text_read_size if read_size is None else min(read_size, text_read_size)
        raw = sys.stdin.buffer.readline(read_size)
        if raw == b"":
            raise EOFError("the standard input ended")
        if remaining is not None and len(raw) > remaining:
            raise _CliLimit("input", max_input)
        if max_input is not None:
            input_bytes += len(raw)
        encoding = sys.stdin.encoding or "utf-8"
        errors = sys.stdin.errors or "strict"
        text = raw.decode(encoding, errors).removesuffix("\n").removesuffix("\r")
        if max_text is not None and len(text) > max_text:
            raise TextLimitExceeded(max_text)
        return text

    host = LocalHost(
        arguments=arguments,
        read_line=read_input,
        grants=Grants(read=allow_read, write=allow_write, network=allow_network, process=allow_process),
        declarations=analysis.checked.capabilities,
        network_allowed=True,
        max_text=max_text,
        processes_allowed=True,
    )
    written = 0
    def write_output(text: str) -> None:
        nonlocal written
        if max_output is None:
            sys.stdout.write(text)
            return
        for start in range(0, len(text), 4096):
            chunk = text[start:start + 4096]
            data = chunk.encode("utf-8")
            room = max_output - written
            if len(data) > room:
                prefix = data[:room].decode("utf-8", errors="ignore")
                sys.stdout.write(prefix)
                written += len(prefix.encode("utf-8"))
                raise _CliLimit("output", max_output)
            sys.stdout.write(chunk)
            written += len(data)

    previous_handler = None
    try:
        if timeout is not None:
            def expire(*_):
                raise _CliLimit("time", timeout)

            previous_handler = signal.signal(signal.SIGALRM, expire)
            signal.setitimer(signal.ITIMER_REAL, timeout)
        run(analysis.checked, write_output, text_limit=max_text, host=host)
    except _CliLimit as error:
        sys.stdout.flush()
        return limit_failure(error, source)
    except NexoraRuntimeError as error:
        if error.diagnostic.category == CONTRACT:
            return fail(((error.diagnostic, source),), "the program stopped because a contract was broken",
                        EXIT_CONTRACT_VIOLATION)
        return fail(((error.diagnostic, source),), "the program stopped because of a runtime error",
                    EXIT_RUNTIME_ERROR)
    finally:
        if timeout is not None and previous_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
    # Flushed here, not at interpreter exit, so that a closed pipe is handled by main().
    sys.stdout.flush()
    return EXIT_OK


_DEBUG_MAX_BREAKPOINTS = 256
_DEBUG_DEFAULT_MAX_STEPS = 10_000


def _open_debug_console():
    """Open the controlling terminal so debug commands do not consume program input."""
    return Path("CONIN$" if os.name == "nt" else "/dev/tty").open(
        encoding="utf-8", errors="replace",
    )


def _debug(path: str, output_format: str, arguments: tuple[str, ...] = (),
           breakpoints: tuple[int, ...] = (), max_steps: int = _DEBUG_DEFAULT_MAX_STEPS,
           allow_read: tuple[str, ...] = (), allow_write: tuple[str, ...] = (),
           allow_network: tuple[str, ...] = (), allow_process: tuple[str, ...] = (),
           timeout: float | None = None, max_output: int | None = None,
           max_text: int | None = None, max_source: int | None = None,
           max_memory: int | None = None, max_input: int | None = None,
           console=None) -> int:
    """Run the checked program with an interactive, statement-level observer."""
    for name, value in (("timeout", timeout), ("max-output", max_output), ("max-text", max_text),
                        ("max-source", max_source), ("max-input", max_input), ("max-memory", max_memory),
                        ("max-steps", max_steps)):
        if value is not None and (value <= 0 or (name == "timeout" and not math.isfinite(value))):
            print(f"error: --{name} must be greater than zero", file=sys.stderr)
            return EXIT_USAGE
    if timeout is not None and (not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer")):
        print("error: --timeout requires a POSIX platform with interval timers", file=sys.stderr)
        return EXIT_USAGE
    if max_memory is not None and not sys.platform.startswith("linux"):
        print("error: --max-memory is enforced only on Linux; use an OS supervisor on this platform",
              file=sys.stderr)
        return EXIT_USAGE

    close_console = console is None

    def limit_failure(error: _CliLimit, source: Source) -> int:
        name = "--max-source" if error.kind == "source" else error.kind
        diagnostic = Diagnostic("E3015", f"{name} limit exceeded ({error.limit})")
        source = Source(error.path, "") if error.path is not None else source
        if output_format == "json":
            _print_json(_document(path, ((diagnostic, source),)), sys.stderr)
        else:
            print(render(diagnostic, source), file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    def fail(reports, summary: str, code: int) -> int:
        sys.stdout.flush()
        if output_format == "json":
            _print_json(_document(path, reports), sys.stderr)
        else:
            _write_reports(reports)
            print(f"error: {path}: {summary}", file=sys.stderr)
        return code

    try:
        try:
            source, failure = _load(path, max_bytes=max_source)
        except _CliLimit as error:
            return limit_failure(error, Source(path, ""))
        if source is None:
            reports = ((failure, Source(path, "")),)
            if output_format == "json":
                _print_json(_document(path, reports), sys.stderr)
            else:
                _write_reports(reports)
                print(f"error: {path}: the file could not be read", file=sys.stderr)
            return EXIT_UNREADABLE_FILE

        if max_memory is not None:
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
            except (ImportError, AttributeError, OSError, ValueError):
                print("error: --max-memory requires POSIX RLIMIT_AS support", file=sys.stderr)
                return EXIT_USAGE

        try:
            analysis = analyze(source, read=_module_reader(source, max_source=max_source))
        except _CliLimit as error:
            return limit_failure(error, source)
        except MemoryError:
            if max_memory is None:
                raise
            diagnostic = Diagnostic(
                "E3007", "Process memory limit exceeded while checking this program",
                hint="Increase --max-memory or reduce the size of the source project.",
            )
            reports = ((diagnostic, source),)
            if output_format == "json":
                _print_json(_document(path, reports), sys.stderr)
            else:
                _write_reports(reports)
                print(f"error: {path}: the process memory limit was exceeded", file=sys.stderr)
            return EXIT_RUNTIME_ERROR

        if analysis.checked is None:
            reports = _reports(analysis)
            errors = sum(1 for diagnostic, _ in reports if diagnostic.severity == ERROR)
            if output_format == "json":
                _print_json(_document(path, reports), sys.stderr)
            else:
                _write_reports(reports)
                print(f"error: {path}: not run because of {_plural(errors)}", file=sys.stderr)
            return EXIT_INVALID_PROGRAM

        project_sources = {
            module.source.name: module.source
            for module in analysis.project.modules
        } if analysis.project else {source.name: source}
        source_by_key = {name.replace("\\", "/"): item for name, item in project_sources.items()}
        function_files = {
            id(function): module.source.name
            for module in analysis.project.modules if module.program
            for function in module.program.functions
        } if analysis.project else {}

        entry_key = source.name.replace("\\", "/")
        initial = set(breakpoints)
        if len(initial) > _DEBUG_MAX_BREAKPOINTS:
            print(f"error: at most {_DEBUG_MAX_BREAKPOINTS} breakpoints are allowed", file=sys.stderr)
            return EXIT_USAGE
        if any(line < 1 or line > len(source._lines) for line in initial):
            print("error: --breakpoint must name a line in the source file", file=sys.stderr)
            return EXIT_USAGE
        active_breakpoints = {entry_key: initial} if initial else {}

        input_bytes = 0

        def read_input() -> str:
            nonlocal input_bytes
            if max_input is None and max_text is None:
                line = sys.stdin.readline()
                if line == "":
                    raise EOFError("the standard input ended")
                return line.removesuffix("\n").removesuffix("\r")
            remaining = max_input - input_bytes if max_input is not None else None
            read_size = remaining + 1 if remaining is not None else None
            if max_text is not None:
                text_read_size = 4 * (max_text + 1) + 1
                read_size = text_read_size if read_size is None else min(read_size, text_read_size)
            raw = sys.stdin.buffer.readline(read_size)
            if raw == b"":
                raise EOFError("the standard input ended")
            if remaining is not None and len(raw) > remaining:
                raise _CliLimit("input", max_input)
            if max_input is not None:
                input_bytes += len(raw)
            encoding = sys.stdin.encoding or "utf-8"
            text = raw.decode(encoding, sys.stdin.errors or "strict").removesuffix("\n").removesuffix("\r")
            if max_text is not None and len(text) > max_text:
                raise TextLimitExceeded(max_text)
            return text

        host = LocalHost(
            arguments=arguments,
            read_line=read_input,
            grants=Grants(read=allow_read, write=allow_write, network=allow_network, process=allow_process),
            declarations=analysis.checked.capabilities,
            network_allowed=True,
            max_text=max_text,
            processes_allowed=True,
        )
        written = 0

        def write_output(text: str) -> None:
            nonlocal written
            if max_output is None:
                sys.stdout.write(text)
                sys.stdout.flush()
                return
            for start in range(0, len(text), 4096):
                chunk = text[start:start + 4096]
                data = chunk.encode("utf-8")
                room = max_output - written
                if len(data) > room:
                    prefix = data[:room].decode("utf-8", errors="ignore")
                    sys.stdout.write(prefix)
                    sys.stdout.flush()
                    written += len(prefix.encode("utf-8"))
                    raise _CliLimit("output", max_output)
                sys.stdout.write(chunk)
                sys.stdout.flush()
                written += len(data)

        if console is None:
            try:
                console = _open_debug_console()
            except OSError:
                print("error: nex debug needs a controlling terminal for its commands", file=sys.stderr)
                return EXIT_USAGE

        timer_remaining = [timeout]
        timer_active = [False]

        def pause_timer() -> None:
            if timeout is not None and timer_active[0]:
                remaining, _ = signal.getitimer(signal.ITIMER_REAL)
                timer_remaining[0] = remaining
                signal.setitimer(signal.ITIMER_REAL, 0)
                timer_active[0] = False

        def resume_timer() -> None:
            if timeout is None:
                return
            remaining = timer_remaining[0]
            if remaining is None or remaining <= 0:
                raise _CliLimit("time", timeout)
            signal.setitimer(signal.ITIMER_REAL, remaining)
            timer_active[0] = True

        mode = ["step"]
        stop_reason = [None]

        def show_event(event: DebugEvent) -> None:
            filename = (event.file or source.name).replace("\\", "/")
            current_source = source_by_key.get(filename)
            line_text = current_source.line_text(event.span.line) if current_source else ""
            print(f"\nPaused at {filename}:{event.span.line}:{event.span.column} in {event.function}",
                  file=sys.stderr)
            if line_text:
                print(f"  > {event.span.line}: {line_text}", file=sys.stderr)
            print("Call stack:", file=sys.stderr)
            for index, frame in enumerate(event.call_stack):
                frame_file = (frame.file or source.name).replace("\\", "/")
                frame_line = event.span.line if index == 0 or frame.call_site is None else frame.call_site.line
                print(f"  #{index} {frame.function} at {frame_file}:{frame_line}", file=sys.stderr)
            print("Variables:", file=sys.stderr)
            if event.variables:
                for name, value in event.variables:
                    print(f"  {name} = {format_debug_value(value)}", file=sys.stderr)
            else:
                print("  (none)", file=sys.stderr)
            points = sorted(active_breakpoints.get(filename, ()))
            print(f"Breakpoints in {filename}: {', '.join(map(str, points)) or '(none)'}", file=sys.stderr)

        def breakpoint_target(argument: str, current_file: str) -> tuple[str, int] | None:
            if ":" in argument:
                filename, number = argument.rsplit(":", 1)
                key = filename.replace("\\", "/")
            else:
                key, number = current_file, argument
            try:
                line = int(number)
            except ValueError:
                return None
            if key not in source_by_key or not 1 <= line <= len(source_by_key[key]._lines):
                return None
            return key, line

        def observe(event: DebugEvent) -> bool:
            if event.step > max_steps:
                stop_reason[0] = "limit"
                print(f"\nStopped: reached --max-steps ({max_steps}).", file=sys.stderr)
                return True
            current_file = (event.file or source.name).replace("\\", "/")
            if mode[0] == "continue" and event.span.line not in active_breakpoints.get(current_file, set()):
                return False

            pause_timer()
            show_event(event)
            while True:
                print("debug> ", end="", file=sys.stderr, flush=True)
                command_line = console.readline()
                if command_line == "":
                    stop_reason[0] = "stopped"
                    print("\nDebugger input closed; stopping the program.", file=sys.stderr)
                    return True
                stripped = command_line.strip()
                if not stripped:
                    mode[0] = "step"
                    resume_timer()
                    return False
                parts = stripped.split(None, 1)
                command = parts[0].lower()
                argument = parts[1].strip() if len(parts) == 2 else ""
                if command in {"s", "step"} and not argument:
                    mode[0] = "step"
                    resume_timer()
                    return False
                if command in {"c", "continue"} and not argument:
                    mode[0] = "continue"
                    resume_timer()
                    return False
                if command in {"q", "quit"} and not argument:
                    stop_reason[0] = "stopped"
                    print("Program stopped by the debugger.", file=sys.stderr)
                    return True
                if command in {"b", "break"} and argument:
                    target = breakpoint_target(argument, current_file)
                    if target is None:
                        print("Usage: break [FILE:]LINE; the file and line must exist in this program.",
                              file=sys.stderr)
                        continue
                    key, line = target
                    all_points = sum(len(points) for points in active_breakpoints.values())
                    points = active_breakpoints.setdefault(key, set())
                    if line not in points and all_points >= _DEBUG_MAX_BREAKPOINTS:
                        print(f"At most {_DEBUG_MAX_BREAKPOINTS} breakpoints are allowed.", file=sys.stderr)
                        continue
                    points.add(line)
                    print(f"Breakpoint set at {key}:{line}.", file=sys.stderr)
                    continue
                if command in {"d", "delete"} and argument:
                    target = breakpoint_target(argument, current_file)
                    if target is None:
                        print("Usage: delete [FILE:]LINE", file=sys.stderr)
                        continue
                    key, line = target
                    active_breakpoints.get(key, set()).discard(line)
                    print(f"Breakpoint cleared at {key}:{line}.", file=sys.stderr)
                    continue
                if command in {"b", "break", "breakpoints"} and not argument:
                    any_points = False
                    for filename, points in active_breakpoints.items():
                        for line in sorted(points):
                            print(f"  {filename}:{line}", file=sys.stderr)
                            any_points = True
                    if not any_points:
                        print("No breakpoints set.", file=sys.stderr)
                    continue
                if command in {"h", "help", "?"} and not argument:
                    print("Commands: step (s), continue (c), break [FILE:]LINE (b), "
                          "delete [FILE:]LINE (d), breakpoints, quit (q).", file=sys.stderr)
                    continue
                print("Unknown command. Type 'help' for the debugger commands.", file=sys.stderr)

        previous_handler = None
        try:
            if timeout is not None:
                def expire(*_):
                    raise _CliLimit("time", timeout)

                previous_handler = signal.signal(signal.SIGALRM, expire)
                resume_timer()
            stopped = run(
                analysis.checked,
                write_output,
                text_limit=max_text,
                host=host,
                debug_observer=observe,
                source_files=function_files,
            )
        except _CliLimit as error:
            sys.stdout.flush()
            return limit_failure(error, source)
        except NexoraRuntimeError as error:
            error_source = source_by_key.get((error.file or source.name).replace("\\", "/"), source)
            if error.diagnostic.category == CONTRACT:
                return fail(((error.diagnostic, error_source),), "the program stopped because a contract was broken",
                            EXIT_CONTRACT_VIOLATION)
            return fail(((error.diagnostic, error_source),), "the program stopped because of a runtime error",
                        EXIT_RUNTIME_ERROR)
        except MemoryError:
            if max_memory is None:
                raise
            diagnostic = Diagnostic("E3007", "Process memory limit exceeded while running the program")
            reports = ((diagnostic, source),)
            if output_format == "json":
                _print_json(_document(path, reports), sys.stderr)
            else:
                _write_reports(reports)
                print(f"error: {path}: the process memory limit was exceeded", file=sys.stderr)
            return EXIT_RUNTIME_ERROR
        finally:
            if timeout is not None and previous_handler is not None:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)

        sys.stdout.flush()
        if stopped is not None and stop_reason[0] == "limit":
            return EXIT_RUNTIME_ERROR
        if stopped is not None:
            return EXIT_OK
        print("\nProgram completed.", file=sys.stderr)
        return EXIT_OK
    finally:
        if close_console and console is not None:
            console.close()


class _CliLimit(Exception):
    def __init__(self, kind: str, limit: int | float, path: str | None = None) -> None:
        self.kind, self.limit, self.path = kind, limit, path


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _test(path: str, output_format: str, function: str | None,
          allow_read: tuple[str, ...] = (), allow_write: tuple[str, ...] = (),
          allow_network: tuple[str, ...] = (), allow_process: tuple[str, ...] = ()) -> int:
    """`nex test` (decision 0008). Nothing is written until every selected example was evaluated,
    so an internal error or Ctrl+C never leaves a partial report behind."""
    source, failure = _load(path)
    if source is None:
        analysis = Analysis(Source(path, ""), (failure,))
    else:
        analysis = analyze(source, require_main=False, read=_module_reader(source))
    host = LocalHost(
        grants=Grants(read=allow_read, write=allow_write, network=allow_network, process=allow_process),
        declarations=analysis.checked.capabilities if analysis.checked else Capabilities(),
        network_allowed=True,
        processes_allowed=True,
    )
    try:
        report = api.run_examples(analysis, function, host=host)
    except tooling.ToolingError as error:
        # A usage error, like any other: a message, no document.
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE

    if output_format == "json":
        _print_json(api.test_document(report), sys.stdout)
    else:
        _write_lines(_test_report_lines(report, path))

    if report.status == api.NOT_RUN:
        return EXIT_UNREADABLE_FILE if source is None else EXIT_INVALID_PROGRAM
    return EXIT_OK if report.status == api.PASSED else EXIT_TEST_FAILED


# Where a line of a text report goes.
_OUT, _ERR = "stdout", "stderr"


def _write_lines(lines: list[tuple[str, str]]) -> None:
    """Writes a text report that is already complete, each line to its stream, in order. stdout is
    flushed before anything goes to stderr, so a terminal shows them in that order."""
    for stream, line in lines:
        if stream == _ERR:
            sys.stdout.flush()
        print(line, file=sys.stdout if stream == _OUT else sys.stderr)


def _test_report_lines(report: api.TestReport, path: str) -> list[tuple[str, str]]:
    """The text report of `nex test`, line by line: the summary for stdout, the diagnostics for stderr.
    It is built whole before anything is written, like the JSON document, so a failure while building
    it (an internal error, running out of memory) leaves no partial report behind (decision 0008, 3.4)."""
    lines: list[tuple[str, str]] = []
    source = report.analysis.source
    if report.status == api.NOT_RUN:
        for diagnostic, file in _reports(report.analysis):
            lines += [(_ERR, render(diagnostic, file)), (_ERR, "")]
        if source.text or report.analysis.diagnostics[0].category != "file":
            errors = sum(1 for diagnostic in report.analysis.diagnostics if diagnostic.severity == ERROR)
            lines.append((_ERR, f"error: {path}: not tested because of {_plural(errors)}"))
        else:
            lines.append((_ERR, f"error: {path}: the file could not be read"))
        return lines
    if report.status == api.NO_EXAMPLES:
        return [(_OUT, f"{path}: no examples to run"), (_ERR, f"error: {path}: nothing was tested")]

    results = report.results
    functions: dict[str, list] = {}
    for result in results:
        functions.setdefault(result.function, []).append(result)
    if report.function is not None:
        lines.append((_OUT, f"{path}: {_count(len(results), 'example')} of '{report.function}'"))
    else:
        lines.append((_OUT, f"{path}: {_count(len(results), 'example')} in {_count(len(functions), 'function')}"))
    width = max(len(name) for name in functions)
    for name, own in functions.items():
        counts = [f"{sum(r.status == status for r in own)} {status}"
                  for status in (api.PASSED, api.FAILED, api.ERROR) if any(r.status == status for r in own)]
        lines.append((_OUT, f"  {name.ljust(width)}   {', '.join(counts)}"))

    for result in results:
        if result.status == api.PASSED:
            continue
        lines += [(_ERR, ""), (_ERR, render(result.diagnostic, source))]
        if result.output:
            lines.append((_ERR, f"\noutput of example {result.index} of '{result.function}':"))
            lines += [(_ERR, f"    {line}") for line in result.output.rstrip("\n").split("\n")]

    summary = api.summary_of(report)
    if report.status == api.PASSED:
        lines.append((_OUT, f"✓ {_count(summary['total'], 'example')} passed: {path}"))
    else:
        not_passed = summary["failed"] + summary["error"]
        lines += [(_ERR, ""), (_ERR, f"error: {path}: {not_passed} of {_count(summary['total'], 'example')} "
                                     f"did not pass ({summary['failed']} failed, {_count(summary['error'], 'error')})")]
    return lines


def _use_utf8() -> None:
    """Program output and diagnostics are always UTF-8, whatever the console's code page."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


def _output_was_closed(error: Exception) -> bool:
    """True if writing failed because the reader of our output went away.
    Unix reports a broken pipe; Windows reports 'invalid argument' for the same situation."""
    return isinstance(error, BrokenPipeError) or (isinstance(error, OSError) and error.errno == errno.EINVAL)


def _discard_output() -> None:
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        pass


def _flush_quietly() -> None:
    try:
        sys.stdout.flush()
    except OSError:
        pass


# nex migrate (decision 0019, section 8)

_VERIFIED = "structure verified; text outside the edits verified; behaviour not checked by this command"


def _migrate(path: str, write: bool, files: migrate_files.Files | None = None) -> int:
    """`nex migrate`: the routes of 8.2, the checks of 8.3 and, with `write`, the writing of G7.

    Every file is read through `files` (8.9.2), once, and kept in memory: both front ends analyse
    those bytes, and the writer reads them again before replacing anything (G7). The tests give
    their own `files`; nothing else can.
    """
    from .legacy011 import diagnostics as diagnostics011
    from .legacy011 import pipeline as pipeline011

    files = files or migrate_files.Files()
    if not path.endswith(".nex"):
        print(f"error: nex migrate only migrates .nex files, not {path}", file=sys.stderr)
        return EXIT_USAGE

    read: dict[str, bytes] = {}       # the bytes of each file, as first read: key -> bytes

    def read_bytes_once(file: Path | str) -> bytes:
        # The program is known by the path it was given; a module, by its resolved path. A module
        # that cannot be read, or is not UTF-8, is E0001 or E0002 of the analysis, as in every
        # command: code 4 is only for the file the command was given (8.7.1, "as for every command").
        key = file if isinstance(file, str) else str(file)
        if key not in read:
            read[key] = files.read(key)
        return read[key]

    try:
        text, _ = migrate_files.decode(read_bytes_once(path))
    except OSError as error:
        _report((Diagnostic("E0001", f"{error.strerror or type(error).__name__}: {path}"),), Source(path, ""))
        return EXIT_UNREADABLE_FILE
    except UnicodeDecodeError:
        _report((Diagnostic("E0002", f"{path} must be saved as UTF-8 text"),), Source(path, ""))
        return EXIT_UNREADABLE_FILE

    entry011 = diagnostics011.Source(path, text)
    old = pipeline011.analyze(entry011, require_main=False, read=_module_reader(
        entry011, diagnostics011.Source, diagnostics011.Diagnostic, read_bytes_once))
    entry012 = Source(path, text)
    new = analyze(entry012, require_main=False, read=_module_reader(entry012, read_bytes=read_bytes_once))

    if not old.ok and new.ok:
        print(f"{path}: the program is already written in the syntax of 0.12; nothing to migrate")
        return EXIT_OK
    if not old.ok:
        return _migrate_refused_both(path, old, new, diagnostics011)
    if new.ok:
        return _migrate_nothing(path, old, new)
    return _migrate_files(path, old, read, write, files)


def _migrate_modules(analysis) -> list:
    """The modules of a program, in the order of their paths (G6, G7). The program is known by
    the path it was given and a module by its resolved path, so both are resolved to be ordered."""
    return sorted(analysis.project.modules, key=lambda module: _real_path(module.path))


def _real_path(key: str) -> str:
    return str(Path(key).resolve())


def _migrate_refused_both(path: str, old, new, diagnostics011) -> int:
    """8.2: a program that is neither a program of 0.11 nor one of 0.12, and why (8.2.1)."""
    from .lexer import tokenize

    print(f"error: {path}: this program passes neither the check of 0.11 nor the check of 0.12; "
          "nothing was written", file=sys.stderr)
    for module in _migrate_modules(new):
        tokens, lexical = tokenize(module.source)
        found = "it has lexical errors" if lexical else migrate.describe_markers(*migrate.markers(tokens))
        print(f"  {module.source.name}: {found}", file=sys.stderr)
    print("\nWith the front end of 0.11:\n", file=sys.stderr)
    for diagnostic, source in old.project.reports():
        print(diagnostics011.render(diagnostic, source), file=sys.stderr)
        print(file=sys.stderr)
    print("With the front end of 0.12:\n", file=sys.stderr)
    _write_reports(new.project.reports())
    return EXIT_INVALID_PROGRAM


def _migrate_nothing(path: str, old, new) -> int:
    """8.2.2: both checks pass, so no file has a function. The two safety checks still run."""
    trees = {module.path: module.program for module in new.project.modules}
    refusals = []
    for module in _migrate_modules(old):
        plan = migrate.plan(module.source.text, module.tokens, module.program)
        if module.program.functions or plan.edits:
            # Premise 3 of 8.2.2 is broken: a defect of NEXORA, not of the program.
            print(f"internal error: {module.source.name} passes both checks and has something to migrate. "
                  "This is a bug in NEXORA; nothing was written.", file=sys.stderr)
            return EXIT_INTERNAL_ERROR
        refusals += [(module.source.name, refusal) for refusal in plan.refusals]
        if not refusals and not migrate.equivalent(module.program, trees[module.path]):
            print(f"error: {module.source.name}: 0.11 and 0.12 read this file differently; "
                  "nothing was written", file=sys.stderr)
            return EXIT_INVALID_PROGRAM
    if refusals:
        return _migrate_refusals(path, refusals)
    print(f"{path}: nothing to migrate: the program reads the same in 0.11 and in 0.12")
    return EXIT_OK


def _migrate_refusals(path: str, refusals) -> int:
    """G5 and 8.6: every reason, with its file and position; nothing is written."""
    for shown, refusal in refusals:
        print(f"{shown}:{refusal.line}:{refusal.column}: {refusal.message}", file=sys.stderr)
    print(f"error: {path}: nex migrate cannot decide {len(refusals)} "
          f"{'case' if len(refusals) == 1 else 'cases'} for you; nothing was written", file=sys.stderr)
    return EXIT_INVALID_PROGRAM


def _migrate_files(path: str, old, read: dict[str, bytes], write: bool, files: migrate_files.Files) -> int:
    """The route "migrate": the edits of every file (8.5), G2, G4 and G3, and then G7 or the text."""
    modules = _migrate_modules(old)
    plans, refusals = {}, []
    for module in modules:
        plan = migrate.plan(module.source.text, module.tokens, module.program)
        plans[module.path] = plan
        refusals += [(module.source.name, refusal) for refusal in plan.refusals]
    if refusals:
        return _migrate_refusals(path, refusals)

    outputs = {}
    for module in modules:
        output = migrate.apply(module.source.text, plans[module.path].edits)
        if not migrate.kept_outside(module.source.text, plans[module.path].edits, output):
            return _migrate_defect(module.source.name, "a character outside the edits changed (G2)")
        outputs[module.path] = output

    # G4: the migrated program, read from memory, passes the check of 0.12.
    def migrated_bytes(file: Path) -> bytes:
        key = str(file)
        return migrate_files.encode(outputs[key], read[key].startswith(migrate_files.BOM))

    entry = Source(path, outputs[path])
    checked = analyze(entry, require_main=False, read=_module_reader(entry, read_bytes=migrated_bytes))
    if not checked.ok:
        _write_reports(checked.project.reports())
        return _migrate_defect(path, "the migrated program does not pass the check of 0.12 (G4)")
    # G3: every file has the structure it had.
    trees = {module.path: module.program for module in checked.project.modules}
    for module in modules:
        if not migrate.equivalent(module.program, trees[module.path]):
            return _migrate_defect(module.source.name, "the migrated file is not structurally equivalent (G3)")

    shown = {_real_path(module.path): module.source.name for module in modules}
    if not write:
        for module in modules:
            edits = plans[module.path].edits
            if not edits:
                continue
            print(f"--- {module.source.name}: {len(edits)} {'edit' if len(edits) == 1 else 'edits'}")
            for edit in edits:
                line, column = _position(module.source.text, edit.start)
                before = module.source.text[edit.start:edit.end]
                print(f"  {line}:{column}  {edit.kind}  {before!r} -> {edit.text!r}")
            print(f"--- {module.source.name}: migrated text")
            sys.stdout.write(outputs[module.path])
            if not outputs[module.path].endswith(("\n", "\r")):
                print()
        print(_VERIFIED)
        print("Nothing was written. Run it again with --write to replace the files.")
        return EXIT_OK

    planned = [migrate_files.Planned(_real_path(module.path), read[module.path],
                                     migrate_files.encode(outputs[module.path],
                                                          read[module.path].startswith(migrate_files.BOM)))
               for module in modules]
    report = migrate_files.write_all(planned, files)
    if report.changed:
        for key in report.changed:
            print(f"{shown[key]}: This file changed while it was being migrated: run nex migrate again",
                  file=sys.stderr)
        print(f"error: {path}: nothing was written", file=sys.stderr)
        return EXIT_INVALID_PROGRAM
    for key in report.replaced:
        print(f"replaced: {shown[key]}")
    if report.ok:
        if not report.replaced:
            print(f"{path}: no file needed an edit")
        print(_VERIFIED)
        return EXIT_OK
    sys.stdout.flush()
    if report.failed is None:
        # Interrupted between two files: none of them failed.
        print(f"error: {path}: interrupted; the files already replaced stay replaced", file=sys.stderr)
    else:
        what = "was interrupted" if report.interrupted else "could not be written"
        print(f"error: {path}: {shown[report.failed[0]]} {what}; the files already replaced stay replaced",
              file=sys.stderr)
    print(f"  replaced: {', '.join(shown[key] for key in report.replaced) or '(none)'}", file=sys.stderr)
    if report.failed is not None:
        print(f"  failed: {shown[report.failed[0]]} ({report.failed[1]})", file=sys.stderr)
    print(f"  not written: {', '.join(shown[key] for key in report.not_written) or '(none)'}", file=sys.stderr)
    if report.left is not None:
        temporary, error = report.left
        print(f"  left behind: {os.path.basename(temporary)}, a temporary file that could not be removed "
              f"({error}); it does not end in .nex, so no program reads it", file=sys.stderr)
    return EXIT_INTERRUPTED if report.interrupted else EXIT_UNREADABLE_FILE


def _migrate_defect(shown: str, what: str) -> int:
    """Code 70 (8.7.1): a check that the edits are designed to pass did not pass."""
    print(f"internal error: {shown}: {what}. This is a bug in NEXORA; nothing was written.", file=sys.stderr)
    return EXIT_INTERNAL_ERROR


def _position(text: str, offset: int) -> tuple[int, int]:
    """The line and column of an offset, with the line endings the lexer reads."""
    line, start, index = 1, 0, 0
    while index < offset:
        character = text[index]
        if character == "\r" or character == "\n":
            if character == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                index += 1
            line, start = line + 1, index + 1
        index += 1
    return line, offset - start + 1


def main(argv: list[str] | None = None) -> int:
    """Entry point of `nex`. Returns the process exit code."""
    _use_utf8()
    parser = _build_parser()
    cli_argv = list(sys.argv[1:] if argv is None else argv)
    program_args: list[str] | None = None
    if cli_argv and cli_argv[0] in {"run", "debug"} and "--" in cli_argv:
        separator = cli_argv.index("--")
        # A separator after the file introduces program arguments. Before the file,
        # argparse needs it to accept a filename that starts with a dash.
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                parser.parse_args(cli_argv[:separator])
        except SystemExit:
            pass
        else:
            program_args = cli_argv[separator + 1:]
            cli_argv = cli_argv[:separator]
    try:
        arguments = parser.parse_args(cli_argv)
        if program_args is not None:
            arguments.args = program_args
    except SystemExit as exit_request:
        # argparse exits by itself for --help, --version (0) and for usage errors (2).
        return exit_request.code if isinstance(exit_request.code, int) else EXIT_USAGE

    if arguments.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        if arguments.command == "run":
            return _run(arguments.file, arguments.format, tuple(arguments.args),
                        tuple(arguments.allow_read), tuple(arguments.allow_write),
                        tuple(arguments.allow_network), tuple(arguments.allow_process),
                        arguments.timeout, arguments.max_output, arguments.max_text, arguments.max_source,
                        arguments.max_memory, arguments.max_input)
        if arguments.command == "debug":
            return _debug(arguments.file, arguments.format, tuple(arguments.args),
                          tuple(arguments.breakpoint), arguments.max_steps,
                          tuple(arguments.allow_read), tuple(arguments.allow_write),
                          tuple(arguments.allow_network), tuple(arguments.allow_process),
                          arguments.timeout, arguments.max_output, arguments.max_text, arguments.max_source,
                          arguments.max_memory, arguments.max_input)
        if arguments.command == "inspect":
            return _analysis_command(arguments.file, "json", tooling.inspect_document)
        if arguments.command == "context":
            return _analysis_command(arguments.file, arguments.format, tooling.context_document,
                                     tooling.render_context)
        if arguments.command == "test":
            return _test(arguments.file, arguments.format, arguments.function,
                         tuple(arguments.allow_read), tuple(arguments.allow_write),
                         tuple(arguments.allow_network), tuple(arguments.allow_process))
        if arguments.command == "migrate":
            return _migrate(arguments.file, arguments.write)
        if arguments.command == "symbols":
            return _analysis_command(
                arguments.file, arguments.format,
                lambda analysis: tooling.symbols_document(analysis, name=arguments.name, function=arguments.function),
                tooling.render_symbols,
            )
        return _check(arguments.file, arguments.format, arguments.evidence)
    except KeyboardInterrupt:
        _flush_quietly()
        print(f"\ninterrupted: {arguments.file}", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as error:  # last line of defence, see below
        if _output_was_closed(error):
            # Whoever was reading the output stopped (`nex run file.nex | head -1`). Not an error.
            # Output is pointed at the null device so that Python's exit does not complain.
            _discard_output()
            return EXIT_OK
        # Anything that reaches this point is a defect in NEXORA, not in the user's program,
        # and is reported as such. NEXORA_DEBUG=1 shows the Python traceback for investigation.
        if os.environ.get("NEXORA_DEBUG"):
            raise
        sys.stdout.flush()
        print(
            f"internal error: NEXORA hit an unexpected problem ({type(error).__name__}: {error}).\n"
            "This is a bug in NEXORA, not in your program. "
            "Run the command again with the environment variable NEXORA_DEBUG=1 to see the details.",
            file=sys.stderr,
        )
        return EXIT_INTERNAL_ERROR

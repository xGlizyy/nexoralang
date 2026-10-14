"""The `nex` command-line interface."""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
from pathlib import Path

from . import api, tooling
from .diagnostics import CONTRACT, MAX_DIAGNOSTICS, Diagnostic, NexoraRuntimeError, Source, render
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
EXIT_INTERNAL_ERROR = 70     # a bug in NEXORA itself (and, inherited from nex run, MemoryError)
EXIT_INTERRUPTED = 130       # stopped by the user with Ctrl+C

_EPILOG = """\
exit codes:
  0   success
  1   the program has lexical, syntax, semantic or type errors
  2   wrong command-line usage
  3   the program failed while running
  4   the file could not be read
  5   the program broke a rule it declares while running: a contract
      ('requires', 'ensures') or the condition of a refined type
  6   nex test: an example did not pass, or there was no example to run
  70  internal error in NEXORA (a bug, please report it); also when a
      program runs out of memory
  130 interrupted with Ctrl+C
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nex",
        description="NEXORA: run, check and analyse programs written in the NEXORA language.",
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
    run_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how to report errors (default: text). 'json' writes one JSON document to standard error "
             "if the program is invalid or fails; the program's own output is not affected",
    )

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
    test_parser.add_argument("--function", help="only the examples declared in this function")
    return parser


def _load(path: str) -> tuple[Source | None, Diagnostic | None]:
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        reason = error.strerror or type(error).__name__
        return None, Diagnostic("E0001", f"{reason}: {path}")
    try:
        # utf-8-sig also accepts files that start with a byte-order mark.
        return Source(path, data.decode("utf-8-sig")), None
    except UnicodeDecodeError:
        return None, Diagnostic("E0002", f"{path} must be saved as UTF-8 text")


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


def _check(path: str, output_format: str) -> int:
    source, failure = _load(path)
    if source is None:
        diagnostics, code = (failure,), EXIT_UNREADABLE_FILE
        source = Source(path, "")
    else:
        diagnostics = analyze(source).diagnostics
        code = EXIT_INVALID_PROGRAM if diagnostics else EXIT_OK

    if output_format == "json":
        _print_json(tooling.diagnostics_document(path, diagnostics), sys.stdout)
    elif diagnostics:
        _report(diagnostics, source)
        print(f"error: {path}: check failed with {_plural(len(diagnostics))}", file=sys.stderr)
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

    analysis = analyze(source)
    document = build(analysis)
    if output_format == "json":
        _print_json(document, sys.stdout)
    else:
        print(render_text(document))
    return EXIT_OK if analysis.ok else EXIT_INVALID_PROGRAM


def _run(path: str, output_format: str) -> int:
    def fail(diagnostics, source: Source, summary: str, code: int) -> int:
        # Whatever the program printed before failing is shown first.
        sys.stdout.flush()
        if output_format == "json":
            _print_json(tooling.diagnostics_document(path, diagnostics), sys.stderr)
        else:
            _report(diagnostics, source)
            print(f"error: {path}: {summary}", file=sys.stderr)
        return code

    source, failure = _load(path)
    if source is None:
        return fail((failure,), Source(path, ""), "the file could not be read", EXIT_UNREADABLE_FILE)

    analysis = analyze(source)
    if analysis.checked is None:
        summary = f"not run because of {_plural(len(analysis.diagnostics))}"
        return fail(analysis.diagnostics, source, summary, EXIT_INVALID_PROGRAM)

    try:
        run(analysis.checked, sys.stdout.write)
    except NexoraRuntimeError as error:
        if error.diagnostic.category == CONTRACT:
            return fail((error.diagnostic,), source, "the program stopped because a contract was broken",
                        EXIT_CONTRACT_VIOLATION)
        return fail((error.diagnostic,), source, "the program stopped because of a runtime error",
                    EXIT_RUNTIME_ERROR)
    # Flushed here, not at interpreter exit, so that a closed pipe is handled by main().
    sys.stdout.flush()
    return EXIT_OK


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _test(path: str, output_format: str, function: str | None) -> int:
    """`nex test` (decision 0008). Nothing is written until every selected example was evaluated,
    so an internal error or Ctrl+C never leaves a partial report behind."""
    source, failure = _load(path)
    if source is None:
        analysis = Analysis(Source(path, ""), (failure,))
    else:
        analysis = analyze(source, require_main=False)
    try:
        report = api.run_examples(analysis, function)
    except tooling.ToolingError as error:
        # A usage error, like any other: a message, no document.
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE

    if output_format == "json":
        _print_json(api.test_document(report), sys.stdout)
    else:
        _report_test(report, path)

    if report.status == api.NOT_RUN:
        return EXIT_UNREADABLE_FILE if source is None else EXIT_INVALID_PROGRAM
    return EXIT_OK if report.status == api.PASSED else EXIT_TEST_FAILED


def _report_test(report: api.TestReport, path: str) -> None:
    source = report.analysis.source
    if report.status == api.NOT_RUN:
        _report(report.analysis.diagnostics, source)
        if source.text or report.analysis.diagnostics[0].category != "file":
            print(f"error: {path}: not tested because of {_plural(len(report.analysis.diagnostics))}", file=sys.stderr)
        else:
            print(f"error: {path}: the file could not be read", file=sys.stderr)
        return
    if report.status == api.NO_EXAMPLES:
        print(f"{path}: no examples to run")
        print(f"error: {path}: nothing was tested", file=sys.stderr)
        return

    results = report.results
    functions: dict[str, list] = {}
    for result in results:
        functions.setdefault(result.function, []).append(result)
    if report.function is not None:
        print(f"{path}: {_count(len(results), 'example')} of '{report.function}'")
    else:
        print(f"{path}: {_count(len(results), 'example')} in {_count(len(functions), 'function')}")
    width = max(len(name) for name in functions)
    for name, own in functions.items():
        counts = [f"{sum(r.status == status for r in own)} {status}"
                  for status in (api.PASSED, api.FAILED, api.ERROR) if any(r.status == status for r in own)]
        print(f"  {name.ljust(width)}   {', '.join(counts)}")
    sys.stdout.flush()

    for result in results:
        if result.status == api.PASSED:
            continue
        print(file=sys.stderr)
        print(render(result.diagnostic, source), file=sys.stderr)
        if result.output:
            print(f"\noutput of example {result.index} of '{result.function}':", file=sys.stderr)
            for line in result.output.rstrip("\n").split("\n"):
                print(f"    {line}", file=sys.stderr)

    summary = api.summary_of(report)
    if report.status == api.PASSED:
        print(f"✓ {_count(summary['total'], 'example')} passed: {path}")
    else:
        not_passed = summary["failed"] + summary["error"]
        print(file=sys.stderr)
        print(f"error: {path}: {not_passed} of {_count(summary['total'], 'example')} did not pass "
              f"({summary['failed']} failed, {_count(summary['error'], 'error')})", file=sys.stderr)


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


def main(argv: list[str] | None = None) -> int:
    """Entry point of `nex`. Returns the process exit code."""
    _use_utf8()
    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exit_request:
        # argparse exits by itself for --help, --version (0) and for usage errors (2).
        return exit_request.code if isinstance(exit_request.code, int) else EXIT_USAGE

    if arguments.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        if arguments.command == "run":
            return _run(arguments.file, arguments.format)
        if arguments.command == "inspect":
            return _analysis_command(arguments.file, "json", tooling.inspect_document)
        if arguments.command == "context":
            return _analysis_command(arguments.file, arguments.format, tooling.context_document,
                                     tooling.render_context)
        if arguments.command == "test":
            return _test(arguments.file, arguments.format, arguments.function)
        if arguments.command == "symbols":
            return _analysis_command(
                arguments.file, arguments.format,
                lambda analysis: tooling.symbols_document(analysis, name=arguments.name, function=arguments.function),
                tooling.render_symbols,
            )
        return _check(arguments.file, arguments.format)
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

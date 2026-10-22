"""Reusable entry points: check or run NEXORA source code held in memory.

This is the interface for programs that embed NEXORA (the web playground, for one).
It goes through exactly the same stages as the `nex` command: `pipeline.analyze`
for the static analysis and `interpreter.run` for the execution. There is no second
implementation of the language behind it.

`check_source` and `run_source` return a plain dictionary, ready for `json.dumps`, with this
shape (schema `nexora.result/1`, documented in docs/playground.md):

    {
      "schema": "nexora.result/1",
      "action": "check" | "run",
      "status": "success" | "invalid" | "runtime_error" | "contract_violation"
                | "output_limit" | "memory_limit",
      "output": "<what the program printed>",
      "diagnostics": [ <diagnostics, as in nexora.diagnostics/1> ],
      "message": null | "<explanation of a status that is not a diagnostic>"
    }

`test_source` evaluates the `example` clauses of a program and returns a `nexora.test/1`
document, the same one `nex test --format json` writes (decision 0008).

Nothing here reads or writes files: `filename` is only the name shown in diagnostics.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, replace

from . import ast_nodes as ast
from . import tooling
from .capabilities import Host
from .checker import BUILTINS, KNOWN_TYPES, own_calls
from .diagnostics import CONTRACT, MAX_DIAGNOSTICS, Diagnostic, NexoraRuntimeError, Source
from .interpreter import MAX_CALL_DEPTH, ExampleRun, run, run_example
from .pipeline import Analysis, analyze
from .tokens import KEYWORDS, RESERVED_WORDS
from .types import LIST, OPTION, RESULT
from .values import show_value
from .version import __version__

RESULT_SCHEMA = "nexora.result/1"
TEST_SCHEMA = "nexora.test/1"
DEFAULT_FILENAME = "playground.nex"

# Every value "status" can take in a result.
SUCCESS = "success"                         # check: no errors. run: the program finished
INVALID = "invalid"                         # static errors: the program was not started
RUNTIME_ERROR = "runtime_error"             # the program started and failed
CONTRACT_VIOLATION = "contract_violation"   # a contract or a refined type was broken while running
OUTPUT_LIMIT = "output_limit"               # the program printed more than the host allows
MEMORY_LIMIT = "memory_limit"               # the program needed more memory than the host allows


@dataclass(frozen=True)
class Limits:
    """Limits a host can impose on one execution. None means no limit (what `nex run` uses)."""

    # Bytes of UTF-8 output. Past it the program is stopped and the status is "output_limit".
    output_bytes: int | None = None
    # Characters of a Text value built with '+'. Past it the program fails with E3006.
    text_chars: int | None = None


class _OutputLimitReached(Exception):
    """Raised by the output collector to stop a program that printed too much."""


class _Output:
    def __init__(self, limit: int | None) -> None:
        self._limit = limit
        self._size = 0
        self._parts: list[str] = []

    def write(self, text: str) -> None:
        if self._limit is None:
            self._parts.append(text)
            return
        data = text.encode("utf-8")
        room = self._limit - self._size
        if len(data) > room:
            # Keep what fits, without cutting a character in half.
            self._parts.append(data[:max(room, 0)].decode("utf-8", errors="ignore"))
            self._size = self._limit
            raise _OutputLimitReached
        self._parts.append(text)
        self._size += len(data)

    def text(self) -> str:
        return "".join(self._parts)


def _result(action: str, status: str, filename: str, diagnostics=(), output: str = "",
            message: str | None = None) -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "action": action,
        "status": status,
        "output": output,
        "diagnostics": [diagnostic.to_dict(filename) for diagnostic in diagnostics],
        "message": message,
    }


def check_source(source: str, filename: str = DEFAULT_FILENAME) -> dict:
    """Analyses a program without running it: syntax, names, types and return paths."""
    analysis = analyze(Source(filename, source))
    return _result("check", SUCCESS if analysis.ok else INVALID, filename, analysis.diagnostics)


NO_LIMITS = Limits()
_MEMORY_MESSAGE = "The program needed more memory than this environment allows and was stopped."


def run_source(source: str, filename: str = DEFAULT_FILENAME, *, limits: Limits = NO_LIMITS,
               host: Host | None = None) -> dict:
    """Analyses a program and, if it has no static errors, runs it and collects its output.

    A program with static errors is never started: the status is "invalid" and the output empty.
    If the program fails while running, "output" holds what it had printed until then.

    `host` is what the program may do besides computing: its arguments, its input and the
    files it may touch. Without one, the program can only compute and print (decision 0015).
    """
    analysis = analyze(Source(filename, source))
    if analysis.checked is None:
        return _result("run", INVALID, filename, analysis.diagnostics)

    output = _Output(limits.output_bytes)
    try:
        run(analysis.checked, output.write, text_limit=limits.text_chars, host=host)
    except NexoraRuntimeError as error:
        if error.diagnostic.code == "E3007":
            # Out of memory while running: the same status as below, now with its diagnostic (decision 0009).
            return _result("run", MEMORY_LIMIT, filename, (error.diagnostic,), output.text(), _MEMORY_MESSAGE)
        status = CONTRACT_VIOLATION if error.diagnostic.category == CONTRACT else RUNTIME_ERROR
        return _result("run", status, filename, (error.diagnostic,), output.text())
    except _OutputLimitReached:
        return _result(
            "run", OUTPUT_LIMIT, filename, output=output.text(),
            message=f"The program printed more than {limits.output_bytes} bytes and was stopped.",
        )
    except MemoryError:
        # Memory that ran out outside the interpreter, or while building E3007 (decision 0009, 3.5).
        return _result("run", MEMORY_LIMIT, filename, output=output.text(), message=_MEMORY_MESSAGE)
    return _result("run", SUCCESS, filename, output=output.text())


# Testing: the `example` clauses (decision 0008)

# The global status of a test run, and of each example.
PASSED = "passed"            # at least one example was evaluated, and all passed
FAILED = "failed"            # some example ended in "failed" or "error" (global); the example is false (one)
NO_EXAMPLES = "no_examples"  # the analysis is clean, but no example was selected
NOT_RUN = "not_run"          # static errors, or an unreadable file: nothing was evaluated
ERROR = "error"              # an example whose evaluation stopped with a runtime error or a broken rule


@dataclass(frozen=True)
class ExampleResult:
    """The outcome of one example, with everything a report shows about it."""

    function: str
    index: int                       # its position among the examples of its function, from 1
    example: ast.Example
    status: str                      # PASSED, FAILED or ERROR
    values: tuple[dict, ...]         # the own calls that were invoked, in order of invocation
    not_evaluated: tuple[dict, ...]  # the own calls that were never invoked, in the order of the text
    diagnostic: Diagnostic | None    # None if passed; E4004 if failed; the original one, with a note, if error
    output: str


@dataclass(frozen=True)
class TestReport:
    """Everything `nex test` and `test_source` know once all the selected examples were evaluated."""

    analysis: Analysis
    function: str | None             # the --function filter, if any
    status: str                      # PASSED, FAILED, NO_EXAMPLES or NOT_RUN
    results: tuple[ExampleResult, ...] | None   # None when NOT_RUN

    __test__ = False                 # not a pytest test class, despite its name


def run_examples(analysis: Analysis, function: str | None = None, host: Host | None = None) -> TestReport:
    """Evaluates the examples of an analysed program, each in a new interpreter, in the order of
    the file. `analysis` should come from `analyze(source, require_main=False)`.

    Raises tooling.ToolingError("unknown_function") if `function` names no function of a program
    without static errors. Running out of memory during an example is a diagnostic of the program,
    E3007 (decision 0009). Any exception that is not a diagnostic of the program propagates: a
    defect of NEXORA or KeyboardInterrupt (decision 0008, 3.4). Since the report is built only at
    the end, such an exception never leaves a partial report behind."""
    checked = analysis.checked
    if checked is None:
        return TestReport(analysis, function, NOT_RUN, None)
    # The functions of the file that runs are the ones with examples to evaluate: an example
    # of an imported module belongs to the text of that other file, whose spans this report
    # cannot show (decision 0018). A module is tested by passing it instead of the program.
    own = {declared.name for declared in checked.program.functions}
    if function is not None and function not in own:
        close = difflib.get_close_matches(function, sorted(own), n=1)
        suggestion = f". Did you mean '{close[0]}'?" if close else ""
        raise tooling.ToolingError(
            "unknown_function", f"{analysis.source.name} has no function named '{function}'{suggestion}",
        )

    results = []
    for declared in checked.program.functions:
        if function is not None and declared.name != function:
            continue
        for index, example in enumerate(declared.examples, start=1):
            calls = own_calls(example, declared.name)
            results.append(_example_result(analysis, declared.name, index, example, calls,
                                            run_example(checked, example, calls, host)))

    if not results:
        status = NO_EXAMPLES
    elif all(result.status == PASSED for result in results):
        status = PASSED
    else:
        status = FAILED
    return TestReport(analysis, function, status, tuple(results))


def _example_result(analysis: Analysis, function: str, index: int, example: ast.Example,
                    calls: list[ast.Call], run: ExampleRun) -> ExampleResult:
    source = analysis.source
    values = tuple(
        {
            "call": source.text_of(record.node.span),
            "span": ast.to_dict(record.node.span),
            "type": analysis.types.get(id(record.node)),
            "status": record.status,
            "value": show_value(record.value) if record.status == "returned" else None,
        }
        for record in run.invoked
    )
    invoked = {id(record.node) for record in run.invoked}
    not_evaluated = tuple(
        {
            "call": source.text_of(call.span),
            "span": ast.to_dict(call.span),
            "type": analysis.types.get(id(call)),
            "reason": "short_circuit" if id(call) in run.short_circuited else "stopped_before",
        }
        for call in calls if id(call) not in invoked
    )

    if run.error is not None:
        note = f"While evaluating example {index} of '{function}', at line {example.condition.span.line}."
        diagnostic = replace(run.error, notes=(*run.error.notes, note))
        status = ERROR
    elif run.value:
        diagnostic, status = None, PASSED
    else:
        notes = [f"{value['call']} returned {value['value']}" for value in values]
        if example.message is not None:
            notes.append(f"Reason: {example.message}")
        diagnostic = Diagnostic("E4004", f"This example of '{function}' is false", example.condition.span,
                                notes=tuple(notes))
        status = FAILED
    return ExampleResult(function, index, example, status, values, not_evaluated, diagnostic, run.output)


def summary_of(report: TestReport) -> dict | None:
    if report.results is None:
        return None
    counts = {"total": len(report.results), PASSED: 0, FAILED: 0, ERROR: 0}
    for result in report.results:
        counts[result.status] += 1
    return counts


def test_document(report: TestReport) -> dict:
    """The `nexora.test/1` document of a report. `ok` and `diagnostics` keep their meaning in every
    format: the result of the static analysis. `status` says what happened to the examples."""
    analysis = report.analysis
    name = analysis.source.name
    document = tooling.diagnostics_document(name, analysis.diagnostics)
    document["schema"] = TEST_SCHEMA
    document["status"] = report.status
    document["filter"] = {"function": report.function}
    document["summary"] = summary_of(report)
    document["examples"] = None if report.results is None else [
        {
            "function": result.function,
            "index": result.index,
            "span": ast.to_dict(result.example.condition.span),
            "expression": analysis.source.text_of(result.example.condition.span),
            "message": result.example.message,
            "status": result.status,
            "values": list(result.values),
            "not_evaluated": list(result.not_evaluated),
            "diagnostic": None if result.diagnostic is None else result.diagnostic.to_dict(name),
            "output": result.output,
        }
        for result in report.results
    ]
    return document


test_document.__test__ = False   # not a pytest test, despite its name


def test_source(source: str, filename: str = DEFAULT_FILENAME, *, function: str | None = None) -> dict:
    """Analyses a program and evaluates its `example` clauses; returns a `nexora.test/1` document.

    The analysis does not require 'main', and 'main' is never run. `function` keeps only the
    examples declared in that function; the functions they call still check their contracts. A
    function that does not exist raises tooling.ToolingError("unknown_function"). An example that
    runs out of memory ends in "error" with E3007, and the next ones are evaluated (decision 0009).
    An internal error is not turned into a document: the exception reaches the caller, and so does
    a MemoryError outside the evaluation of an example."""
    analysis = analyze(Source(filename, source), require_main=False)
    return test_document(run_examples(analysis, function))


test_source.__test__ = False     # not a pytest test, despite its name


def language_info() -> dict:
    """Facts about this version of the language, for tools that present it (an editor, for one).
    Taken from the implementation itself, so they cannot drift from it."""
    return {
        "version": __version__,
        "keywords": sorted(KEYWORDS),
        "reserved_words": sorted(RESERVED_WORDS),
        "types": [*KNOWN_TYPES, LIST.name, OPTION.name, RESULT.name],
        "builtins": sorted(BUILTINS),
        "limits": {
            "max_call_depth": MAX_CALL_DEPTH,
            "max_diagnostics": MAX_DIAGNOSTICS,
        },
    }

"""Reusable entry points: check or run NEXORA source code held in memory.

This is the interface for programs that embed NEXORA (the web playground, for one).
It goes through exactly the same stages as the `nex` command: `pipeline.analyze`
for the static analysis and `interpreter.run` for the execution. There is no second
implementation of the language behind it.

Both functions return a plain dictionary, ready for `json.dumps`, with this shape
(schema `nexora.result/1`, documented in docs/playground.md):

    {
      "schema": "nexora.result/1",
      "action": "check" | "run",
      "status": "success" | "invalid" | "runtime_error" | "contract_violation"
                | "output_limit" | "memory_limit",
      "output": "<what the program printed>",
      "diagnostics": [ <diagnostics, as in nexora.diagnostics/1> ],
      "message": null | "<explanation of a status that is not a diagnostic>"
    }

Nothing here reads or writes files: `filename` is only the name shown in diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checker import BUILTINS, KNOWN_TYPES
from .diagnostics import CONTRACT, MAX_DIAGNOSTICS, NexoraRuntimeError, Source
from .interpreter import MAX_CALL_DEPTH, run
from .pipeline import analyze
from .tokens import KEYWORDS, RESERVED_WORDS
from .version import __version__

RESULT_SCHEMA = "nexora.result/1"
DEFAULT_FILENAME = "playground.nex"

# Every value "status" can take in a result.
SUCCESS = "success"                         # check: no errors. run: the program finished
INVALID = "invalid"                         # static errors: the program was not started
RUNTIME_ERROR = "runtime_error"             # the program started and failed
CONTRACT_VIOLATION = "contract_violation"   # a 'requires' or 'ensures' condition was false
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


def run_source(source: str, filename: str = DEFAULT_FILENAME, *, limits: Limits = NO_LIMITS) -> dict:
    """Analyses a program and, if it has no static errors, runs it and collects its output.

    A program with static errors is never started: the status is "invalid" and the output empty.
    If the program fails while running, "output" holds what it had printed until then.
    """
    analysis = analyze(Source(filename, source))
    if analysis.checked is None:
        return _result("run", INVALID, filename, analysis.diagnostics)

    output = _Output(limits.output_bytes)
    try:
        run(analysis.checked, output.write, text_limit=limits.text_chars)
    except NexoraRuntimeError as error:
        status = CONTRACT_VIOLATION if error.diagnostic.category == CONTRACT else RUNTIME_ERROR
        return _result("run", status, filename, (error.diagnostic,), output.text())
    except _OutputLimitReached:
        return _result(
            "run", OUTPUT_LIMIT, filename, output=output.text(),
            message=f"The program printed more than {limits.output_bytes} bytes and was stopped.",
        )
    except MemoryError:
        return _result(
            "run", MEMORY_LIMIT, filename, output=output.text(),
            message="The program needed more memory than this environment allows and was stopped.",
        )
    return _result("run", SUCCESS, filename, output=output.text())


def language_info() -> dict:
    """Facts about this version of the language, for tools that present it (an editor, for one).
    Taken from the implementation itself, so they cannot drift from it."""
    return {
        "version": __version__,
        "keywords": sorted(KEYWORDS),
        "reserved_words": sorted(RESERVED_WORDS),
        "types": list(KNOWN_TYPES),
        "builtins": sorted(BUILTINS),
        "limits": {
            "max_call_depth": MAX_CALL_DEPTH,
            "max_diagnostics": MAX_DIAGNOSTICS,
        },
    }

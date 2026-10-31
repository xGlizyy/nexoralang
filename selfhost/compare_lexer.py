"""Differential check: the NEXORA lexer (selfhost/lexer.nex) against the Python one.

    python selfhost/compare_lexer.py FILE.nex [FILE.nex ...]

For every file both lexers run on the same text and their tokens (kind, lexeme, span, and the
decoded value of text literals) and lexical errors (code, label, hint, span) are compared. Exit
status 1 when any file differs. This is a test tool for the self-hosted work of decision 0025; it
is not part of the language.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nexora.diagnostics import Source
from nexora.lexer import tokenize

HERE = Path(__file__).resolve().parent


def python_lines(path: Path) -> list[str]:
    tokens, diagnostics = tokenize(Source(path.name, path.read_text(encoding="utf-8")))
    lines = []
    for token in tokens:
        span = token.span
        value = token.value if token.type.value == "text" else ""
        lines.append(f"T|{token.type.value}|{token.lexeme}|{value}|"
                     f"{span.line}:{span.column}-{span.end_line}:{span.end_column}")
    for diagnostic in diagnostics:
        span = diagnostic.span
        lines.append(f"D|{diagnostic.code}|{diagnostic.label}|{diagnostic.hint or ''}|"
                     f"{span.line}:{span.column}-{span.end_line}:{span.end_column}")
    return lines


def nexora_lines(path: Path) -> list[str]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", str(HERE / "lexer.nex"), "--allow-read", ".",
         "--max-output", "100000000", "--", str(path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return [f"RUN FAILED ({run.returncode}): {run.stdout[-300:]} {run.stderr[-600:]}"]
    lines = []
    for line in run.stdout.split("\n")[:-1]:
        parts = line.split("|")
        # Only text literals have a value to compare; numbers carry their digits in the NEXORA lexer.
        if parts[0] == "T" and parts[1] != "text":
            parts[3] = ""
        lines.append("|".join(parts))
    return lines


def main(paths: list[str]) -> int:
    failures = 0
    for name in paths:
        path = Path(name)
        expected, actual = python_lines(path), nexora_lines(path)
        if expected == actual:
            print(f"ok    {name} ({len(expected)} lines)")
            continue
        failures += 1
        print(f"DIFF  {name}")
        for index, (want, got) in enumerate(zip(expected, actual)):
            if want != got:
                print(f"  line {index + 1}\n    python: {want!r}\n    nexora: {got!r}")
                break
        else:
            print(f"  python has {len(expected)} lines, nexora has {len(actual)}")
            tail = (expected if len(expected) > len(actual) else actual)[min(len(expected), len(actual)):][:2]
            print(f"  first extra: {tail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

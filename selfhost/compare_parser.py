"""Differential check: the NEXORA parser (selfhost/parser.nex) against the Python one.

    python selfhost/compare_parser.py CASES.txt [CASES.txt ...]

A cases file has one expression per line. Lines starting with '#types' or '#records' add names the
program would declare (a record name is also a type name). Both parsers read every expression and
their result is compared: the tree as JSON when it parses, or the first syntax error (code, message,
hint, notes, span) when it does not. A line with a lexical error is skipped: the lexer is checked
on its own (compare_lexer.py). Exit status 1 when any line differs.

This is a test tool for the self-hosted work of decision 0025; it is not part of the language.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nexora import ast_nodes as ast
from nexora.diagnostics import Source
from nexora.lexer import tokenize
from nexora.parser import _BUILTIN_TYPE_NAMES, ParseError, Parser

HERE = Path(__file__).resolve().parent


def python_results(lines: list[str]) -> dict[int, str]:
    type_names = set(_BUILTIN_TYPE_NAMES)
    record_names: set[str] = set()
    results: dict[int, str] = {}
    for number, line in enumerate(lines, start=1):
        if line.startswith("#types"):
            type_names |= set(line.split()[1:])
        elif line.startswith("#records"):
            names = set(line.split()[1:])
            type_names |= names
            record_names |= names
        elif line:
            tokens, diagnostics = tokenize(Source("case", line))
            if diagnostics:
                results[number] = "SKIP"
                continue
            parser = Parser(tokens, frozenset(type_names), frozenset(record_names))
            try:
                expression = parser._expression()
            except ParseError as error:
                d = error.diagnostic
                s = d.span
                results[number] = (f"ERR|{d.code}|{d.label}|{d.hint or ''}|{'~~'.join(d.notes)}|"
                                   f"{s.line}:{s.column}-{s.end_line}:{s.end_column}")
                continue
            if not parser._check(__import__("nexora.tokens", fromlist=["TokenType"]).TokenType.EOF):
                results[number] = "TRAILING"
            else:
                results[number] = "OK|" + json.dumps(ast.to_dict(expression), ensure_ascii=False)
    return results


def nexora_results(path: Path) -> dict[int, str]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", str(HERE / "parser.nex"), "--allow-read", ".",
         "--max-output", "100000000", "--", str(path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return {0: f"RUN FAILED ({run.returncode}): {run.stdout[-400:]} {run.stderr[-800:]}"}
    results: dict[int, str] = {}
    for line in run.stdout.split("\n")[:-1]:
        number, _, rest = line.partition("|")
        results[int(number)] = rest
    return results


def same(expected: str, actual: str) -> bool:
    if expected.startswith("OK|") and actual.startswith("OK|"):
        return json.loads(expected[3:]) == json.loads(actual[3:])
    return expected == actual


def main(paths: list[str]) -> int:
    failures = 0
    for name in paths:
        path = Path(name)
        lines = path.read_text(encoding="utf-8").split("\n")
        expected = python_results(lines)
        actual = nexora_results(path)
        if 0 in actual:
            print(f"DIFF  {name}\n  {actual[0]}")
            failures += 1
            continue
        bad = [n for n in expected if not same(expected[n], actual.get(n, "<missing>"))]
        if not bad:
            print(f"ok    {name} ({len(expected)} expressions)")
            continue
        failures += 1
        print(f"DIFF  {name}: {len(bad)} of {len(expected)} differ")
        for n in bad[:5]:
            print(f"  line {n}: {lines[n - 1]!r}\n    python: {expected[n][:300]}\n    nexora: {actual.get(n, '<missing>')[:300]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

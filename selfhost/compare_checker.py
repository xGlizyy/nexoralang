"""Differential check: the NEXORA checker (selfhost/checker.nex) against the Python one.

    python selfhost/compare_checker.py FILE.nex [FILE.nex ...]

For every file that has no lexical or syntax errors, both checkers read the program. The tree with the
type of every expression (what `nex inspect` shows), the errors and the warnings are compared. A program that uses something the NEXORA
checker does not know yet is reported as unsupported by it, and skipped. Exit status 1 when any
checked file differs.

The files go to the NEXORA checker in batches, to pay the start-up of the interpreter once per batch.

This is a test tool for the self-hosted work of decision 0024; it is not part of the language.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from compare_programs import first_difference, same

from nexora import ast_nodes as ast
from nexora.checker import check
from nexora.diagnostics import ERROR, Source
from nexora.lexer import tokenize
from nexora.parser import parse

HERE = Path(__file__).resolve().parent
BATCH = 6


def python_result(path: Path) -> list[str]:
    tokens, lexical = tokenize(Source(path.name, path.read_text(encoding="utf-8")))
    if lexical:
        return ["SKIP|lexical"]
    program, syntax = parse(tokens)
    if syntax:
        return ["SKIP|syntax"]
    checked, diagnostics = check(program)
    lines = ["CHECKED|" + json.dumps(ast.to_dict(program, checked.types), ensure_ascii=False)]
    errors = [d for d in diagnostics if d.severity == ERROR][:100]
    for d in errors + [d for d in diagnostics if d.severity != ERROR]:
        s = d.span
        where = "" if s is None else f"{s.line}:{s.column}-{s.end_line}:{s.end_column}"
        lines.append(f"D|{d.code}|{d.label}|{d.hint or ''}|{'~~'.join(d.notes)}|{where}")
    return lines


def nexora_results(paths: list[Path]) -> dict[str, list[str]]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "checker.nex").as_posix(), "--allow-read", ".",
         "--max-output", "1000000000", "--", "--check", *[p.as_posix() for p in paths]],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return {"": [f"RUN FAILED ({run.returncode}): {run.stdout[-300:]} {run.stderr[-900:]}"]}
    results: dict[str, list[str]] = {}
    current = ""
    for line in run.stdout.split("\n")[:-1]:
        if line.startswith("FILE|"):
            current = line[5:]
            results[current] = []
        else:
            results[current].append(line)
    return results


def same_checked(expected: list[str], actual: list[str]) -> bool:
    expected = [line.replace("CHECKED|", "PROGRAM|", 1) for line in expected]
    actual = [line.replace("CHECKED|", "PROGRAM|", 1) for line in actual]
    return same(expected, actual)


def main(names: list[str]) -> int:
    paths = [Path(name) for name in names]
    failures = skipped = unsupported = checked_ok = 0
    reasons: dict[str, int] = {}
    for start in range(0, len(paths), BATCH):
        batch = paths[start:start + BATCH]
        actual = nexora_results(batch)
        if "" in actual:
            print(f"DIFF  batch starting at {batch[0]}\n  {actual[''][0]}")
            failures += len(batch)
            continue
        for path in batch:
            got = actual.get(path.as_posix(), ["<missing>"])
            if got[0].startswith("UNSUPPORTED|"):
                unsupported += 1
                reason = got[0].split("|", 1)[1]
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            expected = python_result(path)
            if got[0].startswith("SKIP|") or expected[0].startswith("SKIP|"):
                skipped += 1
                continue
            if same_checked(expected, got):
                checked_ok += 1
                print(f"ok    {path} ({len(expected) - 1} errors)")
            else:
                failures += 1
                diff = first_difference(
                    [line.replace("CHECKED|", "PROGRAM|", 1) for line in expected],
                    [line.replace("CHECKED|", "PROGRAM|", 1) for line in got],
                )
                print(f"DIFF  {path}\n  {diff}")
    print(f"{checked_ok} ok, {failures} different, {unsupported} unsupported, {skipped} skipped")
    if reasons:
        print("unsupported because of:", ", ".join(f"{k} ({v})" for k, v in sorted(reasons.items(), key=lambda i: -i[1])))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

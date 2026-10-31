"""Differential check: whole programs, NEXORA parser against the Python one.

    python selfhost/compare_programs.py FILE.nex [FILE.nex ...]

For every file both parsers read the program. Their tree (as JSON) and their syntax errors (code,
message, hint, notes, span) are compared. A file with lexical errors is skipped: the lexer is checked
on its own (compare_lexer.py). Exit status 1 when any file differs.

The files go to the NEXORA parser in batches, to pay the start-up of the interpreter once per batch.

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
from nexora.parser import parse

HERE = Path(__file__).resolve().parent
BATCH = 8


def python_result(path: Path) -> list[str]:
    tokens, lexical = tokenize(Source(path.name, path.read_text(encoding="utf-8")))
    if lexical:
        return ["SKIP"]
    program, diagnostics = parse(tokens)
    lines = ["PROGRAM|" + json.dumps(ast.to_dict(program), ensure_ascii=False)]
    for d in diagnostics:
        s = d.span
        lines.append(f"D|{d.code}|{d.label}|{d.hint or ''}|{'~~'.join(d.notes)}|"
                     f"{s.line}:{s.column}-{s.end_line}:{s.end_column}")
    return lines


def nexora_results(paths: list[Path]) -> dict[str, list[str]]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "parser.nex").as_posix(), "--allow-read", ".",
         "--max-output", "1000000000", "--", "--program", *[p.as_posix() for p in paths]],
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


def same(expected: list[str], actual: list[str]) -> bool:
    if len(expected) != len(actual):
        return False
    for want, got in zip(expected, actual):
        if want.startswith("PROGRAM|") and got.startswith("PROGRAM|"):
            if json.loads(want[8:]) != json.loads(got[8:]):
                return False
        elif want != got:
            return False
    return True


def first_difference(expected: list[str], actual: list[str]) -> str:
    for index, (want, got) in enumerate(zip(expected, actual)):
        if want.startswith("PROGRAM|") and got.startswith("PROGRAM|"):
            a, b = json.loads(want[8:]), json.loads(got[8:])
            if a != b:
                return "tree differs: " + where_differs(a, b)
        elif want != got:
            return f"line {index + 1}\n    python: {want[:400]}\n    nexora: {got[:400]}"
    return f"python has {len(expected)} lines, nexora has {len(actual)}"


def where_differs(a, b, path: str = "") -> str:
    if type(a) is not type(b):
        return f"{path}: {a!r:.120} vs {b!r:.120}"
    if isinstance(a, dict):
        for key in a:
            if key not in b:
                return f"{path}.{key} missing in nexora"
            if a[key] != b[key]:
                return where_differs(a[key], b[key], f"{path}.{key}")
        for key in b:
            if key not in a:
                return f"{path}.{key} extra in nexora"
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items vs {len(b)}"
        for index, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return where_differs(x, y, f"{path}[{index}]")
    return f"{path}: {a!r:.120} vs {b!r:.120}"


def main(names: list[str]) -> int:
    paths = [Path(name) for name in names]
    failures = 0
    skipped = 0
    for start in range(0, len(paths), BATCH):
        batch = paths[start:start + BATCH]
        actual = nexora_results(batch)
        if "" in actual:
            print(f"DIFF  batch starting at {batch[0]}\n  {actual[''][0]}")
            failures += len(batch)
            continue
        for path in batch:
            expected = python_result(path)
            got = actual.get(path.as_posix(), ["<missing>"])
            if expected == ["SKIP"]:
                skipped += 1
                print(f"skip  {path}")
            elif same(expected, got):
                print(f"ok    {path} ({len(expected) - 1} errors)")
            else:
                failures += 1
                print(f"DIFF  {path}\n  {first_difference(expected, got)}")
    print(f"{len(paths) - failures - skipped} ok, {skipped} skipped, {failures} different")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

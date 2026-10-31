"""Differential check of a project of modules: selfhost/project.nex against the Python loader and checker.

    python selfhost/compare_project.py MAIN.nex [MAIN.nex ...]

Each file is the program that runs; the modules it imports are read from beside it. For each project both implementations
give the modules in the order they are checked, the diagnostics of each one and the typed tree of the program that runs, and
they are compared. A project that uses something the NEXORA checker does not know yet is skipped and counted.

This is a test tool for the self-hosted work of decision 0024; it is not part of the language.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from compare_programs import first_difference, same

from nexora import ast_nodes as ast
from nexora.cli import _module_reader
from nexora.diagnostics import ERROR, Source
from nexora.modules import load

HERE = Path(__file__).resolve().parent
BATCH = 4


def python_result(path: Path) -> list[str]:
    source = Source(path.as_posix(), path.read_text(encoding="utf-8"))
    project = load(source, read=_module_reader(source))
    if any(module.program is None or not module.complete for module in project.modules):
        return ["SKIP|syntax"]
    lines = []
    for module in project.modules:
        lines.append(f"MODULE|{module.name}")
        ordered = [d for d in module.diagnostics if d.severity == ERROR][:100]
        ordered += [d for d in module.diagnostics if d.severity != ERROR]
        for d in ordered:
            s = d.span
            where = "" if s is None else f"{s.line}:{s.column}-{s.end_line}:{s.end_column}"
            lines.append(f"D|{d.code}|{d.label}|{d.hint or ''}|{'~~'.join(d.notes)}|{where}")
    entry = project.entry
    lines.append("CHECKED|" + json.dumps(ast.to_dict(entry.program, project.types), ensure_ascii=False))
    return lines


def nexora_results(paths: list[Path]) -> dict[str, list[str]]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "project.nex").as_posix(), "--allow-read", ".",
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


def _as_program(lines: list[str]) -> list[str]:
    return [line.replace("CHECKED|", "PROGRAM|", 1) for line in lines]


def main(names: list[str]) -> int:
    paths = [Path(name) for name in names]
    failures = skipped = unsupported = ok = 0
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
                print(f"skip  {path} (unsupported: {reason})")
                continue
            expected = python_result(path)
            if got[0].startswith("SKIP|") or expected[0].startswith("SKIP|"):
                skipped += 1
                continue
            # The tree is compared as data (compare_programs.same reads a PROGRAM| line as JSON), not as text.
            if same(_as_program(expected), _as_program(got)):
                ok += 1
                print(f"ok    {path} ({sum(1 for line in expected if line.startswith('D|'))} diagnostics)")
            else:
                failures += 1
                print(f"DIFF  {path}\n  {first_difference(expected, got)}")
    print(f"{ok} ok, {failures} different, {unsupported} unsupported, {skipped} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

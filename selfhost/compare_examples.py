"""Differential check: the `example` clauses, run by the NEXORA interpreter and by `nex test`.

    python selfhost/compare_examples.py FILE.nex [FILE.nex ...]

For every program with examples, `nex test --format json` (the Python interpreter) and the interpreter written
in NEXORA (selfhost/interpreter.nex --test) evaluate them, and for each example the two are compared: its
status, the own calls that were evaluated with their type and value, the ones that were not and why, the
diagnostic and what it printed. A program without examples, or that `nex test` does not run because of a static
error, is skipped, and so is one the NEXORA checker does not know yet. Exit status 1 when one differs.

This is a test tool for the self-hosted work of decision 0024; it is not part of the language.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = 4


def where(span: dict) -> str:
    return f"{span['line']}:{span['column']}-{span['end_line']}:{span['end_column']}"


def python_lines(path: Path) -> list[str] | None:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "test", path.as_posix(), "--format", "json"],
        capture_output=True, text=True, encoding="utf-8", input="",
    )
    try:
        document = json.loads(run.stdout)
    except json.JSONDecodeError:
        return None
    if document.get("examples") is None or not document["examples"]:
        return None
    lines: list[str] = []
    for example in document["examples"]:
        lines.append(f"EX|{example['function']}|{example['index']}|{example['status']}|{where(example['span'])}|"
                     f"{example['expression']}|{example['message'] or ''}")
        for value in example["values"]:
            lines.append(f"VAL|{value['call']}|{where(value['span'])}|{value['type'] or ''}|{value['status']}|"
                         f"{value['value'] or ''}")
        for value in example["not_evaluated"]:
            lines.append(f"NOT|{value['call']}|{where(value['span'])}|{value['type'] or ''}|{value['reason']}")
        diagnostic = example["diagnostic"]
        if diagnostic is not None:
            span = f"{diagnostic['line']}:{diagnostic['column']}-{diagnostic['end_line']}:{diagnostic['end_column']}"
            lines.append(f"DIAG|{diagnostic['code']}|{diagnostic['label']}|{diagnostic['hint'] or ''}|"
                         f"{'~~'.join(diagnostic['notes'])}|{span}")
        lines.extend(f"OUT|{line}" for line in example["output"].split("\n")[:-1])
    return lines


def nexora_lines(paths: list[Path]) -> dict[str, tuple[str, list[str]]]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "interpreter.nex").as_posix(), "--allow-read", ".",
         "--max-output", "1000000000", "--", "--test", *[p.as_posix() for p in paths]],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return {"": (f"RUN FAILED ({run.returncode}): {run.stdout[-300:]} {run.stderr[-900:]}", [])}
    results: dict[str, tuple[str, list[str]]] = {}
    current = ""
    lines: list[str] = []
    for line in run.stdout.split("\n")[:-1]:
        if line.startswith("FILE|"):
            current, lines = line[5:], []
        elif line.startswith("STOP|"):
            results[current] = (line[5:], lines)
        else:
            lines.append(line)
    return results


def main(names: list[str]) -> int:
    paths = [Path(name) for name in names]
    same = different = skipped = 0
    for start in range(0, len(paths), BATCH):
        batch = paths[start:start + BATCH]
        runs = nexora_lines(batch)
        if "" in runs:
            print(f"DIFF  batch starting at {batch[0]}\n  {runs[''][0]}")
            different += len(batch)
            continue
        for path in batch:
            expected = python_lines(path)
            stop, actual = runs.get(path.as_posix(), ("missing", []))
            if expected is None:
                skipped += 1
                print(f"skip  {path} (no examples to run)")
            elif stop != "ok":
                skipped += 1
                print(f"skip  {path} (NEXORA: {stop})")
            elif expected == actual:
                same += 1
                print(f"ok    {path} ({sum(1 for line in expected if line.startswith('EX|'))} examples)")
            else:
                different += 1
                for index in range(max(len(expected), len(actual))):
                    a = expected[index] if index < len(expected) else "<missing>"
                    b = actual[index] if index < len(actual) else "<missing>"
                    if a != b:
                        print(f"DIFF  {path}\n  line {index + 1}\n    python: {a!r}\n    nexora: {b!r}")
                        break
    print(f"{same} equal, {different} different, {skipped} skipped")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

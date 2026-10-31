"""Differential check: the NEXORA interpreter (selfhost/interpreter.nex) against the Python one.

    python selfhost/compare_interpreter.py FILE.nex [FILE.nex ...]

Every program is run by `nex run` (the Python interpreter) and by the interpreter written in NEXORA, and
what they print is compared. Only the programs that `nex run` runs to the end (exit code 0) are compared: the
NEXORA interpreter does not format the errors of a run yet. A program the NEXORA checker does not know yet,
or that needs the host (files, input, network, processes), is reported and skipped. Exit status 1 when a
compared program differs.

The files go to the NEXORA interpreter in batches, to pay the start-up of the interpreter once per batch.

This is a test tool for the self-hosted work of decision 0024; it is not part of the language.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = 4


def python_run(path: Path) -> tuple[int, str]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", path.as_posix()],
        capture_output=True, text=True, encoding="utf-8", input="",
    )
    return run.returncode, run.stdout


def nexora_runs(paths: list[Path]) -> dict[str, tuple[str, str]]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "interpreter.nex").as_posix(), "--allow-read", ".",
         "--max-output", "1000000000", "--", *[p.as_posix() for p in paths]],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return {"": (f"RUN FAILED ({run.returncode}): {run.stdout[-300:]} {run.stderr[-900:]}", "")}
    results: dict[str, tuple[str, str]] = {}
    current = ""
    lines: list[str] = []
    for line in run.stdout.split("\n")[:-1]:
        if line.startswith("FILE|"):
            current = line[5:]
            lines = []
        elif line.startswith("STOP|"):
            results[current] = (line[5:], "".join(item + "\n" for item in lines))
        else:
            lines.append(line)
    return results


def main(names: list[str]) -> int:
    paths = [Path(name) for name in names]
    same = different = skipped = 0
    for start in range(0, len(paths), BATCH):
        batch = paths[start:start + BATCH]
        runs = nexora_runs(batch)
        if "" in runs:
            print(f"DIFF  batch starting at {batch[0]}\n  {runs[''][0]}")
            different += len(batch)
            continue
        for path in batch:
            code, expected = python_run(path)
            stop, actual = runs.get(path.as_posix(), ("missing", ""))
            if code != 0:
                skipped += 1
                print(f"skip  {path} (nex run exits with {code})")
            elif not stop.startswith("ok"):
                skipped += 1
                print(f"skip  {path} (NEXORA: {stop})")
            elif expected == actual:
                same += 1
                print(f"ok    {path} ({len(expected.splitlines())} lines, {stop.split()[1]} steps)")
            else:
                different += 1
                want, got = expected.splitlines(), actual.splitlines()
                for index in range(max(len(want), len(got))):
                    a = want[index] if index < len(want) else "<missing>"
                    b = got[index] if index < len(got) else "<missing>"
                    if a != b:
                        print(f"DIFF  {path}\n  line {index + 1}\n    python: {a!r}\n    nexora: {b!r}")
                        break
    print(f"{same} equal, {different} different, {skipped} skipped")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

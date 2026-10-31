"""Differential check: the NEXORA interpreter (selfhost/interpreter.nex) against the Python one.

    python selfhost/compare_interpreter.py FILE.nex [FILE.nex ...]

Every program is run by `nex run` (the Python interpreter) and by the interpreter written in NEXORA, and
the two are compared: what the program prints and, when it stops with a runtime error or a broken contract,
the diagnostic (code, message, hint, notes and position). A program that `nex run` rejects before running it
is skipped, and so is one the NEXORA checker does not know yet or that needs the host (files, input, network,
processes). Exit status 1 when a compared program differs.

The files go to the NEXORA interpreter in batches, to pay the start-up of the interpreter once per batch.

This is a test tool for the self-hosted work of decision 0025; it is not part of the language.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = 4


def python_run(path: Path) -> tuple[int, str, dict | None]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", path.as_posix(), "--format", "json"],
        capture_output=True, text=True, encoding="utf-8", input="",
    )
    diagnostic = None
    if run.returncode in (3, 5):
        diagnostic = json.loads(run.stderr)["diagnostics"][0]
    return run.returncode, run.stdout, diagnostic


def nexora_runs(paths: list[Path]) -> dict[str, dict]:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "interpreter.nex").as_posix(), "--allow-read", ".",
         "--max-output", "1000000000", "--", *[p.as_posix() for p in paths]],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return {"": {"stop": f"RUN FAILED ({run.returncode}): {run.stdout[-300:]} {run.stderr[-900:]}"}}
    results: dict[str, dict] = {}
    current = ""
    lines: list[str] = []
    fail: str | None = None
    for line in run.stdout.split("\n")[:-1]:
        if line.startswith("FILE|"):
            current, lines, fail = line[5:], [], None
        elif line.startswith("FAIL|"):
            fail = line
        elif line.startswith("STOP|"):
            stop = line[5:]
            results[current] = {
                "stop": stop.split(" ")[0], "steps": stop.split(" ")[1] if stop.startswith("ok") else "",
                "reason": stop, "output": "".join(item + "\n" for item in lines), "fail": fail,
            }
        else:
            lines.append(line)
    return results


def parse_fail(line: str) -> dict:
    _, code, label, hint, notes, where = line.split("|", 5)
    return {"code": code, "label": label, "hint": hint, "notes": notes.split("~~") if notes else [], "where": where}


def expected_fail(diagnostic: dict) -> dict:
    where = f"{diagnostic['line']}:{diagnostic['column']}-{diagnostic['end_line']}:{diagnostic['end_column']}"
    return {"code": diagnostic["code"], "label": diagnostic["label"], "hint": diagnostic["hint"] or "",
            "notes": diagnostic["notes"], "where": where}


def first_difference(want: dict, got: dict) -> str:
    for key in ("code", "label", "hint", "where"):
        if want[key] != got[key]:
            return f"{key}\n    python: {want[key]!r}\n    nexora: {got[key]!r}"
    for index in range(max(len(want["notes"]), len(got["notes"]))):
        a = want["notes"][index] if index < len(want["notes"]) else "<missing>"
        b = got["notes"][index] if index < len(got["notes"]) else "<missing>"
        if a != b:
            return f"note {index + 1}\n    python: {a!r}\n    nexora: {b!r}"
    return "?"


def main(names: list[str]) -> int:
    paths = [Path(name) for name in names]
    same = different = skipped = 0
    for start in range(0, len(paths), BATCH):
        batch = paths[start:start + BATCH]
        runs = nexora_runs(batch)
        if "" in runs:
            print(f"DIFF  batch starting at {batch[0]}\n  {runs[''].get('stop')}")
            different += len(batch)
            continue
        for path in batch:
            code, expected, diagnostic = python_run(path)
            run = runs.get(path.as_posix(), {"stop": "missing", "reason": "missing"})
            if code not in (0, 3, 5):
                skipped += 1
                print(f"skip  {path} (nex run exits with {code})")
            elif run["stop"] not in ("ok", "fail") or (run["fail"] or "").startswith("FAIL|E0000|"):
                skipped += 1
                print(f"skip  {path} (NEXORA: {run['reason']})")
            elif (code == 0) != (run["stop"] == "ok"):
                different += 1
                print(f"DIFF  {path}\n  nex run exits with {code}, NEXORA stops with {run['reason']}")
            elif expected != run["output"]:
                different += 1
                want, got = expected.splitlines(), run["output"].splitlines()
                for index in range(max(len(want), len(got))):
                    a = want[index] if index < len(want) else "<missing>"
                    b = got[index] if index < len(got) else "<missing>"
                    if a != b:
                        print(f"DIFF  {path}\n  output line {index + 1}\n    python: {a!r}\n    nexora: {b!r}")
                        break
            elif code != 0 and expected_fail(diagnostic) != parse_fail(run["fail"]):
                different += 1
                print(f"DIFF  {path}\n  diagnostic: {first_difference(expected_fail(diagnostic), parse_fail(run['fail']))}")
            else:
                same += 1
                how = f"{run['steps']} steps" if code == 0 else f"fails with {diagnostic['code']}"
                print(f"ok    {path} ({len(expected.splitlines())} lines, {how})")
    print(f"{same} equal, {different} different, {skipped} skipped")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

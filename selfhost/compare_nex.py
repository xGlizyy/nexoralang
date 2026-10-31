"""Differential check of the command written in NEXORA (selfhost/nex.nex) against `nex`.

    python selfhost/compare_nex.py check FILE.nex [...]
    python selfhost/compare_nex.py run FILE.nex [...]
    python selfhost/compare_nex.py test FILE.nex [...]

Each file is given to the same command in both implementations and the text they write is compared: everything `nex` writes
to the standard output and to the standard error, in order, against everything nex.nex writes to its standard output. The exit
status is not compared, because a NEXORA program has none to set.

This is a test tool for the self-hosted work of decision 0025; it is not part of the language.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def command_python(command: str, path: str) -> str:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", command, path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, input=b"",
    )
    return run.stdout.decode("utf-8").replace("\r\n", "\n")


def command_nexora(command: str, path: str) -> str:
    native = os.environ.get("NEXORA_NEX")
    if native:
        # nex.nex compiled to an executable by selfhost/cgen.nex: no Python in the way.
        run = subprocess.run(
            [native, "--allow-read", ".", "--allow-write", ".", "--", command, path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, input=b"",
        )
        return run.stdout.decode("utf-8").replace("\r\n", "\n")
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "nex.nex").as_posix(), "--allow-read", ".", "--allow-write", ".",
         "--max-output", "1000000000", "--", command, path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, input=b"",
    )
    return run.stdout.decode("utf-8").replace("\r\n", "\n")


def main(arguments: list[str]) -> int:
    command, paths = arguments[0], arguments[1:]
    same = different = 0
    for path in paths:
        posix = Path(path).as_posix()
        expected = command_python(command, posix)
        actual = command_nexora(command, posix)
        if expected == actual:
            same += 1
            print(f"ok    {posix}")
        else:
            different += 1
            want, got = expected.split("\n"), actual.split("\n")
            index = next((i for i in range(min(len(want), len(got))) if want[i] != got[i]), min(len(want), len(got)))
            print(f"DIFF  {posix}  (line {index + 1})")
            print(f"  nex:     {want[index] if index < len(want) else '<end>'!r}")
            print(f"  nex.nex: {got[index] if index < len(got) else '<end>'!r}")
    print(f"{same} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

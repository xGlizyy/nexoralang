"""Builds the NEXORA compiler (selfhost/cgen.nex) as an executable, and shows that it compiles itself (decision 0026, stage 6).

    NEXORA_CC="cc" PYTHONPATH=nexora/src python selfhost/bootstrap.py [--seed seed.c]

    1. generation 0: Python runs cgen.nex on its own source and writes C        (minutes; skipped with --seed)
    2. the C compiler turns that C into an executable, the first compiler
    3. generation 1: that executable compiles cgen.nex and writes C             (no Python)
    4. the C of generation 1 is the same text as the C of generation 0           (the fixed point; from a seed that is
       older than the source, generation 1 is the new seed and the fixed point is generation 2 against generation 1)
    5. the C compiler turns it into the second compiler, which has to give the same C again

`--seed` starts from a C file written before (the one of a previous run, or one kept in a repository), so the build needs a C
compiler and nothing else. Everything is written under selfhost/build/.

This is a test and build tool for the self-hosted work of decision 0026; it is not part of the language.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
SOURCE = (HERE / "cgen.nex").relative_to(HERE.parent).as_posix()


def step(title: str, command: list[str]) -> float:
    started = time.time()
    done = subprocess.run(command, capture_output=True)
    seconds = time.time() - started
    if done.returncode != 0:
        sys.exit(f"{title} failed ({done.returncode}):\n{(done.stdout + done.stderr).decode('utf-8', 'replace')[-1500:]}")
    print(f"{title}: {seconds:6.1f} s")
    return seconds


def main(arguments: list[str]) -> int:
    compiler = shlex.split(os.environ.get("NEXORA_CC", "cc"))
    BUILD.mkdir(exist_ok=True)
    seed = Path(arguments[arguments.index("--seed") + 1]) if "--seed" in arguments else None
    exe = ".exe" if os.name == "nt" else ""
    generation0 = BUILD / "generation0.c"
    if seed is None:
        step("generation 0 (Python runs the compiler on itself)",
             [sys.executable, "-m", "nexora", "run", (HERE / "cgen.nex").as_posix(), "--allow-read", ".", "--allow-write", ".",
              "--max-output", "1000000000", "--", SOURCE, generation0.relative_to(HERE.parent).as_posix(), "--trusted"])
    else:
        generation0.write_bytes(seed.read_bytes())
    first = BUILD / f"compiler1{exe}"
    step("the C compiler builds the first compiler", [*compiler, "-std=c11", "-O2", generation0.as_posix(), "-o", first.as_posix()])
    generation1 = BUILD / "generation1.c"
    step("generation 1 (the first compiler compiles itself)",
         [first.as_posix(), "--allow-read", ".", "--allow-write", ".", "--", SOURCE, generation1.relative_to(HERE.parent).as_posix(), "--trusted"])
    if seed is None:
        if generation0.read_bytes() != generation1.read_bytes():
            print("DIFFERENT: the compiler does not produce the C it was built from")
            return 1
        print("fixed point: generation 1 is the same C as generation 0")
    elif generation0.read_bytes() == generation1.read_bytes():
        print("the seed is current: generation 1 is the same C as the seed")
    else:
        print("the seed is older than the source (it built a compiler that writes different C); it can be replaced with generation 1")
    second = BUILD / f"compiler2{exe}"
    step("the C compiler builds the second compiler", [*compiler, "-std=c11", "-O2", generation1.as_posix(), "-o", second.as_posix()])
    generation2 = BUILD / "generation2.c"
    step("generation 2 (the second compiler compiles itself)",
         [second.as_posix(), "--allow-read", ".", "--allow-write", ".", "--", SOURCE, generation2.relative_to(HERE.parent).as_posix(), "--trusted"])
    if generation1.read_bytes() != generation2.read_bytes():
        print("DIFFERENT: generation 2 is not generation 1")
        return 1
    print("generation 2 is the same C as generation 1")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

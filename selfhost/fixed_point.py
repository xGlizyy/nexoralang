"""Stage 3 of decision 0024: the interpreter written in NEXORA runs its own source.

    PYTHONPATH=nexora/src python selfhost/fixed_point.py PROGRAM.nex [--levels 0,1,2]

The same program is run at three levels and what it prints is compared:

    level 0   `nex run PROGRAM`                                           the Python interpreter
    level 1   `nex run interpreter.nex -- --run PROGRAM`                  interpreter.nex, run by Python
    level 2   `nex run interpreter.nex -- --run interpreter.nex --run PROGRAM`
                                                                          interpreter.nex, run by interpreter.nex,
                                                                          run by Python

Level 2 first has level 1 check the whole source of the interpreter (five modules), which takes minutes, so it is
optional. Level 3, the interpreter running itself running itself, is not run: see selfhost/README.md for what it costs.

The program must not need the host (files, input, arguments): the point is the interpreter, not the grants.

This is a test tool for the self-hosted work of decision 0024; it is not part of the language.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTERPRETER = (HERE / "interpreter.nex").as_posix()
BIG = "1000000000"


def run(arguments: list[str]) -> tuple[str, float]:
    started = time.time()
    done = subprocess.run(
        [sys.executable, "-m", "nexora", "run", *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=b"",
    )
    if done.returncode != 0:
        raise SystemExit(f"failed ({done.returncode}): {done.stderr.decode('utf-8')[-600:]}")
    return done.stdout.decode("utf-8").replace("\r\n", "\n"), time.time() - started


def program_output(text: str, depth: int) -> tuple[str, str]:
    """What the program printed and how the innermost run ended, from the lines of the drivers.

    Each interpreter prints `FILE|path`, what its program printed and `STOP|how`. With `depth` interpreters, the
    innermost one's lines are the ones in the middle, after `depth` headers and before `depth` trailers."""
    lines = text.split("\n")[:-1]
    headers = 0
    while headers < len(lines) and lines[headers].startswith("FILE|"):
        headers += 1
    body = lines[headers:]
    trailer = []
    while body and body[-1].startswith("STOP|"):
        trailer.append(body.pop())
    return "".join(line + "\n" for line in body), "|".join(reversed(trailer))


def main(arguments: list[str]) -> int:
    path = arguments[0]
    levels = [0, 1, 2]
    if "--levels" in arguments:
        levels = [int(item) for item in arguments[arguments.index("--levels") + 1].split(",")]
    expected: str | None = None
    ok = True
    for level in levels:
        if level == 0:
            output, seconds = run([path])
            stops = ""
            expected = output
        elif level == 1:
            text, seconds = run([INTERPRETER, "--allow-read", ".", "--allow-write", ".", "--max-output", BIG, "--",
                                 "--run", path])
            output, stops = program_output(text, 1)
        else:
            text, seconds = run([INTERPRETER, "--allow-read", ".", "--allow-write", ".", "--max-output", BIG, "--",
                                 "--run", "--allow-read", ".", "--allow-write", ".", INTERPRETER, "--run", path])
            output, stops = program_output(text, 2)
        same = expected is None or output == expected
        ok = ok and same
        print(f"level {level}: {'same' if same else 'DIFFERENT'} output, {seconds:6.1f} s  {stops}")
        if not same:
            print(f"  expected {expected!r}\n  got      {output!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

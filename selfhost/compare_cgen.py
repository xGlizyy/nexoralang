"""Differential check of the code generator to C (selfhost/cgen.nex) against `nex run`.

    NEXORA_CC="python -m ziglang cc" python selfhost/compare_cgen.py FILE.nex [FILE.nex ...]

Each program is run by `nex run` and, compiled by cgen.nex and the C compiler, as an executable. What they write to the
standard output and to the standard error and the exit status are compared. NEXORA_CC is the command of a C compiler (default:
`cc`); the program is built with `-std=c11`.

A program that cgen.nex says it cannot compile yet is counted and skipped. This is a test tool for the self-hosted work of
decision 0026; it is not part of the language.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(command: list[str], **options) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, input=b"", **options)


def text(data: bytes) -> str:
    return data.decode("utf-8").replace("\r\n", "\n")


def python_result(path: str) -> tuple[str, str, int]:
    done = run([sys.executable, "-m", "nexora", "run", path])
    return text(done.stdout), text(done.stderr), done.returncode


def generate(path: str, output: str) -> str:
    done = run([sys.executable, "-m", "nexora", "run", (HERE / "cgen.nex").as_posix(), "--allow-read", ".",
                "--allow-write", ".", "--max-output", "1000000000", "--", path, output])
    return text(done.stdout) + text(done.stderr)


def main(paths: list[str]) -> int:
    compiler = shlex.split(os.environ.get("NEXORA_CC", "cc"))
    same = different = skipped = 0
    with tempfile.TemporaryDirectory(dir=HERE.parent) as scratch:
        for path in paths:
            posix = Path(path).as_posix()
            c_file = Path(scratch, "program.c").relative_to(Path.cwd()).as_posix()
            report = generate(posix, c_file)
            if not report.startswith("wrote "):
                skipped += 1
                print(f"skip  {posix}  ({report.strip().splitlines()[0] if report.strip() else 'no output'})")
                continue
            executable = Path(scratch, "program.exe").as_posix()
            built = run([*compiler, "-std=c11", "-O1", c_file, "-o", executable])
            if built.returncode != 0:
                different += 1
                print(f"DIFF  {posix}\n  the C does not compile:\n{text(built.stderr)[:1500]}")
                continue
            expected = python_result(posix)
            done = run([executable])
            actual = (text(done.stdout), text(done.stderr), done.returncode)
            if expected == actual:
                same += 1
                print(f"ok    {posix} (exit {actual[2]})")
            else:
                different += 1
                names = ("stdout", "stderr", "exit status")
                which = next(i for i in range(3) if expected[i] != actual[i])
                print(f"DIFF  {posix}  ({names[which]})\n  nex run: {expected[which][:300]!r}\n  c:       {actual[which][:300]!r}")
    print(f"{same} equal, {different} different, {skipped} skipped")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

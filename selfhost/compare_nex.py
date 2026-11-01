"""Differential check of the command written in NEXORA (selfhost/nex.nex) against `nex`.

    python selfhost/compare_nex.py check FILE.nex [...]
    python selfhost/compare_nex.py run FILE.nex [...]
    python selfhost/compare_nex.py test FILE.nex [...]

Each file is given to the same command in both implementations. Run by Python, nex.nex has neither a standard error nor a
status, so everything `nex` writes is compared with everything nex.nex writes to its standard output. With NEXORA_NEX set (the
executable cgen.nex makes), the standard output, the standard error and the exit status are compared one by one.

This is a test tool for the self-hosted work of decision 0025; it is not part of the language.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Result:
    """What a command wrote on each stream and how it ended."""

    def __init__(self, out: bytes, err: bytes, code: int | None) -> None:
        self.out = out.decode("utf-8", errors="replace").replace("\r\n", "\n")
        self.err = err.decode("utf-8", errors="replace").replace("\r\n", "\n")
        self.code = code


def command_python(command: str, path: str, extra: tuple[str, ...] = ()) -> Result:
    run = subprocess.run(
        [sys.executable, "-m", "nexora", command, *extra, path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=b"",
    )
    return Result(run.stdout, run.stderr, run.returncode)


def command_nexora(command: str, path: str, extra: tuple[str, ...] = ()) -> Result:
    native = os.environ.get("NEXORA_NEX")
    if native:
        # nex.nex compiled to an executable by selfhost/cgen.nex: no Python in the way. The streams and the status are the
        # ones of the process.
        # An executable built with --cli is called as the command is: `nex check FILE`.
        options = [] if os.environ.get("NEXORA_NEX_CLI") else ["--allow-read", ".", "--allow-write", ".", "--"]
        run = subprocess.run(
            [native, *options, command, *extra, path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=b"",
        )
        return Result(run.stdout, run.stderr, run.returncode)
    # Run by Python, nex.nex has neither a standard error nor a status: everything is on the standard output.
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "nex.nex").as_posix(), "--allow-read", ".", "--allow-write", ".",
         "--max-output", "1000000000", "--", command, *extra, path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, input=b"",
    )
    return Result(run.stdout, b"", None)


def first_difference(want: str, got: str) -> tuple[int, str, str]:
    a, b = want.split("\n"), got.split("\n")
    index = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
    return index + 1, (a[index] if index < len(a) else "<end>"), (b[index] if index < len(b) else "<end>")


def main(arguments: list[str]) -> int:
    command, paths = arguments[0], arguments[1:]
    strict = bool(os.environ.get("NEXORA_NEX"))
    # NEXORA_FORMAT=json gives every command `--format json` (before the file).
    extra = ("--format", "json") if os.environ.get("NEXORA_FORMAT") == "json" else ()
    same = different = 0
    for path in paths:
        posix = Path(path).as_posix()
        want = command_python(command, posix, extra)
        got = command_nexora(command, posix, extra)
        if strict:
            problems = []
            if want.out != got.out:
                problems.append(("stdout", *first_difference(want.out, got.out)))
            if want.err != got.err:
                problems.append(("stderr", *first_difference(want.err, got.err)))
            if want.code != got.code:
                problems.append(("status", 0, str(want.code), str(got.code)))
        else:
            merged = want.out + want.err
            problems = [] if merged == got.out else [("output", *first_difference(merged, got.out))]
        if not problems:
            same += 1
            print(f"ok    {posix}")
        else:
            different += 1
            for stream, line, expected, actual in problems:
                print(f"DIFF  {posix}  {stream} (line {line})")
                print(f"  nex:     {expected!r}")
                print(f"  nex.nex: {actual!r}")
    print(f"{same} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

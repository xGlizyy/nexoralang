r"""`nex run` with the standard input: the executable of nex.nex (built with --cli) against `nex`.

    NEXORA_NEX=path/to/nex-cli PYTHONPATH=nexora/src python selfhost/compare_stdin.py

A program that reads with `input()` is run with several inputs (lines with LF and with CRLF, a last line without a line break,
no input at all, a line that is not ASCII); the standard output, the standard error and the exit status are compared one by one.
This is a test tool for the self-hosted work of decision 0026; it is not part of the language.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROGRAMS = {
    "two lines": 'fn main() {\n    let a = input()\n    let b = input()\n    print(a + "|" + b)\n}\n',
    "until the end": (
        "fn main() {\n    var total = 0\n    var i = 0\n    while i < 3\n        shrinks 3 - i\n    {\n"
        "        total = total + Int.parse(input())\n        i = i + 1\n    }\n    print(total)\n}\n"
    ),
    "echo": 'fn main() {\n    print("you said: " + input())\n}\n',
}

INPUTS = {
    "lf": b"hello\nworld\n",
    "crlf": b"hello\r\nworld\r\n",
    "no final break": b"hello\nworld",
    "one line only": b"hello\n",
    "nothing": b"",
    "empty lines": b"\n\n",
    "numbers": b"1\n2\n3\n",
    "unicode": "héllo ✓\nwörld\n".encode("utf-8"),
}


def run(command: list[str], data: bytes) -> tuple[str, str, int]:
    # Python reads the standard input in the encoding of the console (cp1252 on Windows); UTF-8 mode makes it the same everywhere,
    # which is what the executable always uses.
    done = subprocess.run(command, input=data, capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})
    return (done.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
            done.stderr.decode("utf-8", "replace").replace("\r\n", "\n"), done.returncode)


def main() -> int:
    native = os.environ["NEXORA_NEX"]
    different = total = 0
    with tempfile.TemporaryDirectory() as folder:
        for name, text in PROGRAMS.items():
            path = Path(folder) / (name.replace(" ", "_") + ".nex")
            path.write_text(text, encoding="utf-8", newline="\n")
            for label, data in INPUTS.items():
                total += 1
                want = run([sys.executable, "-m", "nexora", "run", str(path)], data)
                got = run([native, "run", str(path)], data)
                if want != got:
                    different += 1
                    print(f"DIFF  {name} / {label}\n  nex:     {ascii(want)}\n  nex.nex: {ascii(got)}")
    print(f"{total - different} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())

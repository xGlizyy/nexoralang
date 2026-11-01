r"""`nex run --timeout`, `--max-memory` and the other limits of `nex run`: the executable of nex.nex (built with --cli) against `nex`.

    NEXORA_NEX=path/to/nex-cli PYTHONPATH=nexora/src python3 selfhost/compare_limits.py

The time and memory limits exist on Linux only, so this is run there (a static Linux executable built with `zig cc -target
x86_64-linux-musl`, in WSL for instance). The standard output, the standard error and the exit status are compared one by one;
for the memory limit, which stops two very different implementations at different points, only the status and the code of the
diagnostic are compared. This is a test tool for the self-hosted work of decision 0026; it is not part of the language.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

LOOP = (
    'fn main() {\n    print("started")\n    var i = 0\n    while i < 4000000000\n        shrinks 4000000000 - i\n    {\n'
    "        i = i + 1\n    }\n    print(i)\n}\n"
)
FAST = 'fn main() {\n    print("done")\n}\n'
HOG = (
    'fn main() {\n    var big = "x"\n    var i = 0\n    while i < 17\n        shrinks 17 - i\n    {\n        big = big + big\n'
    "        i = i + 1\n    }\n    var items: List[Text] = []\n    var n = 0\n    while n < 5000\n        shrinks 5000 - n\n    {\n"
    "        items = List.append(items, big + to_text(n))\n        n = n + 1\n    }\n    print(List.length(items))\n}\n"
)

# (name, arguments before the file, program, exact comparison?)
CASES = [
    ("timeout stops a loop", ["--timeout", "1"], LOOP, True),
    ("timeout with a fraction", ["--timeout", "0.5"], LOOP, True),
    ("timeout that is not reached", ["--timeout", "20"], FAST, True),
    ("timeout zero", ["--timeout", "0"], FAST, True),
    ("timeout negative", ["--timeout", "-1"], FAST, True),
    ("max-output zero", ["--max-output", "0"], FAST, True),
    ("max-text zero", ["--max-text", "0"], FAST, True),
    ("max-input zero", ["--max-input", "0"], FAST, True),
    ("max-source zero", ["--max-source", "0"], FAST, True),
    ("max-memory zero", ["--max-memory", "0"], FAST, True),
    ("max-memory not reached", ["--max-memory", "4000000000"], FAST, True),
    ("max-memory reached", ["--max-memory", "300000000"], HOG, False),
    ("timeout and format json", ["--timeout", "1", "--format", "json"], LOOP, True),
]


def run(command: list[str]) -> tuple[str, str, int]:
    done = subprocess.run(command, input=b"", capture_output=True, timeout=120)
    return done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace"), done.returncode


def main() -> int:
    native = os.environ["NEXORA_NEX"]
    different = 0
    with tempfile.TemporaryDirectory() as folder:
        for name, options, text, exact in CASES:
            path = Path(folder) / "program.nex"
            path.write_text(text, encoding="utf-8", newline="\n")
            want = run([sys.executable, "-m", "nexora", "run", *options, str(path)])
            got = run([native, "run", *options, str(path)])
            if exact:
                same = want == got
            else:
                same = want[2] == got[2] and "E3007" in want[1] and "E3007" in got[1]
            if not same:
                different += 1
                print(f"DIFF  {name}\n  nex:     {want}\n  nex.nex: {got}")
            else:
                print(f"ok    {name} (status {got[2]})")
    print(f"{len(CASES) - different} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())

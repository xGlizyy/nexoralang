"""Speed of the native `nex` against the Python implementation, on the programs of selfhost/bench/.

    NEXORA_NEX=path/to/nex.exe PYTHONPATH=nexora/src python selfhost/bench.py

Each program is run three times by each and the best time is shown; the output has to be the same. This is a tool for the
self-hosted work of decision 0026; it is not part of the language.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def best(command: list[str]) -> tuple[float, bytes]:
    times = []
    out = b""
    for _ in range(3):
        started = time.time()
        done = subprocess.run(command, capture_output=True, input=b"")
        times.append(time.time() - started)
        out = done.stdout
    return min(times), out.replace(b"\r\n", b"\n")


def main() -> int:
    native = os.environ["NEXORA_NEX"]
    print(f"{'program':10} {'python':>8} {'native':>8}  ratio")
    worst = 0.0
    for path in sorted((HERE / "bench").glob("*.nex")):
        relative = path.relative_to(HERE.parent).as_posix()
        python_time, python_out = best([sys.executable, "-m", "nexora", "run", relative])
        native_time, native_out = best([native, "--allow-read", ".", "--allow-write", ".", "--", "run", relative])
        same = "" if python_out == native_out else "  OUTPUT DIFFERS"
        worst = max(worst, native_time / python_time)
        print(f"{path.stem:10} {python_time:8.2f} {native_time:8.2f}  {native_time / python_time:5.2f}x{same}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

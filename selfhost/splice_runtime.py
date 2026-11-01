"""Puts the current runtime header at the top of C that cgen.nex already wrote, without compiling the program again.

    python selfhost/splice_runtime.py INPUT.c OUTPUT.c

The C that the generator writes is the runtime followed by the program (from the line `/* The program: ... */`). While the
runtime is being tuned, the program does not change, so this gives a new executable in seconds instead of minutes. It is a
development shortcut: the real build is `bootstrap.py`, which writes the whole file with the generator.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = re.compile(r"\n/\* The program: [^\n]* \*/\n\nstatic const char \*const nx_lines0")


def main(arguments: list[str]) -> int:
    source = Path(arguments[0]).read_text(encoding="utf-8")
    at = MARKER.search(source).start()
    header = (HERE / "runtime" / "nexora_rt.h").read_text(encoding="utf-8")
    # A tool built with --trusted starts with `#define RT_NO_FRAMES`: that line stays.
    first = "#define RT_NO_FRAMES\n" if source.startswith("#define RT_NO_FRAMES\n") else ""
    Path(arguments[1]).write_text(first + header.rstrip("\n") + "\n" + source[at:], encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

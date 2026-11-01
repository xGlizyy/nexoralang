"""The formatter written in NEXORA against the one of Python: the same file goes to both and the text they give is compared.

    NEXORA_FORMATTER=path/to/formatter-driver PYTHONPATH=nexora/src python selfhost/compare_format.py FILE.nex [FILE.nex ...]

Each file is read with universal line endings (as `read_file` reads it) and formatted whole. The text and whether the program could be
formatted must be equal, and formatting the result again must not change it (formatting twice is formatting once).
"""

import os
import subprocess
import sys
from pathlib import Path

from nexora.formatter import format_source

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def native(tool, path):
    done = subprocess.run([tool, "--allow-read", ".", "--", path], capture_output=True, env=ENV)
    out = done.stdout.decode("utf-8").replace("\r\n", "\n")
    begin, end = "TEXT-BEGIN\n", "\nTEXT-END "
    if not out.startswith(begin) or end not in out:
        return None, None
    text = out[len(begin):out.rindex(end)]
    return text, out[out.rindex(end) + len(end):].strip() == "ok"


def main(files):
    tool = os.environ.get("NEXORA_FORMATTER")
    if not tool:
        sys.exit("set NEXORA_FORMATTER to the driver built from selfhost/formatter.nex")
    different = 0
    for path in files:
        source = Path(path).read_text(encoding="utf-8-sig")
        expected = format_source(source)
        found = native(tool, path)
        if found != (expected.text, expected.ok):
            different += 1
            print(f"DIFFERENT {path}: ok {expected.ok} / {found[1]}")
        elif expected.ok and format_source(expected.text).text != expected.text:
            different += 1
            print(f"NOT IDEMPOTENT {path}")
    print(f"{len(files)} files, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

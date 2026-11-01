"""Compares `nex context` of the native executable with the Python one, in text and in JSON.

    NEXORA_NEX=selfhost/build/nex_cli.exe PYTHONPATH=nexora/src python selfhost/compare_context.py FILE.nex [FILE.nex ...]

Standard output and exit status must be equal. A program of several modules is not compared: the native `nex context` does not
summarise it yet (it ends with status 70).
"""

import os
import subprocess
import sys

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(command):
    done = subprocess.run(command, capture_output=True, env=ENV)
    return done.stdout.replace(b"\r\n", b"\n"), done.returncode


def main(files):
    native = os.environ.get("NEXORA_NEX")
    if not native:
        sys.exit("set NEXORA_NEX to the native executable")
    different = 0
    for path in files:
        for output_format in ("text", "json"):
            expected = run([sys.executable, "-m", "nexora", "context", path, "--format", output_format])
            found = run([native, "context", path, "--format", output_format])
            if expected != found:
                different += 1
                print(f"DIFFERENT {path} --format {output_format}: status {expected[1]} / {found[1]}")
    print(f"{len(files)} files, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

"""Compares `nex check --evidence` of the native executable with the Python one, in text and in JSON.

    NEXORA_NEX=selfhost/build/nex_cli.exe PYTHONPATH=nexora/src python selfhost/compare_evidence.py FILE.nex [FILE.nex ...]

Standard output and exit status must be equal.
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
    different = total = 0
    for path in files:
        for output_format in ("text", "json"):
            total += 1
            expected = run([sys.executable, "-m", "nexora", "check", "--evidence", path, "--format", output_format])
            found = run([native, "check", "--evidence", path, "--format", output_format])
            if expected != found:
                different += 1
                print(f"DIFFERENT {path} --format {output_format}: status {expected[1]} / {found[1]}")
    print(f"{len(files)} files, {total} runs, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

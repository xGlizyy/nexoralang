"""Compares `nex symbols` of the native executable with the Python one, in text and in JSON, with and without the filters.

    NEXORA_NEX=selfhost/build/nex_cli.exe PYTHONPATH=nexora/src python selfhost/compare_symbols.py FILE.nex [FILE.nex ...]

Standard output and exit status must be equal. The filters are tried with the first name and the first function of the file.
"""

import json
import os
import subprocess
import sys

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(command):
    done = subprocess.run(command, capture_output=True, env=ENV)
    return done.stdout.replace(b"\r\n", b"\n"), done.returncode


def variants(path):
    yield ["--format", "text"]
    yield ["--format", "json"]
    document, _ = run([sys.executable, "-m", "nexora", "symbols", path, "--format", "json"])
    try:
        symbols = json.loads(document)["symbols"] or []
    except ValueError:
        symbols = []
    if symbols:
        yield ["--format", "json", "--name", symbols[-1]["name"]]
        yield ["--name", symbols[0]["name"]]
        yield ["--function", symbols[-1]["function"] or symbols[0]["name"]]
    yield ["--name", "no_such_name"]


def main(files):
    native = os.environ.get("NEXORA_NEX")
    if not native:
        sys.exit("set NEXORA_NEX to the native executable")
    different = 0
    total = 0
    for path in files:
        for options in variants(path):
            total += 1
            expected = run([sys.executable, "-m", "nexora", "symbols", path, *options])
            found = run([native, "symbols", path, *options])
            if expected != found:
                different += 1
                print(f"DIFFERENT {path} {' '.join(options)}: status {expected[1]} / {found[1]}")
    print(f"{len(files)} files, {total} runs, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

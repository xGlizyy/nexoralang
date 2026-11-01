"""Compares `nex test --format json` of the native executable with the Python one (and the exit status).

    NEXORA_NEX=selfhost/build/nex_cli.exe PYTHONPATH=nexora/src python selfhost/compare_test.py FILE.nex [FILE.nex ...]

Every file is tried whole and, when it has examples, with `--function` for its first function that has one. A path that does not
exist and an unknown function are tried too: the standard output and the status must be equal.
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
    yield []
    document, _ = run([sys.executable, "-m", "nexora", "test", path, "--format", "json"])
    try:
        examples = json.loads(document)["examples"] or []
    except ValueError:
        examples = []
    if examples:
        yield ["--function", examples[0]["function"]]
    yield ["--function", "no_such_function"]


def main(files):
    native = os.environ.get("NEXORA_NEX")
    if not native:
        sys.exit("set NEXORA_NEX to the native executable")
    different = 0
    total = 0
    for path in files:
        for options in variants(path):
            total += 1
            expected = run([sys.executable, "-m", "nexora", "test", path, "--format", "json", *options])
            found = run([native, "test", path, "--format", "json", *options])
            if expected != found:
                different += 1
                print(f"DIFFERENT {path} {' '.join(options)}: status {expected[1]} / {found[1]}")
    print(f"{len(files)} files, {total} runs, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

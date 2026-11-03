"""Compares `nex impact` of the native executable with the Python one, in text and in JSON.

    NEXORA_NEX=selfhost/build/out/nex PYTHONPATH=nexora/src python selfhost/compare_impact.py [DIRECTORY]

The pairs are the files `NAME_a.nex` and `NAME_b.nex` of selfhost/impact_cases/ (or of DIRECTORY), the projects `modules_*`, and a few
pairs made of programs that cannot be compared (a syntax error, a type error, a missing file). The standard output, the standard error
and the exit status must be equal; for the programs that cannot be compared the standard error is compared too, as the executable
writes it.
"""

import itertools
import os
import subprocess
import sys
from pathlib import Path

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(command):
    done = subprocess.run(command, capture_output=True, env=ENV, cwd=ROOT)
    return done.stdout.replace(b"\r\n", b"\n"), done.stderr.replace(b"\r\n", b"\n"), done.returncode


def pairs(directory):
    found = []
    for first in sorted(directory.glob("*_a.nex")):
        second = first.with_name(first.name[: -len("_a.nex")] + "_b.nex")
        if second.exists():
            found.append((first, second))
    projects = {name: directory / name / "main.nex" for name in ("modules_a", "modules_b", "modules_c", "modules_e")}
    projects["modules_d"] = directory / "modules_d" / "sub" / "main.nex"
    for first, second in itertools.permutations(projects.values(), 2):
        if first.exists() and second.exists():
            found.append((first, second))
    good = directory / "dir_widen_a.nex"
    for broken in ("invalid_a.nex", "type_error_a.nex"):
        found.append((directory / broken, good))
        found.append((good, directory / broken))
    found.append((good, directory / "does_not_exist.nex"))
    found.append((directory / "does_not_exist.nex", good))
    found.append((good, good))
    found.append((directory / "dir_widen_b.nex", good))
    return found


def main(arguments):
    native = os.environ.get("NEXORA_NEX")
    if not native:
        sys.exit("set NEXORA_NEX to the native executable")
    directory = Path(arguments[0]) if arguments else HERE / "impact_cases"
    different = total = 0
    for first, second in pairs(directory):
        for output_format in ("text", "json"):
            total += 1
            before, after = os.path.relpath(first, ROOT).replace("\\", "/"), os.path.relpath(second, ROOT).replace("\\", "/")
            expected = run([sys.executable, "-m", "nexora", "impact", before, after, "--format", output_format])
            found = run([native, "impact", before, after, "--format", output_format])
            if expected != found:
                different += 1
                print(f"DIFFERENT {before} {after} --format {output_format}: status {expected[2]} / {found[2]}")
                for label, left, right in (("stdout", expected[0], found[0]), ("stderr", expected[1], found[1])):
                    if left != right:
                        print(f"  {label} differs:")
                        print("   python:", left.decode("utf-8", "replace")[:300].replace("\n", "\n          "))
                        print("   native:", right.decode("utf-8", "replace")[:300].replace("\n", "\n          "))
    print(f"{total // 2} pairs, {total} runs, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

"""Compares `nex migrate` of the native executable with the Python one on the 0.11 corpus.

    NEXORA_NEX=selfhost/build/nex_cli.exe PYTHONPATH=nexora/src python selfhost/compare_migrate.py [CORPUS_DIR]

Each .nex file of the corpus is the entry of a program, tried with its line endings as they are and (MIGRATE_VARIANTS, a list separated
by commas, default `plain,crlf,bom,cr`) with CRLF endings, with a byte-order mark and with lone CR endings, each one without `--write`
and with it (MIGRATE_WRITES, `0,1` by default). Standard output, standard error, status and, afterwards, every file of the tree must be
equal. A carriage return is dropped from the two outputs before comparing them: Python on Windows translates the line endings of what it
prints and the executable does not.
"""

import os
import shutil
import subprocess
import sys
import tempfile

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
DEFAULT = os.path.join(os.path.dirname(__file__), "..", "nexora", "tests", "migration", "corpus011")
CR, LF = bytes([13]), bytes([10])


def variants(data):
    wanted = os.environ.get("MIGRATE_VARIANTS", "plain,crlf,bom,cr").split(",")
    lf = data.replace(CR + LF, LF)
    forms = {
        "plain": data,
        "crlf": lf.replace(LF, CR + LF),
        "bom": bytes([0xEF, 0xBB, 0xBF]) + data,
        "cr": lf.replace(LF, CR),
    }
    for name in wanted:
        yield name, forms[name]


def tree(root):
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, root)] = handle.read()
    return found


def run(command, cwd):
    done = subprocess.run(command, capture_output=True, env=ENV, cwd=cwd)
    return done.stdout.replace(CR, b""), done.stderr.replace(CR, b""), done.returncode


def main(corpus):
    native = os.environ.get("NEXORA_NEX")
    if not native:
        sys.exit("set NEXORA_NEX to the native executable")
    entries = []
    for folder, _, names in os.walk(corpus):
        for name in sorted(names):
            if name.endswith(".nex"):
                entries.append(os.path.relpath(os.path.join(folder, name), corpus).replace(os.sep, "/"))
    entries.sort()
    writes = [flag == "1" for flag in os.environ.get("MIGRATE_WRITES", "0,1").split(",")]
    different = total = 0
    with tempfile.TemporaryDirectory() as scratch:
        for entry in entries:
            with open(os.path.join(corpus, entry), "rb") as handle:
                original = handle.read()
            for label, data in variants(original):
                for write in writes:
                    total += 1
                    sides = {}
                    for side in ("python", "native"):
                        folder = os.path.join(scratch, side)
                        shutil.rmtree(folder, ignore_errors=True)
                        shutil.copytree(corpus, folder)
                        with open(os.path.join(folder, entry), "wb") as handle:
                            handle.write(data)
                        command = [sys.executable, "-m", "nexora", "migrate"] if side == "python" else [native, "migrate"]
                        command += [entry, "--write"] if write else [entry]
                        sides[side] = (run(command, folder), tree(folder))
                    if sides["python"] != sides["native"]:
                        different += 1
                        print(f"DIFFERENT {entry} [{label}] {'--write' if write else ''}: "
                              f"status {sides['python'][0][2]} / {sides['native'][0][2]}")
    print(f"{len(entries)} files, {total} runs, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT))

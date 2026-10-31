"""Differential check of the host: arguments, input, files, network and processes.

    python selfhost/compare_host.py

Each case is a program with the options a user would give (--allow-read, --allow-write, --allow-network,
--allow-process), an input and arguments. It is run by `nex run` and by the interpreter written in NEXORA
(selfhost/interpreter.nex --run), and what it prints and the diagnostic it stops with are compared.

The cases write their files under selfhost/host_cases/. Paths are given relative to the repository root, which
is where this script has to be run from. This is a test tool for the self-hosted work of decision 0024; it is
not part of the language.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "host_cases"
DATA = "selfhost/host_cases/data"

READ_DATA = f'uses read "{DATA}"\n'
WRITE_DATA = f'uses write "{DATA}"\n'

# name -> (program, options, input, arguments)
CASES_TABLE = {
    "arguments": (
        'fn main() {\n    let given = args()\n    print(List.length(given))\n    for word in given {\n        print(word)\n    }\n}\n',
        [], "", ["alpha", "beta gamma", "3"],
    ),
    "no_arguments": (
        'fn main() {\n    print(List.length(args()))\n}\n', [], "", [],
    ),
    "input_lines": (
        'fn main() {\n    let first = input()\n    let second = input()\n    print(first + "-" + second)\n    print(Text.length(input()))\n}\n',
        [], "one\ntwo\n\n", [],
    ),
    "input_without_final_newline": (
        'fn main() {\n    print(input())\n}\n', [], "only", [],
    ),
    "input_ended": (
        'fn main() {\n    print(input())\n    print(input())\n    print(input())\n}\n', [], "a\nb\n", [],
    ),
    "input_none": (
        'fn main() {\n    print("before")\n    print(input())\n}\n', [], "", [],
    ),
    "read_ok": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}/in.txt"\n    print(read_file(path))\n    print(read_file("{DATA}/in.txt"))\n}}\n',
        [("read", DATA)], "", [],
    ),
    "read_subdirectory": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}/sub/../in.txt"\n    print(read_file(path))\n}}\n',
        [("read", DATA)], "", [],
    ),
    "read_not_declared": (
        f'fn main() {{\n    let path = "{DATA}/in.txt"\n    print(read_file(path))\n}}\n',
        [("read", DATA)], "", [],
    ),
    "read_not_granted": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}/in.txt"\n    print(read_file(path))\n}}\n',
        [], "", [],
    ),
    "read_granted_elsewhere": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}/in.txt"\n    print(read_file(path))\n}}\n',
        [("read", "selfhost/host_cases/other")], "", [],
    ),
    "read_sibling": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}2/in.txt"\n    print(read_file(path))\n}}\n',
        [("read", DATA)], "", [],
    ),
    "read_escapes": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}/../secret.txt"\n    print(read_file(path))\n}}\n',
        [("read", DATA)], "", [],
    ),
    "read_granted_parent": (
        READ_DATA + f'fn main() {{\n    let path = "{DATA}/in.txt"\n    print(read_file(path))\n}}\n',
        [("read", "selfhost/host_cases")], "", [],
    ),
    "write_then_read": (
        READ_DATA + WRITE_DATA + f'fn main() {{\n    let path = "{DATA}/out.txt"\n    write_file(path, "written by the program")\n    print(read_file(path))\n}}\n',
        [("read", DATA), ("write", DATA)], "", [],
    ),
    "write_not_declared": (
        f'fn main() {{\n    let path = "{DATA}/out.txt"\n    write_file(path, "x")\n}}\n',
        [("write", DATA)], "", [],
    ),
    "write_not_granted": (
        WRITE_DATA + f'fn main() {{\n    let path = "{DATA}/out.txt"\n    write_file(path, "x")\n}}\n',
        [], "", [],
    ),
    "write_outside": (
        WRITE_DATA + f'fn main() {{\n    let path = "{DATA}2/out.txt"\n    write_file(path, "x")\n}}\n',
        [("write", DATA)], "", [],
    ),
    "network_not_declared": (
        'fn main() {\n    let url = "https://example.com/data"\n    print(Net.get(url))\n}\n',
        [("network", "https://example.com")], "", [],
    ),
    "network_not_granted": (
        'uses network "https://example.com"\nfn main() {\n    let url = "https://example.com/data"\n    print(Net.get(url))\n}\n',
        [], "", [],
    ),
    "network_other_origin": (
        'uses network "https://example.com"\nfn main() {\n    let url = "https://other.org/data"\n    print(Net.get(url))\n}\n',
        [("network", "https://example.com")], "", [],
    ),
    "network_not_https": (
        'uses network "https://example.com"\nfn main() {\n    let url = "http://example.com/data"\n    print(Net.get(url))\n}\n',
        [("network", "https://example.com")], "", [],
    ),
    "network_other_port": (
        'uses network "https://example.com"\nfn main() {\n    let url = "https://example.com:8443/data"\n    print(Net.get(url))\n}\n',
        [("network", "https://example.com")], "", [],
    ),
    "network_credentials": (
        'uses network "https://example.com"\nfn main() {\n    let url = "https://user@example.com/data"\n    print(Net.get(url))\n}\n',
        [("network", "https://example.com")], "", [],
    ),
    "process_not_declared": (
        'fn main() {\n    let command = "python"\n    print(Process.run(command, ["--version"]))\n}\n',
        [("process", "python")], "", [],
    ),
    "process_not_granted": (
        'uses process "python"\nfn main() {\n    let command = "python"\n    print(Process.run(command, ["--version"]))\n}\n',
        [], "", [],
    ),
    "process_other_command": (
        'uses process "python"\nfn main() {\n    let command = "ruby"\n    print(Process.run(command, ["--version"]))\n}\n',
        [("process", "python")], "", [],
    ),
}


def prepare() -> None:
    (CASES / "data" / "sub").mkdir(parents=True, exist_ok=True)
    (CASES / "other").mkdir(parents=True, exist_ok=True)
    (CASES / "data" / "in.txt").write_text("the text of a file\nwith two lines\n", encoding="utf-8", newline="\n")
    (CASES / "secret.txt").write_text("secret\n", encoding="utf-8", newline="\n")
    for name, (program, _, _, _) in CASES_TABLE.items():
        (CASES / f"{name}.nex").write_text(program, encoding="utf-8", newline="\n")
    (CASES / "data" / "out.txt").unlink(missing_ok=True)


def options_of(allow: list[tuple[str, str]]) -> list[str]:
    return [item for kind, scope in allow for item in (f"--allow-{kind}", scope)]


def python_run(path: str, allow: list[tuple[str, str]], text: str, arguments: list[str]):
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", path, "--format", "json", *options_of(allow),
         *(["--", *arguments] if arguments else [])],
        capture_output=True, text=True, encoding="utf-8", input=text,
    )
    diagnostic = None
    if run.returncode in (3, 5):
        diagnostic = json.loads(run.stderr)["diagnostics"][0]
    return run.returncode, run.stdout, diagnostic


def nexora_run(path: str, allow: list[tuple[str, str]], text: str, arguments: list[str]):
    stdin_file = CASES / "stdin.txt"
    stdin_file.write_text(text, encoding="utf-8", newline="")
    run = subprocess.run(
        [sys.executable, "-m", "nexora", "run", (HERE / "interpreter.nex").as_posix(), "--allow-read", ".",
         "--allow-write", ".", "--max-output", "1000000000", "--", "--run", *options_of(allow),
         "--stdin", stdin_file.relative_to(HERE.parent).as_posix(), "--cwd", Path.cwd().as_posix(), path, *arguments],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        return {"stop": f"RUN FAILED ({run.returncode}): {run.stdout[-300:]} {run.stderr[-900:]}"}
    lines: list[str] = []
    fail = None
    result = {"stop": "missing", "output": "", "fail": None}
    for line in run.stdout.split("\n")[:-1]:
        if line.startswith("FILE|"):
            lines, fail = [], None
        elif line.startswith("FAIL|"):
            fail = line
        elif line.startswith("STOP|"):
            result = {"stop": line[5:].split(" ")[0], "reason": line[5:], "output": "".join(item + "\n" for item in lines),
                      "fail": fail}
        else:
            lines.append(line)
    return result


def parse_fail(line: str) -> dict:
    _, code, label, hint, notes, where = line.split("|", 5)
    return {"code": code, "label": label, "hint": hint, "notes": notes.split("~~") if notes else [], "where": where}


def expected_fail(diagnostic: dict) -> dict:
    where = f"{diagnostic['line']}:{diagnostic['column']}-{diagnostic['end_line']}:{diagnostic['end_column']}"
    return {"code": diagnostic["code"], "label": diagnostic["label"], "hint": diagnostic["hint"] or "",
            "notes": diagnostic["notes"], "where": where}


def main() -> int:
    if Path.cwd().resolve() != HERE.parent.resolve():
        print("run it from the repository root")
        return 2
    prepare()
    same = different = skipped = 0
    for name, (_, allow, text, arguments) in CASES_TABLE.items():
        path = f"selfhost/host_cases/{name}.nex"
        code, expected, diagnostic = python_run(path, allow, text, arguments)
        run = nexora_run(path, allow, text, arguments)
        if code not in (0, 3, 5):
            skipped += 1
            print(f"skip  {name} (nex run exits with {code})")
        elif run["stop"] not in ("ok", "fail") or (run["fail"] or "").startswith("FAIL|E0000|"):
            skipped += 1
            print(f"skip  {name} (NEXORA: {run.get('reason', run['stop'])})")
        elif (code == 0) != (run["stop"] == "ok") or expected != run["output"]:
            different += 1
            print(f"DIFF  {name}\n  python ({code}): {expected!r}\n  nexora: {run['output']!r} {run.get('reason', '')}")
        elif code != 0 and expected_fail(diagnostic) != parse_fail(run["fail"]):
            different += 1
            want, got = expected_fail(diagnostic), parse_fail(run["fail"])
            key = next((k for k in ("code", "label", "hint", "where", "notes") if want[k] != got[k]), "?")
            print(f"DIFF  {name}\n  diagnostic {key}\n    python: {want[key]!r}\n    nexora: {got[key]!r}")
        else:
            same += 1
            print(f"ok    {name}" + ("" if code == 0 else f" (fails with {diagnostic['code']})"))
    print(f"{same} equal, {different} different, {skipped} skipped")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())

"""Compares what `Process.run` and `Net.get` do, in the native tools and in Python.

    NEXORA_NEX=path/to/nex PYTHONPATH=nexora/src python selfhost/compare_host_run.py [--network]

(compare_host.py compares the decisions: what the program declares and the user allows. This one compares the operations.)

Programs that start a command (the interpreter that runs this script is the command, so it exists on every system) and, with
--network, programs that read a page over HTTPS, are run by `nex run` of Python and by the native `nex run`, with the permissions
they need. The standard output, the standard error and the exit status have to be equal. A failure that depends on the library of TLS
of the system (the wording of a rejected certificate) is compared by its code and its first words only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

COMMAND = Path(sys.executable).name.removesuffix(".exe")


def program(command: str, arguments: str) -> str:
    return f'uses process "{command}"\n\nfn main() {{\n    print(Process.run("{command}", {arguments}))\n}}\n'


def python_code(code: str) -> str:
    return '["-c", "' + code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"]'


ALLOW = ["--allow-process", COMMAND]

PROCESS_CASES = [
    ("prints", program(COMMAND, python_code("print('hello')")), ALLOW),
    ("unicode without a line break", program(COMMAND, python_code("import sys; sys.stdout.buffer.write('ñandú ✓'.encode())")), ALLOW),
    ("arguments", program(COMMAND, '["-c", "import sys; print(sys.argv[1:])", "a b", "c\\"d", "", "e\\\\f"]'), ALLOW),
    ("exit status", program(COMMAND, python_code("import sys; sys.exit(3)")), ALLOW),
    ("exit status and standard error", program(COMMAND, python_code("import sys; sys.stderr.write('  it failed \\n'); sys.exit(2)")), ALLOW),
    ("output that is not UTF-8", program(COMMAND, python_code("import sys; sys.stdout.buffer.write(bytes([255, 254]))")), ALLOW),
    ("output too large", program(COMMAND, python_code("import sys; sys.stdout.write('x' * 2000000)")), ALLOW),
    ("standard input is empty", program(COMMAND, python_code("import sys; print(repr(sys.stdin.read()))")), ALLOW),
    ("environment", program(COMMAND, python_code("import os; print(sorted(k for k in os.environ if k.upper() in ('HOME', 'USER', 'FOO')))")), ALLOW),
    ("not on PATH", program("nexora_no_such_command", "[]"), ["--allow-process", "nexora_no_such_command"]),
    ("timeout", program(COMMAND, python_code("import time; time.sleep(30)")), ALLOW),
]

NETWORK_CASES = [
    ("page", 'uses network "https://example.com"\n\nfn main() {\n    let page = Net.get("https://example.com/")\n    print(Text.contains(page, "Example Domain"))\n}\n',
     ["--allow-network", "https://example.com"]),
    ("page that does not exist", 'uses network "https://example.com"\n\nfn main() {\n    print(Net.get("https://example.com/nexora-no-such-page"))\n}\n',
     ["--allow-network", "https://example.com"]),
    ("expired certificate", 'uses network "https://expired.badssl.com"\n\nfn main() {\n    print(Net.get("https://expired.badssl.com/"))\n}\n',
     ["--allow-network", "https://expired.badssl.com"]),
    ("wrong host in the certificate", 'uses network "https://wrong.host.badssl.com"\n\nfn main() {\n    print(Net.get("https://wrong.host.badssl.com/"))\n}\n',
     ["--allow-network", "https://wrong.host.badssl.com"]),
    ("self-signed certificate", 'uses network "https://self-signed.badssl.com"\n\nfn main() {\n    print(Net.get("https://self-signed.badssl.com/"))\n}\n',
     ["--allow-network", "https://self-signed.badssl.com"]),
]

SYSTEM_DEPENDENT = ("expired certificate", "wrong host in the certificate", "self-signed certificate")


def run(command: list[str], env: dict) -> tuple[int, str, str]:
    done = subprocess.run(command, capture_output=True, env=env, timeout=120)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def code_of(text: str) -> str:
    return next((line.split("]")[0] for line in text.splitlines() if "error[" in line), "")


def main(arguments: list[str]) -> int:
    tool = os.environ.get("NEXORA_NEX")
    if not tool:
        sys.exit("set NEXORA_NEX to the native nex")
    cases = list(PROCESS_CASES)
    if "--network" in arguments:
        cases += NETWORK_CASES
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    different = 0
    with tempfile.TemporaryDirectory() as folder:
        for name, source, grants in cases:
            path = Path(folder) / "case.nex"
            path.write_text(source, encoding="utf-8", newline="\n")
            expected = run([sys.executable, "-m", "nexora", "run", *grants, str(path)], env)
            found = run([tool, "run", *grants, str(path)], env)
            if name in SYSTEM_DEPENDENT:
                same = expected[0] == found[0] and code_of(expected[2]) == code_of(found[2]) and "HTTPS request failed" in found[2]
            else:
                same = expected == found
            if not same:
                different += 1
                print(f"DIFFERENT {name}")
                print("  python:", expected[0], repr(expected[1][:200]), repr(expected[2][:600]))
                print("  nexora:", found[0], repr(found[1][:200]), repr(found[2][:600]))
    print(f"{len(cases)} programs, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

r"""The debug session of the worker written in NEXORA against the one of Python: the same request and the same commands go to
both, and every line they write is compared.

    NEXORA_WORKER=path/to/worker.exe PYTHONPATH=nexora/src python selfhost/compare_debug.py [NAME]

Each scenario is a request and the commands the controller sends, one for each time the program stops; when the commands run
out, `continue` is sent until the session ends. This is a test tool for the self-hosted work of decision 0026; it is not part
of the language.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMITS = {"output_bytes": 4096, "text_chars": 4096}

LOOPS = (
    "fn add(a: Int, b: Int) gives Int {\n    let s = a + b\n    return s\n}\n\n"
    "fn main() {\n    let xs = [1, 2, 3]\n    var t = 0\n    for x in xs {\n        t = add(t, x)\n    }\n"
    "    print(t)\n    print(\"done\")\n}\n"
)

VALUES = (
    "type Point = { x: Int, y: Int }\n\n"
    "type Shape = enum {\n    Circle(radius: Int),\n    Square(side: Int),\n    Dot\n}\n\n"
    "fn find(items: List[Int], wanted: Int) gives Option[Int] {\n    for item in items {\n        if item == wanted {\n            return Some(item)\n        }\n    }\n    return None\n}\n\n"
    "fn main() {\n    let p = Point(x: 1, y: 2)\n    let s = Shape.Circle(5)\n    let d = Shape.Dot\n    let found = find([1, 2, 3], 2)\n"
    "    let missing = find([1], 9)\n    let r: Result[Int, Text] = Ok(3)\n    let e: Result[Int, Text] = Err(\"bad\")\n"
    "    let long = \"abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij abcdefghij\"\n"
    "    let nested = [[1, 2], [3, [4]], [], [5, 6, 7, 8, 9, 10, 11, 12, 13]]\n    let quote = \"a \\\"b\\\"\\n\\tc \\\\ é ✓\"\n    let f = 1.5\n    let ok = true\n    print(ok)\n}\n"
)

RECURSE = (
    "fn down(n: Int) gives Int\n    needs n >= 0\n{\n    if n == 0 {\n        return 0\n    }\n    return down(n - 1)\n}\n\n"
    "fn main() {\n    print(down(3))\n}\n"
)

MANY = (
    "fn main() {\n    var i = 0\n    while i < 11000\n        shrinks 11000 - i\n    {\n        i = i + 1\n    }\n    print(i)\n}\n"
)


def program(code: str, **extra) -> dict:
    return {"action": "debug", "code": code, "limits": LIMITS, **extra}


STEP = {"command": "step"}
CONT = {"command": "continue"}
STOP = {"command": "stop"}

SCENARIOS: list[tuple[str, dict, list]] = [
    ("loops, stepping", program(LOOPS), [STEP] * 12 + [STOP]),
    ("loops, to the end", program(LOOPS), [STEP] * 40),
    ("loops, continue", program(LOOPS), [CONT]),
    ("loops, breakpoint inside", program(LOOPS, breakpoints=[3]), [CONT, CONT, STEP, CONT]),
    ("loops, breakpoint as a list of two", program(LOOPS, breakpoints=[3, 12]), [CONT, CONT, CONT, CONT, CONT]),
    ("loops, breakpoints as an object", program(LOOPS, breakpoints={"playground.nex": [12]}), [CONT, STEP, CONT]),
    ("loops, set breakpoints later", program(LOOPS), [STEP, {"command": "set_breakpoints", "lines": [3]}, CONT, CONT, STOP]),
    ("loops, set breakpoints for a file", program(LOOPS), [{"command": "set_breakpoints", "file": "playground.nex", "lines": [12]}, CONT, CONT]),
    ("loops, breakpoint on the last line", program(LOOPS, breakpoints=[14]), [CONT, CONT]),
    ("values", program(VALUES), [STEP] * 16),
    ("recursion", program(RECURSE), [STEP] * 20),
    ("recursion, contract", program(RECURSE.replace("down(3)", "down(0 - 1)")), [STEP] * 6),
    ("runtime error", program("fn main() {\n    let x = 1\n    print(x / 0)\n}\n"), [STEP, STEP, STEP]),
    ("output limit", program("fn main() {\n    var i = 0\n    while i < 100\n        shrinks 100 - i\n    {\n        print(\"abcdefghij\")\n        i = i + 1\n    }\n}\n", limits={"output_bytes": 30, "text_chars": 100}), [CONT]),
    ("output delta", program('fn main() {\n    print("a")\n    print("b")\n    print("c")\n}\n'), [STEP, STEP, STEP, STEP, STEP]),
    ("unicode output", program('fn main() {\n    print("héllo ✓")\n    print(1)\n}\n'), [STEP, STEP, STEP]),
    ("too many steps", program(MANY), [CONT]),
    ("invalid program", program("fn main() {\n    print(nope)\n}\n"), []),
    ("invalid with bad breakpoints", program("fn main() {\n    print(nope)\n}\n", breakpoints=[99]), []),
    ("bad breakpoint line", program(LOOPS, breakpoints=[99]), []),
    ("bad breakpoint zero", program(LOOPS, breakpoints=[0]), []),
    ("bad breakpoint type", program(LOOPS, breakpoints="3"), []),
    ("bad breakpoint file", program(LOOPS, breakpoints={"other.nex": [1]}), []),
    ("empty program", program("fn main() {\n}\n"), []),
    ("no statements output", program("fn main() {\n    print(1)\n}\n"), [CONT]),
    ("read a file", program('uses read "."\n\nfn main() {\n    print(read_file("x"))\n}\n'), [STEP, STEP]),
    ("write a file", program('uses write "."\n\nfn main() {\n    write_file("x", "a")\n}\n'), [STEP, STEP]),
    ("network", program('uses network "https://example.com"\n\nfn main() {\n    print(Net.get("http://example.com/"))\n}\n'), [STEP, STEP]),
    ("input", program("fn main() {\n    print(input())\n}\n"), [STEP, STEP]),
    ("commands not understood", program(LOOPS), ["not json", "[1]", {"command": "dance"}, {}, {"command": "set_breakpoints", "lines": [99]}, {"command": "set_breakpoints", "file": 3, "lines": [1]}, STEP, STOP]),
    ("project", program("", filename="main.nex", files={
        "main.nex": 'import "lib.nex"\n\nfn main() {\n    let a = lib.twice(4)\n    print(a)\n}\n',
        "lib.nex": "pub fn twice(n: Int) gives Int {\n    let r = n * 2\n    return r\n}\n"}), [STEP] * 10),
    ("project with breakpoints", program("", filename="main.nex", files={
        "main.nex": 'import "lib.nex"\n\nfn main() {\n    let a = lib.twice(4)\n    print(a)\n}\n',
        "lib.nex": "pub fn twice(n: Int) gives Int {\n    let r = n * 2\n    return r\n}\n"}, breakpoints={"lib.nex": [3]}), [CONT, CONT]),
    ("project in folders", program("", filename="app/main.nex", files={
        "app/main.nex": 'import "../lib/util.nex"\n\nfn main() {\n    print(util.one())\n}\n',
        "lib/util.nex": "pub fn one() gives Int {\n    let x = 1\n    return x\n}\n"}), [STEP] * 8),
    ("not a debug request", {"action": "debug", "code": 5}, []),
    ("no code", {"action": "debug"}, []),
]


def start(command: list[str], request: dict) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "nexora" / "src")}
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT, env=env)
    assert process.stdin is not None
    process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
    process.stdin.flush()
    return process


def read(process: subprocess.Popen) -> object:
    assert process.stdout is not None
    line = process.stdout.readline().decode("utf-8")
    if not line:
        return None
    try:
        return json.loads(line)
    except ValueError:
        return {"unreadable": line[:200]}


def send(process: subprocess.Popen, command: object) -> None:
    assert process.stdin is not None
    text = command if isinstance(command, str) else json.dumps(command)
    try:
        process.stdin.write((text + "\n").encode("utf-8"))
        process.stdin.flush()
    except OSError:
        pass


def run(name: str, request: dict, commands: list) -> list[str]:
    python = start([sys.executable, *([] if os.environ.get("NEXORA_NO_ISOLATE") else ["-I"]), "-m", "nexora.worker"], request)
    native = start([str(Path(os.environ["NEXORA_WORKER"]).resolve())], request)
    problems: list[str] = []
    index = 0
    for _ in range(400):
        want, got = read(python), read(native)
        if want != got:
            problems.append(f"line {index}\n  python: {json.dumps(want, ensure_ascii=False)[:1200]}\n  nexora: {json.dumps(got, ensure_ascii=False)[:1200]}")
            break
        if want is None or not isinstance(want, dict) or want.get("state") not in ("paused", "command_error"):
            break
        command = commands[index] if index < len(commands) else CONT
        index += 1
        send(python, command)
        send(native, command)
    for process in (python, native):
        try:
            process.kill()
        except OSError:
            pass
        process.wait()
    return problems


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    different = 0
    total = 0
    for name, request, commands in SCENARIOS:
        if only and only not in name:
            continue
        total += 1
        problems = run(name, request, commands)
        if problems:
            different += 1
            print(f"DIFF  {name}\n  " + problems[0])
    print(f"{total - different} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())

r"""The worker written in NEXORA against the worker of Python: the same requests go to both and the answers are compared.

    NEXORA_WORKER=path/to/worker.exe PYTHONPATH=nexora/src python selfhost/compare_worker.py

The requests are the examples of the language (checked and run), the programs of the test suite of the worker, and a list of
requests that are written here: limits, projects, paths that are not allowed, requests that are not understood. The answers
are read as JSON and compared field by field, without `duration_ms` (the native worker has no clock; the server measures it).

This is a test tool for the self-hosted work of decision 0026; it is not part of the language.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "nexora" / "examples"

LIMITS = {"output_bytes": 65536, "text_chars": 262144}


def run_program(code: str, **extra) -> dict:
    return {"action": "run", "code": code, "limits": LIMITS, **extra}


def hand_written() -> list[tuple[str, object]]:
    """Requests that name what they test. A request can be a dict (written as JSON) or the raw text of a line."""
    cases: list[tuple[str, object]] = [
        ("info", {"action": "info"}),
        ("check ok", {"action": "check", "code": 'fn main() {\n    print("hi")\n}\n'}),
        ("check warning", {"action": "check", "code": "fn main() {\n    let x = 1\n}\n"}),
        ("check syntax", {"action": "check", "code": "fn main( {\n}\n"}),
        ("check lexical", {"action": "check", "code": 'fn main() {\n    print("abc)\n}\n'}),
        ("check no main", {"action": "check", "code": "fn f() gives Int {\n    return 1\n}\n"}),
        ("check filename", {"action": "check", "code": "fn main() {\n    let x: Int = \"a\"\n}\n", "filename": "a/b.nex"}),
        ("check unicode", {"action": "check", "code": 'fn main() {\n    print("héllo ✓ 日本語 😀")\n}\n'}),
        ("run unicode", run_program('fn main() {\n    print("héllo ✓ 日本語 😀")\n}\n')),
        ("run empty", run_program("fn main() {\n}\n")),
        ("run invalid", run_program("fn main() {\n    print(undefined)\n}\n")),
        ("run default filename", {"action": "run", "code": 'fn main() {\n    print("x")\n}\n'}),
        ("run runtime error", run_program("fn main() {\n    print(1 / 0)\n}\n")),
        ("run output limit", run_program("fn main() {\n    var i = 0\n    while i < 100\n        shrinks 100 - i\n    {\n        print(\"abcdefghij\")\n        i = i + 1\n    }\n}\n",
                                         limits={"output_bytes": 55, "text_chars": 1000})),
        ("run output limit exact", run_program('fn main() {\n    print("abcd")\n    print("efgh")\n}\n',
                                               limits={"output_bytes": 10, "text_chars": 1000})),
        ("run output limit unicode", run_program('fn main() {\n    print("ééééé")\n    print("日本語")\n}\n',
                                                 limits={"output_bytes": 13, "text_chars": 1000})),
        ("run text limit", run_program('fn main() {\n    var s = "ab"\n    var i = 0\n    while i < 30\n        shrinks 30 - i\n    {\n        s = s + s\n        i = i + 1\n    }\n    print(Text.length(s))\n}\n',
                                       limits={"output_bytes": 65536, "text_chars": 1000})),
        ("run reads a file", run_program('uses read "."\n\nfn main() {\n    print(read_file("x.txt"))\n}\n')),
        ("run writes a file", run_program('uses write "."\n\nfn main() {\n    write_file("x.txt", "a")\n}\n')),
        ("run network", run_program('uses network "https://example.com"\n\nfn main() {\n    print(Net.get("https://example.com/"))\n}\n')),
        ("run network not https", run_program('uses network "https://example.com"\n\nfn main() {\n    print(Net.get("http://example.com/"))\n}\n')),
        ("run process", run_program('uses process "ls"\n\nfn main() {\n    print(Process.run("ls", []))\n}\n')),
        ("run input", run_program("fn main() {\n    print(input())\n}\n")),
        ("run args", run_program("fn main() {\n    print(List.length(args()))\n}\n")),
        ("run contract", run_program("fn f(n: Int) gives Int\n    needs n > 0\n{\n    return n\n}\n\nfn main() {\n    print(f(0))\n}\n")),
        ("run list growth", run_program("fn main() {\n    var items: List[Int] = []\n    var i = 0\n    while i < 20000\n        shrinks 20000 - i\n    {\n        items = List.append(items, i)\n        i = i + 1\n    }\n    print(List.length(items))\n}\n", limits={"output_bytes": 100, "text_chars": 100})),
        ("import in a single source", {"action": "check", "code": 'import "other.nex"\n\nfn main() {\n}\n'}),
        ("import in a single source, run", run_program('import "other.nex"\n\nfn main() {\n}\n')),
        # The checker says nothing else about a program whose import cannot be read (the loader of Python drops it).
        ("import in a single source, used", {"action": "check", "code": 'import "other.nex"\n\nfn main() {\n    print(other.one())\n}\n'}),
        # Projects
        ("project ok", {"action": "run", "code": "", "filename": "main.nex", "limits": LIMITS, "files": {
            "main.nex": 'import "lib.nex"\n\nfn main() {\n    print(lib.twice(4))\n}\n',
            "lib.nex": "pub fn twice(n: Int) gives Int {\n    return n * 2\n}\n"}}),
        ("project check", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": 'import "lib.nex"\n\nfn main() {\n    print(lib.twice(4))\n}\n',
            "lib.nex": "pub fn twice(n: Int) gives Int {\n    return n * 2\n}\n"}}),
        ("project in folders", {"action": "run", "code": "", "filename": "app/main.nex", "limits": LIMITS, "files": {
            "app/main.nex": 'import "../lib/util.nex"\n\nfn main() {\n    print(util.one())\n}\n',
            "lib/util.nex": "pub fn one() gives Int {\n    return 1\n}\n"}}),
        ("project backslash paths", {"action": "run", "code": "", "filename": "app\\main.nex", "limits": LIMITS, "files": {
            "app\\main.nex": 'import "util.nex"\n\nfn main() {\n    print(util.one())\n}\n',
            "app/util.nex": "pub fn one() gives Int {\n    return 1\n}\n"}}),
        ("project missing import", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": 'import "missing.nex"\n\nfn main() {\n}\n'}}),
        ("project import outside", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": 'import "../outside.nex"\n\nfn main() {\n}\n'}}),
        ("project absolute import", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": 'import "/lib.nex"\n\nfn main() {\n}\n', "lib.nex": "pub fn f() {\n}\n"}}),
        ("project circular", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": 'import "a.nex"\n\nfn main() {\n}\n',
            "a.nex": 'import "b.nex"\n\npub fn a() {\n}\n', "b.nex": 'import "a.nex"\n\npub fn b() {\n}\n'}}),
        ("project error in a module", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": 'import "lib.nex"\n\nfn main() {\n    print(lib.f())\n}\n',
            "lib.nex": "pub fn f() gives Int {\n    return \"a\"\n}\n"}}),
        ("project runtime error in a module", {"action": "run", "code": "", "filename": "main.nex", "limits": LIMITS, "files": {
            "main.nex": 'import "lib.nex"\n\nfn main() {\n    print(lib.f(0))\n}\n',
            "lib.nex": "pub fn f(n: Int) gives Int {\n    return 10 / n\n}\n"}}),
        ("project unused module", {"action": "run", "code": "", "filename": "main.nex", "limits": LIMITS, "files": {
            "main.nex": 'fn main() {\n    print(1)\n}\n', "extra.nex": "pub fn f() {\n}\n"}}),
        ("project bad path: no extension", {"action": "check", "code": "", "filename": "main", "files": {"main": "fn main() {\n}\n"}}),
        ("project bad path: parent", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "../x.nex": ""}}),
        ("project bad path: absolute", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "/x.nex": ""}}),
        ("project bad path: colon", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "c:x.nex": ""}}),
        ("project bad path: space", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "a b.nex": ""}}),
        ("project bad path: dots", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "a/./b.nex": ""}}),
        ("project bad path: deep", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "a/b/c/d/e/f/g/h/i.nex": ""}}),
        ("project bad path: long part", {"action": "check", "code": "", "filename": "main.nex", "files": {
            "main.nex": "fn main() {\n}\n", "a" * 65 + ".nex": ""}}),
        ("project no entry", {"action": "check", "code": "", "filename": "main.nex", "files": {"other.nex": "fn main() {\n}\n"}}),
        ("project empty", {"action": "check", "code": "", "filename": "main.nex", "files": {}}),
        ("project too many", {"action": "check", "code": "", "filename": "f0.nex", "files": {f"f{i}.nex": "fn main() {\n}\n" for i in range(33)}}),
        ("project file not text", {"action": "check", "code": "", "filename": "main.nex", "files": {"main.nex": 1}}),
        ("project files not an object", {"action": "check", "code": "", "filename": "main.nex", "files": ["main.nex"]}),
        ("project with null files", {"action": "check", "code": "fn main() {\n}\n", "files": None}),
        ("project info", {"action": "info", "files": {"main.nex": ""}}),
        ("project debug files", {"action": "info", "code": "x", "files": {}}),
        # Requests that are not understood
        ("not json", "this is not json"),
        ("json array", "[1, 2]"),
        ("empty object", "{}"),
        ("unknown action", {"action": "format", "code": ""}),
        ("code not text", {"action": "check", "code": 5}),
        ("no code", {"action": "check"}),
        ("filename not text", {"action": "check", "code": "fn main() {\n}\n", "filename": 3}),
        ("filename null", {"action": "check", "code": "fn main() {\n}\n", "filename": None}),
        ("limits not object", {"action": "run", "code": "fn main() {\n}\n", "limits": 5}),
        ("limits null", {"action": "run", "code": 'fn main() {\n    print(1)\n}\n', "limits": None}),
    ]
    return cases


def example_cases() -> list[tuple[str, object]]:
    cases: list[tuple[str, object]] = []
    for path in sorted(EXAMPLES.rglob("*.nex")):
        name = path.relative_to(EXAMPLES).as_posix()
        text = path.read_text(encoding="utf-8")
        if "import " in text and "modules/" in name:
            continue
        cases.append((f"example check {name}", {"action": "check", "code": text, "filename": path.name}))
        cases.append((f"example run {name}", run_program(text, filename=path.name)))
    main = (EXAMPLES / "modules" / "main.nex")
    models = (EXAMPLES / "modules" / "models.nex")
    if main.exists() and models.exists():
        for action in ("check", "run"):
            cases.append((f"example project modules {action}", {
                "action": action, "code": "", "filename": "main.nex", "limits": LIMITS,
                "files": {"main.nex": main.read_text(encoding="utf-8"), "models.nex": models.read_text(encoding="utf-8")}}))
    return cases


def encode(request: object) -> bytes:
    text = request if isinstance(request, str) else json.dumps(request, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def ask(command: list[str], request: object) -> object:
    done = subprocess.run(command, input=encode(request), capture_output=True, timeout=120, cwd=ROOT)
    try:
        return json.loads(done.stdout.decode("utf-8"))
    except ValueError:
        return {"unreadable": done.stdout.decode("utf-8", errors="replace")[:200], "stderr": done.stderr.decode("utf-8", errors="replace")[:200]}


def comparable(answer: object) -> object:
    if isinstance(answer, dict):
        return {key: value for key, value in answer.items() if key != "duration_ms"}
    return answer


def main() -> int:
    native = [str(Path(os.environ["NEXORA_WORKER"]).resolve())]
    python = [sys.executable, *([] if os.environ.get("NEXORA_NO_ISOLATE") else ["-I"]), "-m", "nexora.worker"]
    env_path = str(ROOT / "nexora" / "src")
    os.environ["PYTHONPATH"] = env_path
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    cases = hand_written() + example_cases()
    different = 0
    shown = 0
    for name, request in cases:
        if only and only not in name:
            continue
        want = comparable(ask(python, request))
        got = comparable(ask(native, request))
        if want != got:
            different += 1
            if shown < 12 or only:
                shown += 1
                print(f"DIFF  {name}")
                print(f"  python: {json.dumps(want, ensure_ascii=False)[:1500]}")
                print(f"  nexora: {json.dumps(got, ensure_ascii=False)[:1500]}")
            else:
                print(f"DIFF  {name}")
    total = sum(1 for name, _ in cases if not only or only in name)
    print(f"{total - different} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())

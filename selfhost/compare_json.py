r"""The JSON of selfhost/json.nex against Python's json module: each text is read and written by both and the results compared.

    NEXORA_JSON=path/to/json_roundtrip.exe python selfhost/compare_json.py

This is a test tool for the self-hosted work of decision 0026; it is not part of the language.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

CASES = [
    "null", "true", "false", "0", "-0", "7", "-12345", "9223372036854775807", "1.5", "-2.5e3", "1e5", "1E-2", "0.1",
    r'""', r'"abc"', r'"a\"b"', r'"a\\b"', r'"a\/b"', r'"line\nbreak"', r'"tab\there"', r'"cr\rhere"', r'"\b\f"', r'"A"',
    r'"é"', r'"éx"', r'"€"', r'"😀"', '"héllo wörld"', '"日本語"', '"emoji 😀 ok"', r'"\u0001"',
    r'"\u001f"', "[]", "[1, 2, 3]", "[1,[2,[3]]]", '[null, true, "x"]', "{}", '{"a": 1}', '{"a": 1, "b": [1, 2], "c": {"d": null}}',
    '  {"k" : "v" }  ', '{"language": "nexora", "limits": {"output_bytes": 65536, "text_chars": 262144}}',
    r'{"code": "fn main() {\n    print(1)\n}\n", "filename": "playground.nex"}', '{"a": 1, "a": 2}', "[1, 2", '{"a" 1}',
    '{"a": }', "nul", "tru", "01", "1.", '"unterminated', r'"bad \x escape"', "[1,]", "{,}", "", "   ", "[] []", "1 2",
    r'{"files": {"main.nex": "fn main() {}"}}',
]


def python_result(text: str) -> str:
    try:
        return json.dumps(json.loads(text), ensure_ascii=False)
    except (ValueError, RecursionError):
        return "ERROR"


def main() -> int:
    executable = os.environ["NEXORA_JSON"]
    # One text a line, in UTF-8, on the standard input: the arguments of a command line are not UTF-8 on every system.
    texts = "".join(case + "\n" for case in CASES)
    done = subprocess.run([executable, "--", str(len(CASES))], input=texts.encode("utf-8"), capture_output=True)
    lines = done.stdout.decode("utf-8").replace("\r\n", "\n").split("\n")[:-1]
    different = 0
    for text, got in zip(CASES, lines):
        want = python_result(text)
        if want != got:
            different += 1
            print(f"DIFF  {text!r}\n  python: {want!r}\n  nexora: {got!r}")
    if len(lines) != len(CASES):
        print(f"DIFF  {len(lines)} answers for {len(CASES)} texts")
        different += 1
    print(f"{len(CASES) - different} equal, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())

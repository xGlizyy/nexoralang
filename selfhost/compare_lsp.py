"""Compares the language server written in NEXORA (selfhost/lsp.nex) with the one of Python (nexora/src/nexora/lsp.py).

    NEXORA_LSP=path/to/lsp PYTHONPATH=nexora/src python selfhost/compare_lsp.py [--encodings utf-16,utf-8,utf-32] FILE.nex [FILE.nex ...]

For each program a session is written: initialize, open the file, a request of each kind at many positions of the text, a change that
breaks the program, a save, a close, shutdown and exit. The same bytes go to both servers and the answers, parsed, have to be equal
(in the same order: the notifications that publish diagnostics come after the answer that caused them).
LSP_POSITIONS is how many positions are asked about in each file (120 by default) and LSP_CRLF=1 sends the text with CRLF line endings.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def frame(message: dict) -> bytes:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def parse(data: bytes) -> list[dict]:
    messages = []
    at = 0
    while at < len(data):
        end = data.find(b"\r\n\r\n", at)
        if end < 0:
            break
        header = data[at:end].decode("ascii", "replace")
        length = int(re.search(r"Content-Length:\s*(\d+)", header, re.I).group(1))
        body = data[end + 4:end + 4 + length]
        messages.append(json.loads(body.decode("utf-8")))
        at = end + 4 + length
    return messages


def positions(text: str, limit: int) -> list[tuple[int, int]]:
    """Lines and characters (counted from zero) worth asking about: the start, the middle and the end of every word."""
    found = []
    for number, line in enumerate(text.split("\n")):
        line = line.rstrip("\r")
        found.append((number, 0))
        for word in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*", line):
            found.append((number, word.start()))
            if word.end() - word.start() > 2:
                found.append((number, word.start() + 1))
            found.append((number, word.end()))
        found.append((number, len(line)))
    if len(found) > limit:
        step = len(found) / limit
        found = [found[int(i * step)] for i in range(limit)]
    return found


def session(path: Path, text: str, encodings: list[str], limit: int) -> list[dict]:
    uri = path.as_uri()
    identifiers = iter(range(1, 100000))
    messages: list[dict] = []

    def request(method: str, params: dict) -> None:
        messages.append({"jsonrpc": "2.0", "id": next(identifiers), "method": method, "params": params})

    def notify(method: str, params: dict) -> None:
        messages.append({"jsonrpc": "2.0", "method": method, "params": params})

    document = {"uri": uri}
    request("initialize", {"capabilities": {"general": {"positionEncodings": encodings}}})
    notify("initialized", {})
    notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "nexora", "version": 1, "text": text}})
    for line, character in positions(text, limit):
        at = {"textDocument": document, "position": {"line": line, "character": character}}
        request("textDocument/hover", at)
        request("textDocument/definition", at)
        request("textDocument/references", {**at, "context": {"includeDeclaration": True}})
        request("textDocument/documentHighlight", at)
        request("textDocument/prepareRename", at)
        request("textDocument/signatureHelp", at)
    for line, character in positions(text, max(8, limit // 12)):
        at = {"textDocument": document, "position": {"line": line, "character": character}}
        request("textDocument/references", {**at, "context": {"includeDeclaration": False}})
        request("textDocument/rename", {**at, "newName": "renamed"})
        request("textDocument/rename", {**at, "newName": ""})
        request("textDocument/completion", at)
    request("textDocument/documentSymbol", {"textDocument": document})
    request("textDocument/formatting", {"textDocument": document, "options": {}})
    lines = text.count("\n") + 1
    for start, end in ((0, 0), (0, min(3, lines)), (max(0, lines // 2 - 2), lines // 2 + 2), (max(0, lines - 3), lines + 2)):
        request("textDocument/rangeFormatting", {
            "textDocument": document, "options": {},
            "range": {"start": {"line": start, "character": 0}, "end": {"line": end, "character": 0}},
        })
    request("textDocument/doesNotExist", {})
    request("textDocument/hover", {"textDocument": {"uri": "file:///nowhere.nex"}, "position": {"line": 0, "character": 0}})
    # A change that breaks the program, and one that repairs it.
    broken = text + "\nfn broken( {\n"
    notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2}, "contentChanges": [{"text": broken}]})
    request("textDocument/documentSymbol", {"textDocument": document})
    request("textDocument/hover", {"textDocument": document, "position": {"line": 0, "character": 3}})
    notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 3}, "contentChanges": [{"text": text}]})
    notify("textDocument/didSave", {"textDocument": document, "text": text})
    notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "nexora", "version": 4, "text": text}})
    notify("textDocument/didClose", {"textDocument": document})
    request("textDocument/hover", {"textDocument": document, "position": {"line": 0, "character": 0}})
    request("shutdown", {})
    notify("exit", {})
    return messages


def run(command: list[str], data: bytes, env: dict) -> list[dict]:
    done = subprocess.run(command, input=data, capture_output=True, env=env, timeout=600)
    return parse(done.stdout)


def main(arguments: list[str]) -> int:
    tool = os.environ.get("NEXORA_LSP")
    if not tool:
        sys.exit("set NEXORA_LSP to the language server built from selfhost/lsp.nex")
    encodings = [[], ["utf-8"], ["utf-32", "utf-16"]]
    limit = int(os.environ.get("LSP_POSITIONS", "120"))
    if arguments[:1] == ["--encodings"]:
        wanted = arguments[1].split(",")
        encodings = [[name] for name in wanted]
        arguments = arguments[2:]
    env = dict(os.environ, PYTHONUTF8="1")
    different = 0
    requests = 0
    for name in arguments:
        path = Path(name).resolve()
        text = path.read_text(encoding="utf-8")
        if os.environ.get("LSP_CRLF"):
            text = text.replace("\n", "\r\n")
        for offered in encodings:
            messages = session(path, text, offered, limit)
            data = b"".join(frame(message) for message in messages)
            expected = run([sys.executable, "-m", "nexora.lsp"], data, env)
            found = run([tool], data, env)
            requests += len(messages)
            if expected != found:
                different += 1
                print(f"DIFFERENT {name} {offered}: {len(expected)} messages from Python, {len(found)} from NEXORA")
                for index, (one, two) in enumerate(zip(expected, found)):
                    if one != two:
                        sent = next((m for m in messages if m.get("id") == one.get("id") and one.get("id") is not None), None)
                        print("  first difference at message", index, "of the answers")
                        print("  request :", json.dumps(sent, ensure_ascii=False)[:300] if sent else "(a notification)")
                        print("  python  :", json.dumps(one, ensure_ascii=False)[:600])
                        print("  nexora  :", json.dumps(two, ensure_ascii=False)[:600])
                        break
    print(f"{len(arguments)} files, {requests} messages, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

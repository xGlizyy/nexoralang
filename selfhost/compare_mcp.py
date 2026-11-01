"""Compares the MCP server written in NEXORA (selfhost/mcp.nex) with the one of Python (nexora/src/nexora/mcp_server.py).

    NEXORA_MCP=path/to/mcp MCP_PYTHON=path/to/python-with-the-mcp-sdk PYTHONPATH=nexora/src python selfhost/compare_mcp.py [FILE.nex ...]

The Python server needs the MCP SDK (version 2), which is not a dependency of NEXORA: MCP_PYTHON is an interpreter that has it
(`python -m pip install mcp` in a virtual environment). A session is sent to both servers one request at a time, waiting for each
answer (the SDK answers concurrent requests in any order, so a fixed order is the only one that can be compared), and the answers,
parsed, have to be equal. The addresses of the pages of pydantic in the messages of invalid arguments carry the version of pydantic
and are compared without it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

PROTOCOL = "2025-06-18"


class Client:
    def __init__(self, command: list[str], env: dict) -> None:
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env
        )

    def ask(self, message: dict, timeout: float = 60.0):
        """Sends a message; for a request, returns the one line that answers it (None if nothing comes in time)."""
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()
        if "id" not in message:
            return None
        box: list = []
        reader = threading.Thread(target=lambda: box.append(self.process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(timeout)
        if not box or not box[0]:
            return None
        return json.loads(box[0].decode("utf-8"))

    def close(self) -> None:
        try:
            self.process.stdin.close()
            self.process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.process.kill()


def normal(value):
    """The answer with the version of pydantic left out of its addresses."""
    return json.loads(re.sub(r"errors\.pydantic\.dev/\d+\.\d+/", "errors.pydantic.dev/X/", json.dumps(value)))


def session(files: list[Path]) -> list[dict]:
    identifiers = iter(range(1, 100000))

    def call(name: str, arguments: dict) -> dict:
        return {"jsonrpc": "2.0", "id": next(identifiers), "method": "tools/call", "params": {"name": name, "arguments": arguments}}

    def request(method: str, params: dict | None = None) -> dict:
        message = {"jsonrpc": "2.0", "id": next(identifiers), "method": method}
        if params is not None:
            message["params"] = params
        return message

    messages = [
        request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "compare", "version": "1"}}),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        request("tools/list"),
        request("ping"),
    ]
    tools = ("nexora_check", "nexora_get_diagnostics", "nexora_inspect", "nexora_get_context", "nexora_get_symbols")
    for path in files:
        text = path.read_text(encoding="utf-8")
        for tool in tools:
            messages.append(call(tool, {"source": text}))
        messages.append(call("nexora_check", {"source": text, "filename": "other_name.nex"}))
        messages.append(call("nexora_get_symbols", {"source": text, "name": "main"}))
        messages.append(call("nexora_get_symbols", {"source": text, "function": "main"}))
    source = "fn main() {\n    print(1)\n}\n"
    messages += [
        call("nexora_check", {}),
        call("nexora_check", {"source": 5}),
        call("nexora_check", {"source": source, "filename": 5}),
        call("nexora_check", {"source": source, "filename": "../a.nex"}),
        call("nexora_check", {"source": source, "filename": "a.txt"}),
        call("nexora_check", {"source": "x" * (256 * 1024 + 1)}),
        call("nexora_check", {"source": source, "extra": 1}),
        call("nexora_get_symbols", {"source": source, "name": "1x"}),
        call("nexora_get_symbols", {"source": source, "function": "a b"}),
        call("nexora_get_symbols", {"source": source, "name": None, "function": None}),
        call("nexora_get_language_spec", {}),
        call("nexora_get_language_spec", {"section": "zzz"}),
        call("nexora_get_language_spec", {"section": "../x"}),
        call("nexora_get_capabilities", {}),
        call("nope", {}),
        request("tools/call", {}),
        request("nope"),
        request("resources/list"),
        request("prompts/list"),
        request("ping"),
    ]
    return messages


def spec_calls(python_answer: dict) -> list[dict]:
    """A call for each section of the specification that the first answer lists."""
    calls = []
    document = json.loads(python_answer["result"]["content"][0]["text"])
    for number, section in enumerate(document.get("sections", [])):
        calls.append({"jsonrpc": "2.0", "id": 900000 + number, "method": "tools/call",
                      "params": {"name": "nexora_get_language_spec", "arguments": {"section": section["id"]}}})
    return calls


def main(arguments: list[str]) -> int:
    tool = os.environ.get("NEXORA_MCP")
    python = os.environ.get("MCP_PYTHON")
    if not tool or not python:
        sys.exit("set NEXORA_MCP to the server built from selfhost/mcp.nex and MCP_PYTHON to a Python that has the MCP SDK")
    env = dict(os.environ, PYTHONUTF8="1")
    files = [Path(name).resolve() for name in arguments]
    messages = session(files)
    expected = Client([python, "-m", "nexora.mcp_server"], env)
    found = Client([tool], env)
    different = 0
    extra: list[dict] = []
    try:
        index = 0
        queue = list(messages)
        while queue:
            message = queue.pop(0)
            one = expected.ask(message)
            two = found.ask(message)
            index += 1
            if message.get("method") == "tools/call" and message["params"].get("name") == "nexora_get_language_spec" \
                    and not message["params"].get("arguments") and one is not None and not one["result"].get("isError"):
                queue = spec_calls(one) + queue
            if "id" in message and (one is None or two is None or normal(one) != normal(two)):
                different += 1
                print(f"DIFFERENT request {message['id']}: {json.dumps(message, ensure_ascii=False)[:300]}")
                print("  python :", json.dumps(one, ensure_ascii=False)[:700])
                print("  nexora :", json.dumps(two, ensure_ascii=False)[:700])
    finally:
        expected.close()
        found.close()
    print(f"{len(files)} files, {index} messages, {different} different")
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

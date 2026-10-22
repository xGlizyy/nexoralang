"""The language server: what it answers for a program.

Every answer comes from the same analysis the command line uses, so the
diagnostics the editor shows are the ones `nex check` gives.
"""

import json

from nexora import lsp

PROGRAM = """fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn main() -> Void {
    let total = add(1, 2)
    print(total)
}
"""


def _server(text: str = PROGRAM) -> lsp.Server:
    server = lsp.Server()
    server.did_open({
        "textDocument": {"uri": "file:///p.nex", "languageId": "nexora", "version": 1, "text": text},
    })
    return server


def _position(line: int, character: int) -> dict:
    return {"line": line, "character": character}


def test_the_diagnostics_are_the_ones_of_the_command_line():
    server = _server("fn main() -> Void {\n    let x: Int = \"text\"\n}\n")
    diagnostics = server.diagnostics_of(server.documents["file:///p.nex"])
    assert [d["code"] for d in diagnostics] == ["E2011"]
    assert diagnostics[0]["range"]["start"]["line"] == 1
    assert diagnostics[0]["source"] == "nexora"
    assert "Expected Int, found Text" in diagnostics[0]["message"]


def test_a_program_without_problems_has_no_diagnostics():
    server = _server()
    assert server.diagnostics_of(server.documents["file:///p.nex"]) == []


def test_the_completion_offers_the_keywords_the_builtins_and_the_names_in_scope():
    server = _server()
    items = server.completion({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(5, 4),
    })
    labels = {item["label"] for item in items}
    assert {"fn", "let", "while", "print", "to_text", "List.append", "total", "add"} <= labels


def test_the_hover_of_a_value_says_its_type():
    server = _server()
    answer = server.hover({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(5, 10),
    })
    assert answer is not None
    assert "total: Int" in answer["contents"]["value"]


def test_the_hover_of_a_function_says_its_signature():
    server = _server()
    answer = server.hover({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(5, 16),
    })
    assert answer is not None
    assert "fn add(a: Int, b: Int) -> Int" in answer["contents"]["value"]


def test_the_definition_of_a_name_is_where_it_was_declared():
    server = _server()
    places = server.definition({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(5, 16),
    })
    assert len(places) == 1
    assert places[0]["range"]["start"] == {"line": 0, "character": 3}


def test_the_references_of_a_name_are_all_the_places_it_is_used():
    server = _server()
    places = server.references({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(0, 4),
    })
    assert len(places) == 2


def test_renaming_changes_the_declaration_and_its_uses():
    server = _server()
    answer = server.rename({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(5, 16),
        "newName": "plus",
    })
    assert answer is not None
    edits = answer["changes"]["file:///p.nex"]
    assert len(edits) == 2
    assert all(edit["newText"] == "plus" for edit in edits)


def test_the_symbols_of_the_document_are_the_functions_and_the_variables():
    server = _server()
    symbols = server.document_symbol({"textDocument": {"uri": "file:///p.nex"}})
    names = [symbol["name"] for symbol in symbols]
    assert "add" in names
    assert "main" in names
    assert "total" in names


def test_the_signature_help_says_the_parameters_of_the_function_being_called():
    server = _server()
    answer = server.signature_help({
        "textDocument": {"uri": "file:///p.nex"},
        "position": _position(5, 16),
    })
    assert answer is not None
    assert answer["signatures"][0]["label"] == "fn add(a: Int, b: Int) -> Int"
    assert [p["label"] for p in answer["signatures"][0]["parameters"]] == ["a", "b"]


def test_the_formatting_of_a_document_gives_the_canonical_shape():
    server = _server("fn main() -> Void {\nlet x   = 1\n}\n")
    edits = server.formatting({"textDocument": {"uri": "file:///p.nex"}, "options": {}})
    assert len(edits) == 1
    assert edits[0]["newText"] == "fn main() -> Void {\n    let x = 1\n}\n"


def test_the_formatting_of_a_range_leaves_the_rest_alone():
    server = _server("fn main() -> Void {\nlet x   = 1\nprint(x)\n}\n")
    edits = server.range_formatting({
        "textDocument": {"uri": "file:///p.nex"},
        "options": {},
        "range": {"start": _position(1, 0), "end": _position(1, 12)},
    })
    assert len(edits) == 1
    assert edits[0]["newText"] == "    let x = 1"


def test_the_server_speaks_the_protocol():
    server = lsp.Server()
    answer = server.initialize({"capabilities": {}})
    assert answer["capabilities"]["hoverProvider"] is True
    assert answer["capabilities"]["documentFormattingProvider"] is True
    assert answer["serverInfo"]["name"] == "nexora-lsp"


def test_a_message_is_read_and_written_with_its_header():
    import io

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode("utf-8")
    reader = io.BytesIO(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    writer = io.BytesIO()
    connection = lsp.Connection(reader, writer)
    message = connection.read()
    assert message["method"] == "initialize"
    connection.write({"jsonrpc": "2.0", "id": 1, "result": {}})
    written = writer.getvalue()
    assert written.startswith(b"Content-Length: ")
    assert b"{\"jsonrpc\": \"2.0\"" in written


def test_the_server_answers_over_the_protocol_in_a_process():
    """The server, started as a process, answers and publishes the diagnostics."""
    import subprocess
    import sys

    program = "fn main() -> Void {\n    let x: Int = \"text\"\n}\n"

    def frame(message: dict) -> bytes:
        body = json.dumps(message).encode("utf-8")
        return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body

    child = subprocess.Popen(
        [sys.executable, "-m", "nexora.lsp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        child.stdin.write(frame({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"capabilities": {}},
        }))
        child.stdin.flush()
        first = child.stdout.readline().decode("ascii")
        assert first.startswith("Content-Length:")
        length = int(first.split(":")[1].strip())
        child.stdout.readline()
        body = child.stdout.read(length)
        answer = json.loads(body.decode("utf-8"))
        assert answer["id"] == 1
        assert answer["result"]["capabilities"]["hoverProvider"] is True

        child.stdin.write(frame({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": "file:///p.nex", "languageId": "nexora", "version": 1, "text": program,
                },
            },
        }))
        child.stdin.flush()
        header = child.stdout.readline().decode("ascii")
        length = int(header.split(":")[1].strip())
        child.stdout.readline()
        published = json.loads(child.stdout.read(length).decode("utf-8"))
        assert published["method"] == "textDocument/publishDiagnostics"
        codes = [d["code"] for d in published["params"]["diagnostics"]]
        assert codes == ["E2011"]
    finally:
        child.stdin.close()
        child.wait(timeout=30)

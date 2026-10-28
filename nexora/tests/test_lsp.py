"""The language server: what it answers for a program.

Every answer comes from the same analysis the command line uses, so the
diagnostics the editor shows are the ones `nex check` gives.
"""

import json

from nexora import lsp

PROGRAM = """fn add(a: Int, b: Int) gives Int {
    return a + b
}

fn main() {
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
    server = _server("fn main() {\n    let x: Int = \"text\"\n}\n")
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
    assert "fn add(a: Int, b: Int) gives Int" in answer["contents"]["value"]


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
    assert answer["signatures"][0]["label"] == "fn add(a: Int, b: Int) gives Int"
    assert [p["label"] for p in answer["signatures"][0]["parameters"]] == ["a", "b"]


def test_the_formatting_of_a_document_gives_the_canonical_shape():
    server = _server("fn main() {\nlet x   = 1\n}\n")
    edits = server.formatting({"textDocument": {"uri": "file:///p.nex"}, "options": {}})
    assert len(edits) == 1
    assert edits[0]["newText"] == "fn main() {\n    let x = 1\n}\n"


def test_the_formatting_of_a_range_leaves_the_rest_alone():
    server = _server("fn main() {\nlet x   = 1\nprint(x)\n}\n")
    edits = server.range_formatting({
        "textDocument": {"uri": "file:///p.nex"},
        "options": {},
        "range": {"start": _position(1, 0), "end": _position(1, 12)},
    })
    assert len(edits) == 1
    assert edits[0]["newText"] == "    let x = 1"


def test_formatting_a_range_does_not_take_the_lines_of_another_place():
    # The range is cut from the formatted text by line number, so the formatted text has
    # to keep every line: the comment and the blank line before the range included.
    server = _server("fn main() {\n// c\n\nlet x   = 1\nprint(x)\n}\n")
    edits = server.range_formatting({
        "textDocument": {"uri": "file:///p.nex"},
        "options": {},
        "range": {"start": _position(3, 0), "end": _position(3, 12)},
    })
    assert edits[0]["newText"] == "    let x = 1"


def test_formatting_a_document_keeps_its_comments():
    server = _server("// a program\nfn main() { // main\nlet x   = 1 // one\n}\n")
    edits = server.formatting({"textDocument": {"uri": "file:///p.nex"}, "options": {}})
    assert edits[0]["newText"] == "// a program\nfn main() { // main\n    let x = 1 // one\n}\n"


def test_the_server_speaks_the_protocol():
    server = lsp.Server()
    answer = server.initialize({"capabilities": {}})
    assert answer["capabilities"]["hoverProvider"] is True
    assert answer["capabilities"]["documentFormattingProvider"] is True
    assert answer["serverInfo"]["name"] == "nexora-lsp"


def test_utf16_positions_are_negotiated_and_used_for_hover_and_diagnostics():
    server = _server('fn main() {\n    let value: Int = "😀"\n    print(value)\n}\n')
    answer = server.initialize({"capabilities": {"general": {"positionEncodings": ["utf-16", "utf-8"]}}})
    assert answer["capabilities"]["positionEncoding"] == "utf-16"
    line = server.documents["file:///p.nex"].lines[1]
    diagnostic = server.diagnostics_of(server.documents["file:///p.nex"])[0]
    assert diagnostic["range"]["end"] == {
        "line": 1,
        "character": len(line.encode("utf-16-le")) // 2,
    }
    program = ('fn echo(prefix: Text, value: Int) gives Int { return value }\n'
               'fn main() {\n    let value = 1\n    let result = echo("😀", value)\n    print(result)\n}\n')
    position_server = _server(program)
    position_line = position_server.documents["file:///p.nex"].lines[3]
    value_character = len(position_line[:position_line.rindex("value")].encode("utf-16-le")) // 2
    answer = position_server.hover({"textDocument": {"uri": "file:///p.nex"},
                                    "position": _position(3, value_character)})
    assert answer is not None and "value: Int" in answer["contents"]["value"]


def test_utf8_position_encoding_is_supported_when_the_client_requests_it():
    server = _server()
    answer = server.initialize({"capabilities": {"general": {"positionEncodings": ["utf-8"]}}})
    assert answer["capabilities"]["positionEncoding"] == "utf-8"


def test_imports_resolve_from_the_importing_file_and_support_unsaved_buffers(tmp_path):
    main_path = tmp_path / "main.nex"
    math_path = tmp_path / "math.nex"
    main_path.write_text('import "math.nex"\nfn main() {\n    let total = math.add(1, 2)\n    print(total)\n}\n', encoding="utf-8")
    math_path.write_text("this is deliberately invalid", encoding="utf-8")
    server = lsp.Server()
    server.did_open({"textDocument": {"uri": main_path.as_uri(), "languageId": "nexora", "version": 1,
                                      "text": main_path.read_text(encoding="utf-8")}})
    server.did_open({"textDocument": {"uri": math_path.as_uri(), "languageId": "nexora", "version": 2,
                                      "text": "pub fn add(a: Int, b: Int) gives Int { return a + b }\n"}})
    main = server.documents[main_path.as_uri()]
    assert server.diagnostics_of(main) == []
    position = _position(2, main.lines[2].index("add"))
    hover = server.hover({"textDocument": {"uri": main.uri}, "position": position})
    assert hover is not None and "fn add(a: Int, b: Int) gives Int" in hover["contents"]["value"]
    definition = server.definition({"textDocument": {"uri": main.uri}, "position": position})
    assert definition == [{"uri": math_path.as_uri(),
                           "range": {"start": {"line": 0, "character": 7},
                                     "end": {"line": 0, "character": 10}}}]
    references = server.references({"textDocument": {"uri": main.uri}, "position": position})
    assert {(item["uri"], item["range"]["start"]["character"]) for item in references} == {
        (math_path.as_uri(), 7), (main_path.as_uri(), main.lines[2].index("add")),
    }
    rename = server.rename({"textDocument": {"uri": main.uri}, "position": position, "newName": "sum"})
    assert set(rename["changes"]) == {main_path.as_uri(), math_path.as_uri()}
    assert all(edit["newText"] == "sum" for edits in rename["changes"].values() for edit in edits)


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

    program = "fn main() {\n    let x: Int = \"text\"\n}\n"

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

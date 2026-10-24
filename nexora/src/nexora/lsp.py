"""The language server of NEXORA: it speaks LSP over stdio.

It does not re-implement the language. Every answer comes from the same stages
the command line uses: the lexer, the parser and the checker (`pipeline.analyze`),
so the diagnostics the editor shows are the ones `nex check` gives, with the same
codes and the same texts.

What it offers:

* diagnostics, with the code, the position and the hint of each problem;
* completion, with the keywords, the built-in functions and the names in scope;
* hover, with the type of a value and the signature of a function;
* go to definition, find the references and rename a symbol;
* the symbols of the document and the signature of the function being called;
* formatting, whole document or a range, with the formatter of the language.

It is written with the standard library only: a server that needs no install
step is a server that always works.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import ast_nodes as ast
from .checker import BUILTINS, CheckedProgram
from .diagnostics import Diagnostic, Source
from .formatter import format_source
from .lexer import tokenize
from .pipeline import Analysis, analyze
from .tokens import KEYWORDS, RESERVED_WORDS, TokenType

# The language this server speaks.
LANGUAGE_ID = "nexora"

# The severity of a diagnostic, by the category the language uses.
_SEVERITY = {
    "syntax": 1,    # Error
    "lexical": 1,
    "type": 1,
    "semantic": 1,
    "contract": 1,
    "runtime": 1,
    "test": 1,
}


def _position(line: int, column: int) -> dict[str, int]:
    """A position of the protocol: it counts from zero."""
    return {"line": max(0, line - 1), "character": max(0, column - 1)}


def _range(span) -> dict[str, dict[str, int]]:
    """The range of a span of the language."""
    return {
        "start": _position(span.line, span.column),
        "end": _position(span.end_line, span.end_column),
    }


def _offset(position: dict[str, int], lines: list[str]) -> tuple[int, int]:
    """The line and the column of a position of the protocol, counted from one."""
    line = position.get("line", 0) + 1
    column = position.get("character", 0) + 1
    if 1 <= line <= len(lines):
        column = min(column, len(lines[line - 1]) + 1)
    return line, column


def _holds(span, line: int, column: int) -> bool:
    """Whether a span of the language holds that position."""
    return span.line == line and span.column <= column < span.end_column


@dataclass
class Document:
    """A file the editor has open."""

    uri: str
    language_id: str
    version: int
    text: str

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n")

    @property
    def source(self) -> Source:
        return Source(self.uri, self.text)


@dataclass
class Server:
    """The state of the server: the open documents and what was analysed."""

    documents: dict[str, Document] = field(default_factory=dict)
    analyses: dict[str, Analysis] = field(default_factory=dict)
    initialized: bool = False

    # Analysis

    def analysis_of(self, document: Document) -> Analysis:
        """The analysis of a document, computed once per version."""
        cached = self.analyses.get(document.uri)
        if cached is not None and cached.source.text == document.text:
            return cached
        result = analyze(document.source, require_main=False)
        self.analyses[document.uri] = result
        return result

    # Diagnostics

    def diagnostics_of(self, document: Document) -> list[dict[str, Any]]:
        """The problems of a document, in the shape of the protocol."""
        analysis = self.analysis_of(document)
        return [_diagnostic(diagnostic) for diagnostic in analysis.diagnostics]

    # Symbols

    def _facts(self, document: Document) -> CheckedProgram | None:
        analysis = self.analysis_of(document)
        return analysis.facts

    def _symbol_at(self, document: Document, line: int, column: int):
        """The symbol that is written at that position, used or declared."""
        facts = self._facts(document)
        if facts is None:
            return None
        for symbol in facts.symbols:
            if _holds(symbol.span, line, column):
                return symbol
            for span in symbol.references:
                if _holds(span, line, column):
                    return symbol
        return None

    def _names_in_scope(self, document: Document, line: int, column: int) -> list[str]:
        """The names a program can use at that position."""
        facts = self._facts(document)
        names: list[str] = []
        if facts is None:
            return names
        for symbol in facts.symbols:
            if symbol.scope is None or symbol.category == "function":
                names.append(symbol.name)
                continue
            # A name is visible from where it was declared.
            scope = symbol.scope
            if scope.line < line or (scope.line == line and scope.column <= column):
                names.append(symbol.name)
        return names

    # Handlers

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self.initialized = True
        return {
            "capabilities": {
                "textDocumentSync": {"openClose": True, "change": 1, "save": {"includeText": True}},
                "completionProvider": {"triggerCharacters": [".", " "]},
                "hoverProvider": True,
                "definitionProvider": True,
                "referencesProvider": True,
                "renameProvider": {"prepareProvider": True},
                "documentSymbolProvider": True,
                "signatureHelpProvider": {"triggerCharacters": ["(", ","]},
                "documentFormattingProvider": True,
                "documentRangeFormattingProvider": True,
                "documentHighlightProvider": True,
                "workspace": {"workspaceFolders": {"supported": True, "changeNotifications": True}},
            },
            "serverInfo": {"name": "nexora-lsp", "version": _version()},
        }

    def did_open(self, params: dict[str, Any]) -> None:
        item = params.get("textDocument", {})
        document = Document(
            uri=item.get("uri", ""),
            language_id=item.get("languageId", LANGUAGE_ID),
            version=item.get("version", 0),
            text=item.get("text", ""),
        )
        self.documents[document.uri] = document
        self.analyses.pop(document.uri, None)

    def did_change(self, params: dict[str, Any]) -> None:
        item = params.get("textDocument", {})
        uri = item.get("uri", "")
        document = self.documents.get(uri)
        if document is None:
            return
        text = item.get("contentChanges", [{}])[-1].get("text", document.text)
        self.documents[uri] = Document(document.uri, document.language_id, item.get("version", document.version), text)
        self.analyses.pop(uri, None)

    def did_close(self, params: dict[str, Any]) -> None:
        uri = params.get("textDocument", {}).get("uri", "")
        self.documents.pop(uri, None)
        self.analyses.pop(uri, None)

    def did_save(self, params: dict[str, Any]) -> None:
        return None

    def completion(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        line, column = _offset(params.get("position", {}), document.lines)
        items: list[dict[str, Any]] = []
        for word in sorted(KEYWORDS):
            items.append({"label": word, "kind": 14, "detail": "keyword", "sortText": f"1{word}"})
        for name, signature in sorted(BUILTINS.items()):
            items.append({
                "label": name,
                "kind": 3,
                "detail": signature.describe(),
                "sortText": f"2{name}",
            })
        for name in sorted(set(self._names_in_scope(document, line, column))):
            items.append({"label": name, "kind": 6, "detail": "in scope", "sortText": f"3{name}"})
        for word in sorted(RESERVED_WORDS):
            items.append({
                "label": word,
                "kind": 14,
                "detail": "reserved word: not implemented yet",
                "sortText": f"4{word}",
            })
        return items

    def hover(self, params: dict[str, Any]) -> dict[str, Any] | None:
        document = self._document(params)
        if document is None:
            return None
        line, column = _offset(params.get("position", {}), document.lines)
        facts = self._facts(document)
        if facts is None:
            return None
        # A function that is being called.
        called = _call_name_at(document, line, column)
        if called is not None:
            function = facts.functions.get(called)
            if function is not None:
                return {"contents": {"kind": "markdown", "value": f"```nexora\n{_signature_of(function, facts)}\n```"}}
            signature = BUILTINS.get(called)
            if signature is not None:
                return {"contents": {"kind": "markdown", "value": f"```nexora\n{signature.describe()}\n```"}}
        symbol = self._symbol_at(document, line, column)
        if symbol is not None:
            detail = symbol.type or "?"
            if symbol.category == "function":
                function = facts.functions.get(symbol.name)
                if function is not None:
                    detail = _signature_of(function, facts)
            return {"contents": {"kind": "markdown", "value": f"```nexora\n{symbol.name}: {detail}\n```"}}
        return None

    def definition(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        line, column = _offset(params.get("position", {}), document.lines)
        symbol = self._symbol_at(document, line, column)
        if symbol is None:
            return []
        return [{"uri": document.uri, "range": _range(symbol.span)}]

    def references(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        line, column = _offset(params.get("position", {}), document.lines)
        symbol = self._symbol_at(document, line, column)
        if symbol is None:
            return []
        spans = [symbol.span, *symbol.references]
        return [{"uri": document.uri, "range": _range(span)} for span in spans]

    def highlight(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        line, column = _offset(params.get("position", {}), document.lines)
        symbol = self._symbol_at(document, line, column)
        if symbol is None:
            return []
        spans = [symbol.span, *symbol.references]
        return [{"range": _range(span), "kind": 1} for span in spans]

    def rename(self, params: dict[str, Any]) -> dict[str, Any] | None:
        document = self._document(params)
        if document is None:
            return None
        line, column = _offset(params.get("position", {}), document.lines)
        symbol = self._symbol_at(document, line, column)
        if symbol is None:
            return None
        new_name = params.get("newName", "")
        if not new_name:
            return None
        spans = [symbol.span, *symbol.references]
        edits = [{"range": _range(span), "newText": new_name} for span in spans]
        return {"changes": {document.uri: edits}}

    def prepare_rename(self, params: dict[str, Any]) -> dict[str, Any] | None:
        document = self._document(params)
        if document is None:
            return None
        line, column = _offset(params.get("position", {}), document.lines)
        symbol = self._symbol_at(document, line, column)
        if symbol is None:
            return None
        return {"range": _range(symbol.span), "placeholder": symbol.name}

    def document_symbol(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        facts = self._facts(document)
        if facts is None:
            return []
        symbols: list[dict[str, Any]] = []
        for function in facts.program.functions:
            symbols.append({
                "name": function.name,
                "kind": 12,
                "range": _range(function.name_span),
                "selectionRange": _range(function.name_span),
                "detail": _return_type_of(function),
            })
        for symbol in facts.symbols:
            if symbol.category == "variable":
                symbols.append({
                    "name": symbol.name,
                    "kind": 13,
                    "range": _range(symbol.span),
                    "selectionRange": _range(symbol.span),
                    "detail": symbol.type or "",
                })
        return symbols

    def signature_help(self, params: dict[str, Any]) -> dict[str, Any] | None:
        document = self._document(params)
        if document is None:
            return None
        facts = self._facts(document)
        if facts is None:
            return None
        line, column = _offset(params.get("position", {}), document.lines)
        name = _call_name_at(document, line, column)
        if name is None:
            return None
        function = facts.functions.get(name)
        if function is not None:
            parameters = [
                {"label": parameter.name, "documentation": _type_text(parameter.type)}
                for parameter in function.params
            ]
            return {
                "signatures": [{"label": _signature_of(function, facts), "parameters": parameters}],
                "activeSignature": 0,
            }
        signature = BUILTINS.get(name)
        if signature is None:
            return None
        parameters = [{"label": label, "documentation": kind or ""} for label, kind in signature.params]
        return {"signatures": [{"label": signature.describe(), "parameters": parameters}], "activeSignature": 0}

    def formatting(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        result = format_source(document.text, document.uri)
        if not result.ok:
            return []
        return [{"range": _whole_range(document), "newText": result.text}]

    def range_formatting(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        area = params.get("range", {})
        start = area.get("start", {}).get("line", 0) + 1
        end = area.get("end", {}).get("line", 0) + 1
        result = format_source(document.text, document.uri)
        if not result.ok:
            return []
        formatted = result.text.split("\n")
        if formatted and formatted[-1] == "":
            formatted.pop()
        return [{
            "range": _range_of_lines(document, start, end),
            "newText": "\n".join(formatted[start - 1:end]),
        }]

    # Helpers

    def _document(self, params: dict[str, Any]) -> Document | None:
        uri = params.get("textDocument", {}).get("uri", "")
        return self.documents.get(uri)


def _version() -> str:
    from .version import __version__

    return __version__


def _diagnostic(diagnostic: Diagnostic) -> dict[str, Any]:
    """A diagnostic of the language, in the shape of the protocol."""
    result: dict[str, Any] = {
        "range": _range(diagnostic.span),
        "severity": _SEVERITY.get(diagnostic.category, 1),
        "code": diagnostic.code,
        "source": "nexora",
        "message": diagnostic.label,
    }
    if diagnostic.hint:
        result["message"] = f"{diagnostic.label}\n\n{diagnostic.hint}"
    return result


def _type_text(reference: ast.TypeRef | None) -> str:
    """The text of a type reference."""
    if reference is None:
        return ""
    if reference.arguments:
        arguments = ", ".join(_type_text(argument) for argument in reference.arguments)
        return f"{reference.name}[{arguments}]"
    return reference.name


def _return_type_of(function: ast.Function) -> str:
    """The type a function gives: Void when it has no 'gives' (decision 0019)."""
    return "Void" if function.return_type is None else _type_text(function.return_type)


def _signature_of(function: ast.Function, facts: CheckedProgram) -> str:
    """The signature of a function, as it is written in the language."""
    parameters = ", ".join(f"{parameter.name}: {_type_text(parameter.type)}" for parameter in function.params)
    if function.return_type is None:
        return f"fn {function.name}({parameters})"
    return f"fn {function.name}({parameters}) gives {_return_type_of(function)}"


def _call_name_at(document: Document, line: int, column: int) -> str | None:
    """The name of the function whose call is being written at that position.

    A call is a name followed by its parenthesis, so the parenthesis is what
    tells a call from a value.
    """
    tokens, _ = tokenize(document.source)
    for index, token in enumerate(tokens):
        if token.type is not TokenType.IDENT:
            continue
        span = token.span
        if span.line != line or not (span.column <= column < span.end_column):
            continue
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if following is not None and following.type is TokenType.LPAREN and following.span.line == line:
            return token.lexeme
        return None
    return None


def _type_names(facts: CheckedProgram) -> dict[str, str]:
    """The declared types, by name."""
    names = {name: "record" for name in facts.records}
    names.update({name: "refined type" for name in facts.refined})
    return names


def _whole_range(document: Document) -> dict[str, dict[str, int]]:
    lines = document.lines
    return {
        "start": {"line": 0, "character": 0},
        "end": {"line": max(0, len(lines) - 1), "character": len(lines[-1]) if lines else 0},
    }


def _range_of_lines(document: Document, start_line: int, end_line: int) -> dict[str, dict[str, int]]:
    lines = document.lines
    last = max(0, min(len(lines), end_line) - 1)
    return {
        "start": {"line": max(0, start_line - 1), "character": 0},
        "end": {"line": last, "character": len(lines[last]) if lines else 0},
    }


# The transport: the protocol of the language server, over standard input and output.

class Connection:
    """Reads the messages of the protocol and writes the answers."""

    def __init__(self, reader=None, writer=None) -> None:
        self.reader = reader if reader is not None else sys.stdin.buffer
        self.writer = writer if writer is not None else sys.stdout.buffer

    def read(self) -> dict[str, Any] | None:
        """The next message, or None when the input ends."""
        headers: dict[str, str] = {}
        while True:
            line = self.reader.readline()
            if not line:
                return None
            text = line.decode("ascii", "replace").strip()
            if not text:
                break
            name, _, value = text.partition(":")
            headers[name.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = b""
        while len(body) < length:
            chunk = self.reader.read(length - len(body))
            if not chunk:
                return None
            body += chunk
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def write(self, message: dict[str, Any]) -> None:
        """A message, with the header the protocol asks for."""
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        self.writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
        self.writer.write(body)
        self.writer.flush()


def _methods(server: Server) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """The methods of the protocol, and what each one answers."""
    return {
        "initialize": server.initialize,
        "initialized": lambda params: None,
        "shutdown": lambda params: None,
        "exit": lambda params: None,
        "textDocument/didOpen": server.did_open,
        "textDocument/didChange": server.did_change,
        "textDocument/didClose": server.did_close,
        "textDocument/didSave": server.did_save,
        "textDocument/completion": server.completion,
        "textDocument/hover": server.hover,
        "textDocument/definition": server.definition,
        "textDocument/references": server.references,
        "textDocument/rename": server.rename,
        "textDocument/prepareRename": server.prepare_rename,
        "textDocument/documentSymbol": server.document_symbol,
        "textDocument/signatureHelp": server.signature_help,
        "textDocument/formatting": server.formatting,
        "textDocument/rangeFormatting": server.range_formatting,
        "textDocument/documentHighlight": server.highlight,
    }


def serve(reader=None, writer=None) -> int:
    """The loop of the server: read a message, answer it, publish the diagnostics."""
    connection = Connection(reader, writer)
    server = Server()
    methods = _methods(server)
    while True:
        message = connection.read()
        if message is None:
            return 0
        method = message.get("method", "")
        identifier = message.get("id")
        params = message.get("params", {})
        if method == "exit":
            return 0
        handler = methods.get(method)
        if handler is None:
            if identifier is not None:
                connection.write({"jsonrpc": "2.0", "id": identifier, "result": None})
            continue
        try:
            result = handler(params)
        except Exception as error:  # noqa: BLE001 - the server answers, it does not fall.
            if identifier is not None:
                connection.write({
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "error": {"code": -32603, "message": f"{type(error).__name__}: {error}"},
                })
            continue
        if identifier is not None:
            connection.write({"jsonrpc": "2.0", "id": identifier, "result": result})
        # The diagnostics of the documents that changed.
        if method in ("textDocument/didOpen", "textDocument/didChange", "textDocument/didSave"):
            uri = params.get("textDocument", {}).get("uri", "")
            document = server.documents.get(uri)
            if document is not None:
                connection.write({
                    "jsonrpc": "2.0",
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": uri,
                        "version": document.version,
                        "diagnostics": server.diagnostics_of(document),
                    },
                })


def main() -> int:
    """The entry point: `python -m nexora.lsp`."""
    return serve()


if __name__ == "__main__":
    sys.exit(main())

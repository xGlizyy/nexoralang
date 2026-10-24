"""`nex migrate`: the edits that move a 0.11 file to the syntax of 0.12 (decision 0019, section 8).

This module only computes. It receives the text of one file and what the frozen 0.11 front
end (`legacy011`) made of it, and answers with the edits of 8.5 or with the refusals of 8.6.
Reading and writing files is the CLI's job.

The edits never re-render the program: each one is a range of the original text and its
replacement, and every character outside them is kept (G2). Positions are offsets in the text,
counted in characters, with the line endings the lexer reads: `\\r\\n`, `\\n` or a lone `\\r`.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

from .legacy011 import ast_nodes as ast
from .legacy011.tokens import Token, TokenType

# The words that become keywords in 0.12 (decision 0019, section 9).
NEW_KEYWORDS = ("needs", "gives", "promises", "keeps", "shrinks", "trust")
# E3: the clause words of 0.11 and their 0.12 words.
CLAUSE_WORDS = {"requires": "needs", "ensures": "promises", "invariant": "keeps", "decreases": "shrinks"}
# E4: the functions of `Option` and `Result` that are renamed.
RENAMED_FUNCTIONS = {"unwrap": "value", "unwrap_or": "value_or"}

_LINE = re.compile(r"[^\r\n]*(\r\n|\n|\r|$)")


@dataclass(frozen=True)
class Edit:
    """One edit of 8.5.2: the range `[start, end)` of the original text and what replaces it."""

    start: int
    end: int
    text: str
    kind: str   # "E1" … "E7"


@dataclass(frozen=True)
class Refusal:
    """A case of 8.6: why the file cannot be migrated without a choice, and where."""

    line: int
    column: int
    message: str


@dataclass(frozen=True)
class FilePlan:
    edits: tuple[Edit, ...]
    refusals: tuple[Refusal, ...]


class _Text:
    """The text with its lines, to turn the positions of the lexer into offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        # (start of the line, end of its content, end of its line ending), for every line.
        self.lines: list[tuple[int, int, int]] = []
        for match in _LINE.finditer(text):
            if match.start() == len(text) and self.lines and match.end() == match.start():
                break
            self.lines.append((match.start(), match.start() + len(match.group(0)) - len(match.group(1)),
                               match.end()))

    def offset(self, line: int, column: int) -> int:
        return self.lines[line - 1][0] + column - 1

    def start_of(self, token: Token) -> int:
        return self.offset(token.span.line, token.span.column)

    def end_of(self, token: Token) -> int:
        return self.offset(token.span.end_line, token.span.end_column)

    def indentation(self, line: int) -> str:
        start, content_end, _ = self.lines[line - 1]
        content = self.text[start:content_end]
        return content[: len(content) - len(content.lstrip(" \t"))]

    def ending(self, line: int) -> str:
        _, content_end, end = self.lines[line - 1]
        return self.text[content_end:end]


def plan(text: str, tokens: tuple[Token, ...], program: ast.Program) -> FilePlan:
    """The edits of one file, or the reasons it cannot be migrated.

    `tokens` and `program` are what the frozen 0.11 front end made of `text`, a file that
    passed the 0.11 check (G1).
    """
    return _Planner(text, tokens, program).run()


class _Planner:
    def __init__(self, text: str, tokens: tuple[Token, ...], program: ast.Program) -> None:
        self.text = _Text(text)
        self.tokens = [t for t in tokens if t.type not in (TokenType.NEWLINE, TokenType.EOF)]
        self.program = program
        self.edits: list[Edit] = []
        self.refusals: list[Refusal] = []

    # Tokens

    def _token_at(self, line: int, column: int) -> int:
        for index, token in enumerate(self.tokens):
            if (token.span.line, token.span.column) == (line, column):
                return index
        raise LookupError(f"no token at {line}:{column}")

    def _token_ending_at(self, line: int, column: int) -> int:
        for index, token in enumerate(self.tokens):
            if (token.span.end_line, token.span.end_column) == (line, column):
                return index
        raise LookupError(f"no token ending at {line}:{column}")

    def _refuse(self, token: Token, message: str) -> None:
        self.refusals.append(Refusal(token.span.line, token.span.column, message))

    # The plan

    def run(self) -> FilePlan:
        self._names()
        for function in self.program.functions:
            self._function(function)
        for node in _walk(self.program):
            if isinstance(node, (ast.While, ast.For)):
                self._loop(node)
            elif isinstance(node, ast.Call):
                self._call(node)
        if self.refusals:
            return FilePlan((), tuple(sorted(self.refusals, key=lambda r: (r.line, r.column))))
        return FilePlan(tuple(_ordered(self.edits)), ())

    def _names(self) -> None:
        # 8.6: a name that is a keyword in 0.12 is the person's to change.
        for token in self.tokens:
            if token.type is TokenType.IDENT and token.lexeme in NEW_KEYWORDS:
                self._refuse(token, f"'{token.lexeme}' is a keyword from 0.12: rename it")
        for declaration in self.program.imports:
            stem = declaration.path.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".nex")
            if stem in NEW_KEYWORDS:
                self.refusals.append(Refusal(
                    declaration.path_span.line, declaration.path_span.column,
                    f"'{stem}' is a keyword from 0.12: rename the file '{stem}.nex'",
                ))
            elif stem in ("Option", "Result"):
                # E4 renames `Option.unwrap` only where it is the built-in type; a module with
                # that name would make the call ambiguous.
                self.refusals.append(Refusal(
                    declaration.path_span.line, declaration.path_span.column,
                    f"A module named '{stem}' hides the built-in type: rename the file '{stem}.nex'",
                ))

    def _function(self, function: ast.Function) -> None:
        fn_index = self._token_at(function.span.line, function.span.column)
        brace_index = self._token_at(function.body.span.line, function.body.span.column)
        arrow_index = next(i for i in range(fn_index, brace_index) if self.tokens[i].type is TokenType.ARROW)
        arrow = self.tokens[arrow_index]
        returns = function.return_type
        void = returns.name == "Void" and returns.qualifier is None and not returns.arguments
        type_end = self.tokens[self._token_ending_at(returns.span.end_line, returns.span.end_column)]
        if void:
            closing = self.tokens[arrow_index - 1]
            self.edits.append(Edit(self.text.end_of(closing), self.text.end_of(type_end), "", "E2"))
        else:
            self.edits.append(Edit(self.text.start_of(arrow), self.text.end_of(arrow), "gives", "E1"))
        for contract in function.contracts:
            self._clause_word(contract.span)
        clauses = sorted([*function.contracts, *function.examples], key=lambda c: (c.span.line, c.span.column))
        first = self.tokens[fn_index]
        if fn_index > 0 and self.tokens[fn_index - 1].type is TokenType.PUB:
            first = self.tokens[fn_index - 1]
        if clauses:
            self._header(brace_index, clauses, first.span.line)
        else:
            self._no_header(brace_index, type_end)

    def _loop(self, loop: ast.While | ast.For) -> None:
        if not loop.clauses:
            return
        for clause in loop.clauses:
            self._clause_word(clause.span)
        brace_index = self._token_at(loop.body.span.line, loop.body.span.column)
        clauses = sorted(loop.clauses, key=lambda c: (c.span.line, c.span.column))
        self._header(brace_index, clauses, loop.span.line)

    def _clause_word(self, span) -> None:
        keyword = self.tokens[self._token_at(span.line, span.column)]
        if keyword.lexeme in CLAUSE_WORDS:
            self.edits.append(Edit(self.text.start_of(keyword), self.text.end_of(keyword),
                                   CLAUSE_WORDS[keyword.lexeme], "E3"))

    def _header(self, brace_index: int, clauses: list, signature_line: int) -> None:
        brace = self.tokens[brace_index]
        first = self.tokens[self._token_at(clauses[0].span.line, clauses[0].span.column)]
        if first.span.line == brace.span.line:
            self._refuse(first, f"Put '{first.lexeme}' on its own line, then run nex migrate again")
            return
        last_index = self._token_ending_at(clauses[-1].span.end_line, clauses[-1].span.end_column)
        last = self.tokens[last_index]
        following = self.tokens[last_index + 1]
        if following.span.line == last.span.end_line:
            keyword = self.tokens[self._token_at(clauses[-1].span.line, clauses[-1].span.column)]
            self._refuse(keyword, f"Put '{keyword.lexeme}' on its own line, then run nex migrate again")
            return
        self.edits.append(self._remove_brace(brace_index))
        line = last.span.end_line
        insertion = self.text.lines[line - 1][2]
        self.edits.append(Edit(insertion, insertion,
                               self.text.indentation(signature_line) + "{" + self.text.ending(line), "E6"))

    def _remove_brace(self, brace_index: int) -> Edit:
        brace = self.tokens[brace_index]
        before = self.tokens[brace_index - 1]
        if before.span.end_line == brace.span.line:
            return Edit(self.text.end_of(before), self.text.end_of(brace), "", "E5a")
        start, content_end, end = self.text.lines[brace.span.line - 1]
        rest = self.text.text[self.text.end_of(brace):content_end]
        if not rest.strip(" \t"):
            return Edit(start, end, "", "E5b")
        comment = self.text.end_of(brace) + (len(rest) - len(rest.lstrip(" \t")))
        return Edit(self.text.start_of(brace), comment, "", "E5c")

    def _no_header(self, brace_index: int, type_end: Token) -> None:
        brace = self.tokens[brace_index]
        before = self.tokens[brace_index - 1]
        if before.span.end_line == brace.span.line:
            return
        start, content_end, end = self.text.lines[brace.span.line - 1]
        rest = self.text.text[self.text.end_of(brace):content_end].strip(" \t")
        if rest.startswith("//"):
            self._refuse(brace, "Move this comment, then run nex migrate again")
            return
        if rest:
            self._refuse(brace, "Put the first statement on its own line, then run nex migrate again")
            return
        self.edits.append(Edit(start, end, "", "E7"))
        insertion = self.text.end_of(type_end)
        self.edits.append(Edit(insertion, insertion, " {", "E7"))

    def _call(self, call: ast.Call) -> None:
        if call.qualifier not in ("Option", "Result"):
            return
        name = call.callee.rsplit(".", 1)[-1]
        if name not in RENAMED_FUNCTIONS:
            return
        span = call.callee_span
        token = self.tokens[self._token_ending_at(span.end_line, span.end_column)]
        self.edits.append(Edit(self.text.start_of(token), self.text.end_of(token), RENAMED_FUNCTIONS[name], "E4"))


def _walk(node):
    """Every node of the tree, in no particular order."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, (list, tuple)):
            stack.extend(current)
            continue
        if not isinstance(current, ast.Node):
            continue
        yield current
        for field in dataclasses.fields(current):
            value = getattr(current, field.name)
            if isinstance(value, (ast.Node, list, tuple)):
                stack.append(value)


def _ordered(edits: list[Edit]) -> list[Edit]:
    """The edits sorted by position (8.5.3). An insertion where a deletion ends goes after it."""
    ordered = sorted(edits, key=lambda e: (e.start, e.end))
    # Adjacent pairs: the second list is one shorter on purpose.
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.end > current.start:
            # The edits of 8.5 never overlap; if they do, the tool has a defect (code 70).
            raise AssertionError(f"edits overlap: {previous} and {current}")
    return ordered


def apply(text: str, edits: tuple[Edit, ...]) -> str:
    """The text with the edits applied, in their order."""
    parts, position = [], 0
    for edit in edits:
        parts.append(text[position:edit.start])
        parts.append(edit.text)
        position = edit.end
    parts.append(text[position:])
    return "".join(parts)


def kept_outside(text: str, edits: tuple[Edit, ...], output: str) -> bool:
    """G2 (8.5.4): every character outside the edits is in the output, unchanged and in order."""
    position = out = 0
    for edit in edits:
        gap = text[position:edit.start]
        if output[out:out + len(gap)] != gap:
            return False
        out += len(gap)
        if output[out:out + len(edit.text)] != edit.text:
            return False
        out += len(edit.text)
        position = edit.end
    return output[out:] == text[position:]

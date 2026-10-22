"""The formatter of NEXORA: it rewrites a program with a canonical shape.

It works on the tokens of the real lexer, never on the raw text: the same words
and the same literals come out, only their spacing and their indentation
change. A program that checks keeps checking, and formatting it twice gives
the same result as formatting it once.

The language is written line by line, so the formatter never joins two lines
nor splits one: it re-indents each line and puts the canonical spaces between
the tokens of that line. Comments are kept where they are, at the indentation
of their line.

This is what the language server of the editor uses (see `lsp.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Source
from .lexer import tokenize
from .tokens import Token, TokenType

# How far a block is indented.
INDENT = "    "

# The tokens after which no space is written.
_NO_SPACE_AFTER = frozenset({TokenType.LPAREN, TokenType.LBRACKET, TokenType.DOT})
# The tokens before which no space is written.
_NO_SPACE_BEFORE = frozenset({
    TokenType.RPAREN, TokenType.RBRACKET, TokenType.COMMA, TokenType.DOT, TokenType.COLON, TokenType.LPAREN,
})
# The tokens that are written as they are, with a space on both sides.
_BINARY = frozenset({
    TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH, TokenType.EQUAL,
    TokenType.EQUAL_EQUAL, TokenType.NOT_EQUAL, TokenType.LESS, TokenType.LESS_EQUAL,
    TokenType.GREATER, TokenType.GREATER_EQUAL, TokenType.ARROW,
})
# The tokens after which a space is always written.
_SPACE_AFTER = frozenset({
    TokenType.FN, TokenType.LET, TokenType.VAR, TokenType.RETURN, TokenType.IF, TokenType.ELSE,
    TokenType.WHILE, TokenType.FOR, TokenType.IN, TokenType.AND, TokenType.OR, TokenType.NOT,
    TokenType.REQUIRES, TokenType.ENSURES, TokenType.EXAMPLE, TokenType.INVARIANT, TokenType.DECREASES,
    TokenType.USES, TokenType.TYPE, TokenType.WHERE,
})
# The tokens that end a statement and are followed by nothing.
_STATEMENT_END = frozenset({TokenType.RBRACE, TokenType.RBRACKET, TokenType.RPAREN})


@dataclass(frozen=True)
class FormatResult:
    """The formatted text and whether the program could be read at all."""

    text: str
    ok: bool


def format_source(source: str, filename: str = "program.nex") -> FormatResult:
    """The program written with the canonical shape.

    A program with lexical errors is returned unchanged: the formatter cannot
    know what the text meant, and rewriting it anyway could change what it
    means.
    """
    tokens, diagnostics = tokenize(Source(filename, source))
    if diagnostics:
        return FormatResult(source, False)
    return FormatResult(_render(tokens), True)


def format_range(source: str, start_line: int, end_line: int, filename: str = "program.nex") -> FormatResult:
    """Only the lines between `start_line` and `end_line`, both counted from 1.

    The whole program is formatted first, so the indentation of the chosen
    lines is the one they have in the program, and only those lines are
    written back: the rest of the file is left as it was.
    """
    lines = source.split("\n")
    if start_line < 1 or end_line > len(lines) or start_line > end_line:
        return FormatResult(source, False)
    result = format_source(source, filename)
    if not result.ok:
        return FormatResult(source, False)
    formatted = result.text.split("\n")
    if formatted and formatted[-1] == "":
        formatted.pop()
    return FormatResult("\n".join(lines[:start_line - 1] + formatted[start_line - 1:end_line] + lines[end_line:]), True)


def _render(tokens: list[Token]) -> str:
    """The text with the canonical shape."""
    lines = _lines(tokens)
    rendered = [_render_line(line, depth) for line, depth in lines]
    text = "\n".join(rendered)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _lines(tokens: list[Token]) -> list[tuple[list[Token], int]]:
    """The tokens of each line, with the depth of the block they belong to."""
    grouped: list[list[Token]] = []
    current: list[Token] = []
    for token in tokens:
        if token.type is TokenType.NEWLINE:
            if current:
                grouped.append(current)
                current = []
            continue
        if token.type is TokenType.EOF:
            break
        current.append(token)
    if current:
        grouped.append(current)
    lines: list[tuple[list[Token], int]] = []
    depth = 0
    for line in grouped:
        # A line that closes a block is written one step back.
        own = depth
        if line and line[0].type is TokenType.RBRACE:
            own = max(0, depth - 1)
        lines.append((line, own))
        for token in line:
            if token.type is TokenType.LBRACE:
                depth += 1
            elif token.type is TokenType.RBRACE:
                depth = max(0, depth - 1)
    return lines


def _render_line(tokens: list[Token], depth: int) -> str:
    """One line, with its tokens separated the canonical way."""
    parts: list[str] = []
    for index, token in enumerate(tokens):
        text = token.lexeme
        if token.type is TokenType.STRING:
            text = _literal(token)
        if parts:
            if _needs_space(tokens, index, parts):
                parts.append(" ")
        parts.append(text)
    body = "".join(parts)
    if not body.strip():
        return ""
    return INDENT * depth + body


def _literal(token: Token) -> str:
    """The text of a literal, as it was written.

    The lexer keeps the source of a text literal, with its quotes and its
    escapes, so there is nothing to rebuild: what the program had is what the
    program gets.
    """
    return token.lexeme


def _needs_space(tokens: list[Token], index: int, parts: list[str]) -> bool:
    """Whether a space goes between the token written last and this one."""
    previous = tokens[index - 1]
    current = tokens[index]
    if previous.type in _NO_SPACE_AFTER or current.type in _NO_SPACE_BEFORE:
        return False
    if current.type is TokenType.LBRACKET and previous.type is TokenType.IDENT:
        # The arguments of a type, as in `List[Text]`: they follow the name.
        return False
    if current.type is TokenType.LBRACE:
        # A brace that opens a block is written after a space; one that opens a
        # record type is written the same way.
        return True
    if previous.type is TokenType.LBRACE:
        return True
    if previous.type in _BINARY or current.type in _BINARY:
        # A minus that follows something that cannot be an operand is unary, and
        # it sticks to the number that follows it.
        if previous.type is TokenType.MINUS and _is_unary(tokens, index - 1):
            return False
        return True
    if previous.type in _SPACE_AFTER or current.type in _SPACE_AFTER:
        return True
    if previous.type is TokenType.LPAREN or current.type is TokenType.RPAREN:
        return False
    if previous.type is TokenType.LBRACKET or current.type is TokenType.RBRACKET:
        return False
    if previous.type is TokenType.COMMA:
        return True
    if current.type is TokenType.COMMA:
        return False
    if current.type is TokenType.COLON:
        return False
    if previous.type is TokenType.COLON:
        return True
    return True


def _is_unary(tokens: list[Token], index: int) -> bool:
    """Whether the operator at `index` is unary: nothing that could be an operand goes before it."""
    if index == 0:
        return True
    previous = tokens[index - 1]
    if previous.type in (TokenType.IDENT, TokenType.INT, TokenType.FLOAT, TokenType.STRING):
        return False
    if previous.type in (TokenType.TRUE, TokenType.FALSE):
        return False
    if previous.type in (TokenType.RPAREN, TokenType.RBRACKET, TokenType.RBRACE):
        return False
    return True


__all__ = ["FormatResult", "format_range", "format_source"]

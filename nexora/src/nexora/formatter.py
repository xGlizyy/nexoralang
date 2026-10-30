"""The formatter of NEXORA: it rewrites a program with a canonical shape.

It works on the tokens of the real lexer, never on the raw text: the same words
and the same literals come out, only their spacing and their indentation
change. A program that checks keeps checking, and formatting it twice gives
the same result as formatting it once.

The language is written line by line, so the formatter works on each line of
the text as it is: it never joins two lines nor splits one, and the result has
the same lines as the source, each with its own line ending. It re-indents each
line and puts the canonical spaces between the tokens of that line. The lexer
does not keep comments, so they are taken from the text: a comment stays on its
line, after the code of that line, and a blank line stays blank. If a line holds
anything that is neither a token nor a comment, the program is not formatted.

This is what the language server of the editor uses (see `lsp.py`).
"""

from __future__ import annotations

import re
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
    TokenType.GREATER, TokenType.GREATER_EQUAL, TokenType.ARROW, TokenType.FAT_ARROW,
})
# The tokens after which a space is always written.
_SPACE_AFTER = frozenset({
    TokenType.FN, TokenType.LET, TokenType.VAR, TokenType.RETURN, TokenType.IF, TokenType.ELSE,
    TokenType.WHILE, TokenType.FOR, TokenType.IN, TokenType.AND, TokenType.OR, TokenType.NOT,
    TokenType.NEEDS, TokenType.GIVES, TokenType.PROMISES, TokenType.TRUST, TokenType.EXAMPLE, TokenType.KEEPS,
    TokenType.SHRINKS, TokenType.USES, TokenType.TYPE, TokenType.WHERE,
})
# The tokens that end a statement and are followed by nothing.
_STATEMENT_END = frozenset({TokenType.RBRACE, TokenType.RBRACKET, TokenType.RPAREN})
# A line and its ending, with the same line breaks the lexer reads: `\r\n`, `\n` or a lone `\r`.
_LINE = re.compile(r"([^\r\n]*)(\r\n|\n|\r|$)")
# The tokens that open and close a group whose lines go one step further in.
_OPEN_GROUP = frozenset({TokenType.LPAREN, TokenType.LBRACKET})
_CLOSE_GROUP = frozenset({TokenType.RPAREN, TokenType.RBRACKET})
# The tokens that start the head of a function or of a loop. When that line does not end with
# `{`, the lines of its header follow, one step further in, up to the `{` alone (decision 0019).
_HEADS = frozenset({TokenType.FN, TokenType.WHILE, TokenType.FOR})
# The clauses that can have a name: `needs name: condition` (decision 0019).
_CLAUSES = frozenset({TokenType.NEEDS, TokenType.PROMISES, TokenType.TRUST, TokenType.KEEPS, TokenType.SHRINKS})


@dataclass(frozen=True)
class FormatResult:
    """The formatted text and whether the program could be read at all."""

    text: str
    ok: bool


def format_source(source: str, filename: str = "program.nex") -> FormatResult:
    """The program written with the canonical shape.

    A program with lexical errors is returned unchanged: the formatter cannot
    know what the text meant, and rewriting it anyway could change what it
    means. So is a program with a line it cannot account for, rather than lose
    what is on it.
    """
    tokens, diagnostics = tokenize(Source(filename, source))
    if diagnostics:
        return FormatResult(source, False)
    text = _render(source, tokens)
    if text is None:
        return FormatResult(source, False)
    return FormatResult(text, True)


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


def _render(source: str, tokens: list[Token]) -> str | None:
    """The text with the canonical shape, or None if a line holds something it cannot place."""
    by_line: dict[int, list[Token]] = {}
    for token in tokens:
        if token.type not in (TokenType.NEWLINE, TokenType.EOF):
            by_line.setdefault(token.span.line, []).append(token)

    out: list[str] = []
    depth = 0   # Blocks open: `{`.
    group = 0   # Parentheses and brackets open: `(` and `[`.
    header = 0  # 1 between the head of a function or a loop and the `{` of its body.
    for number, (text, ending) in enumerate(_physical_lines(source), start=1):
        line = by_line.get(number, [])
        if header and line and line[0].type is TokenType.LBRACE:
            # The `{` alone after the header goes back to the line of the head.
            header = 0
        own = depth + header
        if line and line[0].type is TokenType.RBRACE:
            # A line that closes a block is written one step back.
            own = max(0, depth - 1)
        elif group > 0 and not (line and line[0].type in _CLOSE_GROUP):
            # A line that continues an open group goes one step further in.
            own = depth + header + 1
        if line:
            # Everything after the last token is whitespace or a comment: a comment
            # runs to the end of the line, so none can be between two tokens.
            rest = text[line[-1].span.end_column - 1:].strip()
            if rest and not rest.startswith("//"):
                return None
            rendered = _render_line(line, own) + (" " + rest if rest else "")
        else:
            rest = text.strip()
            if rest and not rest.startswith("//"):
                return None
            rendered = INDENT * own + rest if rest else ""
        out.append(rendered + ending)
        for token in line:
            if token.type is TokenType.LBRACE:
                depth += 1
            elif token.type is TokenType.RBRACE:
                depth = max(0, depth - 1)
            elif token.type in _OPEN_GROUP:
                group += 1
            elif token.type in _CLOSE_GROUP:
                group = max(0, group - 1)
        if _opens_a_header(line) and group == 0:
            header = 1

    result = "".join(out)
    if result and not result.endswith(("\n", "\r")):
        result += "\n"
    return result


def _opens_a_header(line: list[Token]) -> bool:
    """Whether a line is the head of a function or a loop whose header follows on the next lines:
    `fn`, `pub fn`, `while` or `for`, without the `{` of its body at the end."""
    if not line or line[-1].type is TokenType.LBRACE:
        return False
    first = line[1] if line[0].type is TokenType.PUB and len(line) > 1 else line[0]
    return first.type in _HEADS and (line[0].type is not TokenType.PUB or first.type is TokenType.FN)


def _physical_lines(source: str) -> list[tuple[str, str]]:
    """Each line of the text and its ending, as the lexer counts them; the last ending may be ""."""
    lines = [(match.group(1), match.group(2)) for match in _LINE.finditer(source)]
    # The pattern also matches the empty text after the last line ending.
    if lines and lines[-1] == ("", ""):
        lines.pop()
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
    named_clause = index >= 3 and tokens[index - 3].type in _CLAUSES
    if current.type is TokenType.LPAREN and previous.type is TokenType.COLON and named_clause:
        # The condition of a named clause, `needs ok: (x > 0 and`: the name is followed by a
        # space, as the type of a parameter is (decision 0019). Every other '(' keeps its shape.
        return True
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

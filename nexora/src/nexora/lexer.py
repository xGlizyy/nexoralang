"""Lexer: turns source text into tokens.

Nothing is skipped silently: every character is either part of a token, whitespace,
a comment, or reported as an error.
"""

from __future__ import annotations

import math

from .diagnostics import MAX_DIAGNOSTICS, Diagnostic, Source, Span
from .tokens import KEYWORDS, RESERVED_WORDS, STATEMENT_KEYWORDS, Token, TokenType
from .values import INT_MAX

# A set, not a string: `"" in "0123"` is true in Python, and "" is what _peek returns at the end.
_DIGITS = frozenset("0123456789")
_INT_MAX_DIGITS = len(str(INT_MAX))
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "{": "{"}
_SINGLE = {
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ",": TokenType.COMMA,
    ":": TokenType.COLON,
    # A '.' inside a number ("1.5") is read with the number. Any other '.' is this token, which is
    # only valid in a qualified call such as Text.length(s) (decision 0011, 3.4).
    ".": TokenType.DOT,
    "=": TokenType.EQUAL,
    "+": TokenType.PLUS,
    "*": TokenType.STAR,
    "<": TokenType.LESS,
    ">": TokenType.GREATER,
}
# Two-character operators, tried before the single-character ones.
_DOUBLE = {
    "->": TokenType.ARROW,
    "==": TokenType.EQUAL_EQUAL,
    "!=": TokenType.NOT_EQUAL,
    "<=": TokenType.LESS_EQUAL,
    ">=": TokenType.GREATER_EQUAL,
}
_CHARACTER_HINTS = {
    ";": "Statements end at the end of the line; remove the ';'.",
    "'": 'Text is written with double quotes: "text".',
    "!": "Negation is written 'not', and 'different from' is written '!='.",
    "&": "The logical operators are the words 'and', 'or' and 'not'.",
    "|": "The logical operators are the words 'and', 'or' and 'not'.",
}


def _is_name_start(char: str) -> bool:
    return char.isascii() and (char.isalpha() or char == "_")


def _is_name_part(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


def _show(char: str) -> str:
    return f"'{char}'" if char.isprintable() else f"U+{ord(char):04X}"


class Lexer:
    def __init__(self, source: Source) -> None:
        self._text = source.text
        self._pos = 0
        self._line = 1
        self._column = 1
        # Line breaks inside parentheses do not end a statement.
        self._paren_depth = 0
        # Position of the most recent line break that was skipped because it was inside
        # parentheses and directly precedes the token being read (None otherwise).
        self._skipped_newline: Span | None = None
        self._tokens: list[Token] = []
        self._diagnostics: list[Diagnostic] = []

    def tokenize(self) -> tuple[list[Token], list[Diagnostic]]:
        """Returns the tokens (always ending in EOF) and the lexical errors found."""
        # A file that is not NEXORA at all (a binary file, for instance) would otherwise produce
        # one error per character: lexing stops once the limit is reached.
        while self._pos < len(self._text) and len(self._diagnostics) < MAX_DIAGNOSTICS:
            self._scan()
        self._add(TokenType.EOF, "", self._here(0))
        return self._tokens, self._diagnostics

    # Helpers

    def _peek(self, offset: int = 0) -> str:
        index = self._pos + offset
        return self._text[index] if index < len(self._text) else ""

    def _here(self, length: int) -> Span:
        return Span(self._line, self._column, self._line, self._column + length)

    def _advance(self, count: int = 1) -> None:
        self._pos += count
        self._column += count

    def _add(self, kind: TokenType, lexeme: str, span: Span, value=None) -> None:
        self._tokens.append(Token(kind, lexeme, span, value))
        self._skipped_newline = None

    def _error(self, code: str, label: str, span: Span, hint: str | None = None) -> None:
        self._diagnostics.append(Diagnostic(code, label, span, hint))

    # Scanning

    def _scan(self) -> None:
        char = self._peek()

        if char in " \t":
            self._advance()
        elif char in "\r\n":
            self._newline()
        elif char == "/" and self._peek(1) == "/":
            while self._peek() not in ("", "\r", "\n"):
                self._advance()
        elif char in _DIGITS:
            self._number()
        elif char == '"':
            self._string()
        elif _is_name_start(char):
            self._name()
        elif char + self._peek(1) in _DOUBLE:
            pair = char + self._peek(1)
            self._add(_DOUBLE[pair], pair, self._here(2))
            self._advance(2)
        elif char == "-":
            self._add(TokenType.MINUS, char, self._here(1))
            self._advance()
        elif char == "/":
            self._add(TokenType.SLASH, char, self._here(1))
            self._advance()
        elif char in _SINGLE:
            if char == "(":
                self._paren_depth += 1
            elif char == ")":
                self._paren_depth = max(0, self._paren_depth - 1)
            elif char in "{}":
                # Braces never appear inside parentheses, so one of them means a ')' is missing.
                self._end_unclosed_line()
            self._add(_SINGLE[char], char, self._here(1))
            self._advance()
        else:
            hint = _CHARACTER_HINTS.get(char)
            if hint is None and char.isalpha():
                hint = "Names use the letters a-z and A-Z, digits and '_'."
            self._error("E1001", f"{_show(char)} is not part of NEXORA syntax", self._here(1), hint)
            self._advance()

    def _newline(self) -> None:
        span = self._here(1)
        self._pos += 2 if self._text.startswith("\r\n", self._pos) else 1
        self._line += 1
        self._column = 1
        # A run of blank lines is a single statement separator.
        if self._paren_depth > 0:
            self._skipped_newline = span
        elif self._tokens and self._tokens[-1].type is not TokenType.NEWLINE:
            self._add(TokenType.NEWLINE, "", span)

    def _end_unclosed_line(self) -> None:
        """Called on a token that cannot be inside parentheses. If some are still open, a ')'
        is missing: the statement is ended at the line break that was skipped, so the parser
        reports the error on the right line and can still read the lines that follow."""
        if self._paren_depth > 0 and self._skipped_newline is not None:
            self._add(TokenType.NEWLINE, "", self._skipped_newline)
        self._paren_depth = 0

    def _name(self) -> None:
        start, span_start = self._pos, self._here(0)
        while _is_name_part(self._peek()):
            self._advance()
        word = self._text[start:self._pos]
        span = span_start.to(self._here(0))
        if word in STATEMENT_KEYWORDS:
            # These cannot appear inside parentheses either.
            self._end_unclosed_line()
        if word in KEYWORDS:
            self._add(KEYWORDS[word], word, span)
        elif word in RESERVED_WORDS:
            self._add(TokenType.RESERVED, word, span)
        else:
            self._add(TokenType.IDENT, word, span)

    def _digits(self) -> None:
        while self._peek() in _DIGITS or self._peek() == "_":
            self._advance()

    def _number(self) -> None:
        start, span_start = self._pos, self._here(0)
        self._digits()
        is_float = self._peek() == "." and self._peek(1) in _DIGITS
        if is_float:
            self._advance()
            self._digits()
        # Letters glued to a number ("12abc") belong to the same broken literal.
        glued = _is_name_start(self._peek())
        while _is_name_part(self._peek()):
            self._advance()

        lexeme = self._text[start:self._pos]
        span = span_start.to(self._here(0))
        kind = TokenType.FLOAT if is_float else TokenType.INT
        integer_part = lexeme.split(".")[0]

        if glued:
            self._error("E1004", "A number cannot be followed directly by letters", span)
        elif "__" in lexeme or any(part.startswith("_") or part.endswith("_") for part in lexeme.split(".")):
            self._error("E1004", "'_' may only appear between two digits", span)
        elif len(integer_part) > 1 and integer_part.startswith("0"):
            self._error("E1004", "A number cannot start with extra zeros", span)
        else:
            digits = lexeme.replace("_", "")
            if is_float:
                value = float(digits)
                if math.isinf(value):
                    self._error("E1004", "This number is too large for a Float", span)
                self._add(kind, lexeme, span, value)
            else:
                # The length is checked first: Python refuses to convert very long digit strings
                # (more than 4300 digits) and would raise instead of returning a number.
                too_large = len(digits) > _INT_MAX_DIGITS or int(digits) > INT_MAX
                if too_large:
                    self._error("E1004", f"This number is too large for an Int (the maximum is {INT_MAX})", span)
                self._add(kind, lexeme, span, 0 if too_large else int(digits))
            return
        self._add(kind, lexeme, span, 0.0 if is_float else 0)

    def _string(self) -> None:
        start, span_start = self._pos, self._here(0)
        self._advance()
        chars: list[str] = []

        while True:
            char = self._peek()
            if char in ("", "\r", "\n"):
                self._error(
                    "E1002",
                    "This string is never closed",
                    span_start.to(self._here(0)),
                    'Add a closing " before the end of the line. A string cannot span several lines.',
                )
                break
            if char == '"':
                self._advance()
                break
            if char == "\\":
                escape = self._peek(1)
                if escape in _ESCAPES:
                    chars.append(_ESCAPES[escape])
                    self._advance(2)
                    continue
                length = 1 if escape in ("", "\r", "\n") else 2
                self._error(
                    "E1003",
                    "Unknown escape sequence",
                    self._here(length),
                    r'The valid escapes are \n, \t, \", \\ and \{.',
                )
                self._advance(length)
                continue
            if char == "{":
                self._error(
                    "E1005",
                    "'{' is reserved for string interpolation, which is not implemented yet",
                    self._here(1),
                    r"Write \{ to include a literal '{' in the string.",
                )
            chars.append(char)
            self._advance()

        self._add(TokenType.STRING, self._text[start:self._pos], span_start.to(self._here(0)), "".join(chars))


def tokenize(source: Source) -> tuple[list[Token], list[Diagnostic]]:
    return Lexer(source).tokenize()

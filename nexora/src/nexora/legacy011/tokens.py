"""Token definitions for the NEXORA lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .diagnostics import Span


class TokenType(Enum):
    # Keywords with meaning in this version.
    FN = "fn"
    LET = "let"
    RETURN = "return"
    IF = "if"
    ELSE = "else"
    TRUE = "true"
    FALSE = "false"
    AND = "and"
    OR = "or"
    NOT = "not"
    REQUIRES = "requires"
    ENSURES = "ensures"
    TYPE = "type"
    WHERE = "where"
    EXAMPLE = "example"
    VAR = "var"
    WHILE = "while"
    FOR = "for"
    IN = "in"
    INVARIANT = "invariant"
    DECREASES = "decreases"
    USES = "uses"
    IMPORT = "import"
    PUB = "pub"
    # A word reserved for a future version: recognised so it can be rejected clearly.
    RESERVED = "reserved word"

    IDENT = "name"
    INT = "integer"
    FLOAT = "float"
    STRING = "text"

    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    LBRACKET = "["
    RBRACKET = "]"
    COMMA = ","
    COLON = ":"
    DOT = "."
    ARROW = "->"
    EQUAL = "="
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    EQUAL_EQUAL = "=="
    NOT_EQUAL = "!="
    LESS = "<"
    LESS_EQUAL = "<="
    GREATER = ">"
    GREATER_EQUAL = ">="

    NEWLINE = "end of line"
    EOF = "end of file"


KEYWORDS: dict[str, TokenType] = {
    "fn": TokenType.FN,
    "let": TokenType.LET,
    "return": TokenType.RETURN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "requires": TokenType.REQUIRES,
    "ensures": TokenType.ENSURES,
    "type": TokenType.TYPE,
    "where": TokenType.WHERE,
    "example": TokenType.EXAMPLE,
    "var": TokenType.VAR,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "invariant": TokenType.INVARIANT,
    "decreases": TokenType.DECREASES,
    "uses": TokenType.USES,
    "import": TokenType.IMPORT,
    "pub": TokenType.PUB,
}

# Keywords that can only start a statement or a declaration, never appear inside parentheses.
STATEMENT_KEYWORDS: frozenset[str] = frozenset({
    "fn", "let", "var", "return", "if", "else", "while", "for", "requires", "ensures", "example",
    "invariant", "decreases", "type", "where", "uses",
})

# Words the language design sets aside for features that are not implemented yet.
# Reserving them now means adding those features later cannot break existing programs.
RESERVED_WORDS: frozenset[str] = frozenset({
    "ai", "assert", "break", "const", "continue", "enum",
    "match", "test", "tool", "try",
})


@dataclass(frozen=True)
class Token:
    """A lexical unit. `value` holds the decoded value of INT, FLOAT and STRING tokens."""

    type: TokenType
    lexeme: str
    span: Span
    value: int | float | str | None = None

    def describe(self) -> str:
        """How the token is named in a diagnostic."""
        if self.type in (TokenType.NEWLINE, TokenType.EOF):
            return f"the {self.type.value}"
        if self.type is TokenType.IDENT:
            return f"the name '{self.lexeme}'"
        if self.type is TokenType.STRING:
            return "a text literal"
        if self.type in (TokenType.INT, TokenType.FLOAT):
            return f"the number {self.lexeme}"
        return f"'{self.lexeme}'"

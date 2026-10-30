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
    NEEDS = "needs"
    GIVES = "gives"
    PROMISES = "promises"
    TRUST = "trust"
    TYPE = "type"
    ENUM = "enum"
    MATCH = "match"
    WHERE = "where"
    EXAMPLE = "example"
    VAR = "var"
    WHILE = "while"
    FOR = "for"
    IN = "in"
    KEEPS = "keeps"
    SHRINKS = "shrinks"
    USES = "uses"
    IMPORT = "import"
    PUB = "pub"
    # A word reserved for a future version: recognised so it can be rejected clearly.
    RESERVED = "reserved word"
    # A clause word of 0.11 (`requires`, `ensures`, `invariant`, `decreases`), reserved for one
    # minor version so that a program written before 0.12 gets E1107 (decision 0019, section 9).
    OLD_CLAUSE = "word of 0.11"

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
    FAT_ARROW = "=>"
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
    "needs": TokenType.NEEDS,
    "gives": TokenType.GIVES,
    "promises": TokenType.PROMISES,
    "trust": TokenType.TRUST,
    "type": TokenType.TYPE,
    "enum": TokenType.ENUM,
    "match": TokenType.MATCH,
    "where": TokenType.WHERE,
    "example": TokenType.EXAMPLE,
    "var": TokenType.VAR,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "keeps": TokenType.KEEPS,
    "shrinks": TokenType.SHRINKS,
    "uses": TokenType.USES,
    "import": TokenType.IMPORT,
    "pub": TokenType.PUB,
}

# Keywords that can only start a statement or a declaration, never appear inside parentheses.
STATEMENT_KEYWORDS: frozenset[str] = frozenset({
    "fn", "let", "var", "return", "if", "else", "while", "for", "needs", "gives", "promises", "trust",
    "example", "keeps", "shrinks", "type", "where", "uses", "match", "requires", "ensures", "invariant", "decreases",
})

# The clause words of 0.11 and the words that replace them (decision 0019). They are not names
# in 0.12.0; a later minor version frees them.
OLD_CLAUSE_WORDS: dict[str, str] = {
    "requires": "needs", "ensures": "promises", "invariant": "keeps", "decreases": "shrinks",
}

# Words the language design sets aside for features that are not implemented yet.
# Reserving them now means adding those features later cannot break existing programs.
# `ai` and `tool` were reserved until 0.11 and are ordinary names from 0.12 (decision 0019, 9).
RESERVED_WORDS: frozenset[str] = frozenset({
    "assert", "break", "const", "continue", "test", "try",
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

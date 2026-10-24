import pytest

from nexora.tokens import RESERVED_WORDS, TokenType as T

from helpers import codes, lex


def kinds(text: str) -> list[T]:
    tokens, errors = lex(text)
    assert errors == []
    return [token.type for token in tokens]


def test_empty_source_is_just_eof():
    assert kinds("") == [T.EOF]


def test_keywords():
    assert kinds("fn let true false") == [T.FN, T.LET, T.TRUE, T.FALSE, T.EOF]


def test_reserved_words_are_recognised():
    tokens, errors = lex(" ".join(sorted(RESERVED_WORDS)))
    assert errors == []
    assert all(token.type is T.RESERVED for token in tokens[:-1])
    assert len(tokens) - 1 == len(RESERVED_WORDS)


def test_identifiers():
    tokens, _ = lex("name _private snake_case Void x1 letter fnord")
    assert [token.type for token in tokens[:-1]] == [T.IDENT] * 7
    assert [token.lexeme for token in tokens[:-1]] == [
        "name", "_private", "snake_case", "Void", "x1", "letter", "fnord",
    ]


def test_integer_literals():
    tokens, errors = lex("0 42 1_000_000")
    assert errors == []
    assert [(token.type, token.value) for token in tokens[:-1]] == [(T.INT, 0), (T.INT, 42), (T.INT, 1_000_000)]


def test_float_literals():
    tokens, errors = lex("3.14 0.5 1_0.2_5")
    assert errors == []
    assert [(token.type, token.value) for token in tokens[:-1]] == [(T.FLOAT, 3.14), (T.FLOAT, 0.5), (T.FLOAT, 10.25)]


def test_largest_int_is_accepted_and_the_next_one_is_not():
    tokens, errors = lex("9223372036854775807")
    assert errors == [] and tokens[0].value == 2 ** 63 - 1
    assert codes(lex("9223372036854775808")[1]) == ["E1004"]


@pytest.mark.parametrize("text", ["007", "1_", "1__0", "12abc", "1_.5", "00.5"])
def test_invalid_numbers(text):
    assert codes(lex(text)[1]) == ["E1004"]


def test_a_dot_without_digits_is_not_part_of_the_number():
    # Since 0.6.0 it is a token of its own, which the parser rejects (decision 0011, 3.4).
    tokens, errors = lex("1.")
    assert tokens[0].type is T.INT and tokens[0].value == 1
    assert tokens[1].type is T.DOT and errors == []


@pytest.mark.parametrize("text, kinds", [
    ("1.5", [T.FLOAT]),
    ("Text.length", [T.IDENT, T.DOT, T.IDENT]),
    ("1.length", [T.INT, T.DOT, T.IDENT]),
    (".5", [T.DOT, T.INT]),
    ("1.5.2", [T.FLOAT, T.DOT, T.INT]),
    ('"a.b" // c.d', [T.STRING]),
])
def test_where_a_dot_is_a_token(text, kinds):
    tokens, errors = lex(text)
    assert errors == [] and [token.type for token in tokens[:-1]] == kinds


def test_string_literal_and_escapes():
    tokens, errors = lex(r'"a\n\t\"\\\{b"')
    assert errors == []
    assert tokens[0].type is T.STRING
    assert tokens[0].value == 'a\n\t"\\{b'


def test_string_keeps_non_ascii_text_and_comment_markers():
    tokens, errors = lex('"año // ñ ✓"')
    assert errors == []
    assert tokens[0].value == "año // ñ ✓"


def test_operators_and_punctuation():
    assert kinds("( ) { } , : = + - * / ->") == [
        T.LPAREN, T.RPAREN, T.LBRACE, T.RBRACE, T.COMMA, T.COLON, T.EQUAL,
        T.PLUS, T.MINUS, T.STAR, T.SLASH, T.ARROW, T.EOF,
    ]


def test_arrow_and_minus_are_told_apart():
    tokens, errors = lex("a -b ->c")
    assert errors == []
    assert [token.type for token in tokens] == [T.IDENT, T.MINUS, T.IDENT, T.ARROW, T.IDENT, T.EOF]


def test_comments_are_skipped_to_the_end_of_the_line():
    assert kinds("let // let fn \"\nfn") == [T.LET, T.NEWLINE, T.FN, T.EOF]
    assert kinds("// only a comment") == [T.EOF]


def test_a_single_slash_is_division():
    assert kinds("a / b") == [T.IDENT, T.SLASH, T.IDENT, T.EOF]


def test_spaces_and_tabs_are_ignored():
    assert kinds("let\t \tx") == [T.LET, T.IDENT, T.EOF]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_every_line_ending_separates_statements(newline):
    tokens, errors = lex(f"a{newline}b")
    assert errors == []
    assert [token.type for token in tokens] == [T.IDENT, T.NEWLINE, T.IDENT, T.EOF]
    assert (tokens[2].span.line, tokens[2].span.column) == (2, 1)


def test_blank_lines_produce_one_separator_and_none_at_the_start():
    assert kinds("\n\na\n\n\nb\n") == [T.IDENT, T.NEWLINE, T.IDENT, T.NEWLINE, T.EOF]


def test_line_breaks_inside_parentheses_do_not_separate():
    assert kinds("print(\n  1\n)\nx") == [T.IDENT, T.LPAREN, T.INT, T.RPAREN, T.NEWLINE, T.IDENT, T.EOF]


def test_a_missing_parenthesis_does_not_swallow_the_following_lines():
    # 'let', 'fn' and braces cannot be inside parentheses, so they end the unclosed line.
    assert kinds("print(1\nlet x = 2\n}") == [
        T.IDENT, T.LPAREN, T.INT, T.NEWLINE, T.LET, T.IDENT, T.EQUAL, T.INT, T.NEWLINE, T.RBRACE, T.EOF,
    ]
    assert kinds("print(1\n}") == [T.IDENT, T.LPAREN, T.INT, T.NEWLINE, T.RBRACE, T.EOF]
    tokens, _ = lex("print(1\n}")
    assert (tokens[3].span.line, tokens[3].span.column) == (1, 8)


def test_lines_and_columns():
    tokens, _ = lex('fn main() {\n    let name = "NEXORA"\n}')
    positions = {token.lexeme: (token.span.line, token.span.column, token.span.end_column) for token in tokens}
    assert positions["fn"] == (1, 1, 3)
    assert positions["main"] == (1, 4, 8)
    assert positions["{"] == (1, 11, 12)
    assert positions["let"] == (2, 5, 8)
    assert positions["name"] == (2, 9, 13)
    assert positions['"NEXORA"'] == (2, 16, 24)
    assert positions["}"] == (3, 1, 2)


def test_a_tab_counts_as_one_column():
    tokens, _ = lex("\tx")
    assert tokens[0].span.column == 2


def test_columns_count_characters_not_bytes():
    tokens, _ = lex('"ñandú" x')
    assert tokens[1].span.column == 9


def test_eof_position_is_the_end_of_the_text():
    tokens, _ = lex("ab\ncd")
    assert (tokens[-1].span.line, tokens[-1].span.column) == (2, 3)


@pytest.mark.parametrize("char", ["@", "#", "$", ";", "'", "?", "%", "ñ", "\x00"])
def test_invalid_characters_are_reported_not_skipped(char):
    tokens, errors = lex(f"a {char} b")
    assert codes(errors) == ["E1001"]
    assert (errors[0].span.line, errors[0].span.column) == (1, 3)
    # Lexing continues after the bad character.
    assert [token.lexeme for token in tokens[:-1]] == ["a", "b"]


def test_unterminated_string_at_end_of_line():
    tokens, errors = lex('let a = "open\nlet b = 1')
    assert codes(errors) == ["E1002"]
    assert (errors[0].span.line, errors[0].span.column) == (1, 9)
    # The next line is still lexed normally.
    assert tokens[-2].type is T.INT and tokens[-2].span.line == 2


def test_unterminated_string_at_end_of_file():
    assert codes(lex('"open')[1]) == ["E1002"]


def test_invalid_escape():
    _, errors = lex(r'"a\qb"')
    assert codes(errors) == ["E1003"]
    assert (errors[0].span.column, errors[0].span.end_column) == (3, 5)


def test_unescaped_brace_in_string_is_reserved():
    _, errors = lex('"{name}"')
    assert codes(errors) == ["E1005"]
    assert errors[0].span.column == 2


def test_every_error_is_collected():
    _, errors = lex('@ "open\n007 #')
    assert codes(errors) == ["E1001", "E1002", "E1004", "E1001"]

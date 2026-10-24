"""The formatter: the shape it gives, and that it never breaks a program."""

import re
from pathlib import Path

from nexora import formatter
from nexora.tokens import TokenType

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_a_program_keeps_its_shape():
    source = "fn main() {\nlet x   =    1\nprint(x)\n}\n"
    result = formatter.format_source(source)
    assert result.ok
    assert result.text == "fn main() {\n    let x = 1\n    print(x)\n}\n"


def test_the_operators_get_their_spaces():
    source = "fn main() {\nprint(1+2*3)\n}\n"
    result = formatter.format_source(source)
    assert result.text == "fn main() {\n    print(1 + 2 * 3)\n}\n"


def test_a_negative_number_is_not_a_subtraction():
    source = "fn main() {\nlet x = -1\nlet y = 3 - 1\n}\n"
    result = formatter.format_source(source)
    assert result.text == "fn main() {\n    let x = -1\n    let y = 3 - 1\n}\n"


def test_the_types_and_the_calls_keep_their_shape():
    source = "fn f(xs: List[Text]) gives Text {\nreturn Text.slice(xs,0,1)\n}\n"
    result = formatter.format_source(source)
    assert result.text == (
        "fn f(xs: List[Text]) gives Text {\n    return Text.slice(xs, 0, 1)\n}\n"
    )


def test_formatting_twice_gives_the_same_text():
    source = "fn main() {\nlet xs = [1,2]\nfor x in xs {\nprint(x)\n}\n}\n"
    once = formatter.format_source(source)
    twice = formatter.format_source(once.text)
    assert once.text == twice.text


def test_every_example_survives_the_formatter():
    for path in sorted(EXAMPLES.rglob("*.nex")):
        source = path.read_text(encoding="utf-8")
        result = formatter.format_source(source, path.name)
        assert result.ok, path
        # The meaning does not change: the same tokens come out.
        from nexora.lexer import tokenize
        from nexora.diagnostics import Source

        before, _ = tokenize(Source(path.name, source))
        after, _ = tokenize(Source(path.name, result.text))
        assert [(t.type, t.value) for t in before] == [(t.type, t.value) for t in after], path
        # And formatting it again does not move it.
        again = formatter.format_source(result.text, path.name)
        assert again.text == result.text, path


def test_a_program_with_a_lexical_error_is_left_alone():
    source = "fn main() {\nlet x = \"sin cerrar\n}\n"
    result = formatter.format_source(source)
    assert not result.ok
    assert result.text == source


def test_a_range_is_formatted_and_the_rest_is_kept():
    source = "fn main() {\nlet x   = 1\nprint(x)\n}\n"
    result = formatter.format_range(source, 2, 2)
    assert result.ok
    assert result.text == "fn main() {\n    let x = 1\nprint(x)\n}\n"


def test_a_range_that_is_not_a_line_is_refused():
    source = "fn main() {\n}\n"
    result = formatter.format_range(source, 0, 1)
    assert not result.ok
    assert result.text == source


# Comments, blank lines and line endings. The lexer does not keep comments, so the
# formatter takes them from the text; each of these lost them before.


def test_a_comment_on_its_own_line_is_kept_at_the_indentation_of_its_block():
    source = "// top\nfn main() {\n// inside\nprint(1)\n        // before the end\n}\n"
    result = formatter.format_source(source)
    assert result.ok
    assert result.text == (
        "// top\nfn main() {\n    // inside\n    print(1)\n    // before the end\n}\n"
    )


def test_a_comment_after_code_stays_on_its_line():
    source = "fn main() {\nprint(1)    // trailing   \n}\n"
    result = formatter.format_source(source)
    assert result.text == "fn main() {\n    print(1) // trailing\n}\n"


def test_a_comment_next_to_a_brace_stays_next_to_it():
    source = "fn main() { // opens\nprint(1)\n} // closes\n"
    result = formatter.format_source(source)
    assert result.text == "fn main() { // opens\n    print(1)\n} // closes\n"


def test_a_comment_between_contract_clauses_and_examples_is_kept():
    source = (
        "fn f(x: Int) gives Int\n"
        "needs x > 0 // positive\n"
        "// the examples\n"
        "example f(1) == 1\n"
        "{\n"
        "return x\n"
        "}\n"
    )
    result = formatter.format_source(source)
    assert result.text == (
        "fn f(x: Int) gives Int\n"
        "    needs x > 0 // positive\n"
        "    // the examples\n"
        "    example f(1) == 1\n"
        "{\n"
        "    return x\n"
        "}\n"
    )


def test_blank_lines_are_kept():
    source = "fn a() {\nprint(1)\n\n\nprint(2)\n}\n\n// next\nfn main() {\na()\n}\n"
    result = formatter.format_source(source)
    assert result.text == (
        "fn a() {\n    print(1)\n\n\n    print(2)\n}\n\n// next\nfn main() {\n    a()\n}\n"
    )


def test_a_call_across_lines_keeps_its_lines_and_its_comments():
    source = "fn main() {\nprint(max(1, // first\n// own line\n2))\n}\n"
    result = formatter.format_source(source)
    assert result.text == (
        "fn main() {\n    print(max(1, // first\n        // own line\n        2))\n}\n"
    )


def test_two_slashes_inside_a_text_are_not_a_comment():
    source = 'fn main() {\nprint("a // b")   // real\n}\n'
    result = formatter.format_source(source)
    assert result.text == 'fn main() {\n    print("a // b") // real\n}\n'


def test_every_line_keeps_its_own_line_ending():
    crlf = "fn main() {\r\nprint(1) // c\r\n}\r\n"
    assert formatter.format_source(crlf).text == "fn main() {\r\n    print(1) // c\r\n}\r\n"
    cr = "fn main() {\rprint(1)\r}\r"
    assert formatter.format_source(cr).text == "fn main() {\r    print(1)\r}\r"


def test_a_missing_final_line_ending_is_added_once():
    result = formatter.format_source("fn main() {\nprint(1) // c\n}")
    assert result.text == "fn main() {\n    print(1) // c\n}\n"
    assert formatter.format_source(result.text).text == result.text


def test_a_byte_order_mark_is_left_alone():
    # The lexer does not read a byte-order mark, so the text is returned untouched.
    source = "﻿fn main() {\n// c\n}\n"
    result = formatter.format_source(source)
    assert not result.ok
    assert result.text == source


def test_a_range_keeps_the_lines_of_the_file_around_comments_and_blank_lines():
    source = "fn main() {\n// c\n\nlet x   = 1\nprint(x)\n}\n"
    result = formatter.format_range(source, 4, 4)
    assert result.ok
    assert result.text == "fn main() {\n// c\n\n    let x = 1\nprint(x)\n}\n"


def _lines_of(text: str) -> list[tuple[list[tuple], str]]:
    """For each line: its tokens and its comment, which are what the formatter must keep."""
    from nexora.diagnostics import Source
    from nexora.lexer import tokenize

    tokens, errors = tokenize(Source("p.nex", text))
    assert not errors
    by_line: dict[int, list] = {}
    for token in tokens:
        if token.type not in (TokenType.NEWLINE, TokenType.EOF):
            by_line.setdefault(token.span.line, []).append(token)
    shape = []
    for number, line in enumerate(re.split(r"\r\n|\n|\r", text), start=1):
        found = by_line.get(number, [])
        rest = line[found[-1].span.end_column - 1:] if found else line
        shape.append(([(t.type, t.value) for t in found], rest.strip()))
    return shape


def test_every_comment_of_the_examples_stays_on_its_line_with_its_code():
    for path in sorted(EXAMPLES.rglob("*.nex")):
        source = path.read_text(encoding="utf-8")
        result = formatter.format_source(source, path.name)
        assert result.ok, path
        before, after = _lines_of(source), _lines_of(result.text)
        # The final line ending the formatter adds is the only line that may be new.
        if len(after) == len(before) + 1:
            assert after[-1] == ([], "")
            after = after[:-1]
        assert before == after, path
        assert any(comment for _, comment in before), f"{path} has no comment to check"


def test_the_header_of_a_loop_goes_one_step_in_and_its_brace_goes_back():
    source = (
        "fn main() {\n"
        "var i = 0\n"
        "while i < 3\n"
        "keeps i >= 0\n"
        "shrinks 3 - i\n"
        "{\n"
        "i = i + 1\n"
        "}\n"
        "}\n"
    )
    assert formatter.format_source(source).text == (
        "fn main() {\n"
        "    var i = 0\n"
        "    while i < 3\n"
        "        keeps i >= 0\n"
        "        shrinks 3 - i\n"
        "    {\n"
        "        i = i + 1\n"
        "    }\n"
        "}\n"
    )


def test_a_named_condition_across_lines_keeps_its_parenthesis_apart_from_the_name():
    source = "fn g(x: Int) gives Int\nneeds ok:(x > 0 and\nx < 10)\n{\nreturn x\n}\n"
    assert formatter.format_source(source).text == (
        "fn g(x: Int) gives Int\n"
        "    needs ok: (x > 0 and\n"
        "        x < 10)\n"
        "{\n"
        "    return x\n"
        "}\n"
    )

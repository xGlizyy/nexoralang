"""The formatter: the shape it gives, and that it never breaks a program."""

from pathlib import Path

from nexora import formatter

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_a_program_keeps_its_shape():
    source = "fn main() -> Void {\nlet x   =    1\nprint(x)\n}\n"
    result = formatter.format_source(source)
    assert result.ok
    assert result.text == "fn main() -> Void {\n    let x = 1\n    print(x)\n}\n"


def test_the_operators_get_their_spaces():
    source = "fn main() -> Void {\nprint(1+2*3)\n}\n"
    result = formatter.format_source(source)
    assert result.text == "fn main() -> Void {\n    print(1 + 2 * 3)\n}\n"


def test_a_negative_number_is_not_a_subtraction():
    source = "fn main() -> Void {\nlet x = -1\nlet y = 3 - 1\n}\n"
    result = formatter.format_source(source)
    assert result.text == "fn main() -> Void {\n    let x = -1\n    let y = 3 - 1\n}\n"


def test_the_types_and_the_calls_keep_their_shape():
    source = "fn f(xs: List[Text]) -> Text {\nreturn Text.slice(xs,0,1)\n}\n"
    result = formatter.format_source(source)
    assert result.text == (
        "fn f(xs: List[Text]) -> Text {\n    return Text.slice(xs, 0, 1)\n}\n"
    )


def test_formatting_twice_gives_the_same_text():
    source = "fn main() -> Void {\nlet xs = [1,2]\nfor x in xs {\nprint(x)\n}\n}\n"
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
    source = "fn main() -> Void {\nlet x = \"sin cerrar\n}\n"
    result = formatter.format_source(source)
    assert not result.ok
    assert result.text == source


def test_a_range_is_formatted_and_the_rest_is_kept():
    source = "fn main() -> Void {\nlet x   = 1\nprint(x)\n}\n"
    result = formatter.format_range(source, 2, 2)
    assert result.ok
    assert result.text == "fn main() -> Void {\n    let x = 1\nprint(x)\n}\n"


def test_a_range_that_is_not_a_line_is_refused():
    source = "fn main() -> Void {\n}\n"
    result = formatter.format_range(source, 0, 1)
    assert not result.ok
    assert result.text == source

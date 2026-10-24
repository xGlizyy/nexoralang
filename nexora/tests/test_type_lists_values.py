"""D01/I3: list literals, their types, equality and values.

The language has `[a, b]` and `[]`, an immutable `List[T]` value, element-type
inference and structural `==`/`!=`. This file covers literals and values; the
functions of `List` are in `test_type_lists_functions.py`, `for` in
`test_for.py`, and there is still no indexing or `Option`/`Result`/records.
"""

from __future__ import annotations

import pytest

from nexora import ast_nodes as ast
from nexora import types as type_model
from nexora.checker import Checker
from nexora.diagnostics import Source
from nexora.pipeline import analyze
from nexora.values import format_value, show_value

from helpers import check_codes, diagnostics_of, in_main, parse_text, run_text, with_main


def parsed(text: str):
    program, diagnostics = parse_text(text)
    assert diagnostics == [], [diagnostic.label for diagnostic in diagnostics]
    return program


def statement_value(text: str) -> ast.Expr:
    return parsed(in_main(f"let value = {text}")).functions[0].body.statements[0].value


def test_list_literals_are_parsed() -> None:
    literal = statement_value("[1, 2, 3]")

    assert isinstance(literal, ast.ListLiteral)
    assert [element.value for element in literal.elements] == [1, 2, 3]
    assert (literal.span.column, literal.span.end_column) == (17, 26)


def test_an_empty_list_literal_is_parsed() -> None:
    literal = statement_value("[]")

    assert isinstance(literal, ast.ListLiteral)
    assert literal.elements == ()


def test_list_literals_nest() -> None:
    literal = statement_value("[[1], []]")

    assert isinstance(literal, ast.ListLiteral)
    assert all(isinstance(element, ast.ListLiteral) for element in literal.elements)
    assert literal.elements[1].elements == ()


@pytest.mark.parametrize("text", ["[1,]", "[1 2]", "[, 1]", "[1", "]"])
def test_malformed_list_literals_are_syntax_errors(text: str) -> None:
    _, diagnostics = parse_text(in_main(f"let value = {text}"))

    assert [diagnostic.code for diagnostic in diagnostics][0] == "E1101"


def test_the_type_of_a_literal_is_inferred_from_its_elements() -> None:
    text = in_main("let xs = [1, 2, 3]")
    analysis = analyze(Source("test.nex", text))

    assert analysis.diagnostics == ()
    assert analysis.checked is not None
    (symbol,) = [symbol for symbol in analysis.checked.symbols if symbol.name == "xs"]
    assert symbol.type == "List[Int]"
    let = analysis.program.functions[0].body.statements[0]
    assert analysis.types[id(let.value)] == "List[Int]"


def test_nested_literal_types_are_inferred() -> None:
    text = in_main("let xs = [[1], [2, 3]]")
    analysis = analyze(Source("test.nex", text))

    assert analysis.diagnostics == ()
    assert analysis.checked is not None
    (symbol,) = [symbol for symbol in analysis.checked.symbols if symbol.name == "xs"]
    assert symbol.type == "List[List[Int]]"


def test_an_empty_list_takes_its_element_type_from_the_annotation() -> None:
    text = in_main("let xs: List[Int] = []\nprint(xs)")
    analysis = analyze(Source("test.nex", text))

    assert analysis.diagnostics == ()
    assert analysis.checked is not None
    (symbol,) = [symbol for symbol in analysis.checked.symbols if symbol.name == "xs"]
    assert symbol.type == "List[Int]"


def test_an_empty_list_takes_its_element_type_from_a_function_parameter() -> None:
    text = with_main("fn take(xs: List[Int]) {\n    print(xs)\n}", "take([])")
    analysis = analyze(Source("test.nex", text))

    assert analysis.diagnostics == ()


def test_an_empty_list_takes_its_element_type_from_the_return_type() -> None:
    text = with_main("fn empty() gives List[Int] {\n    return []\n}", "print(empty())")

    assert run_text(text) == "[]\n"


def test_an_empty_list_takes_its_element_type_from_the_assignment() -> None:
    text = in_main("var xs: List[Int] = [1]\nxs = []\nprint(xs)")

    assert run_text(text) == "[]\n"


def test_an_empty_nested_list_takes_its_type_from_the_outer_annotation() -> None:
    text = in_main("let xs: List[List[Int]] = [[]]\nprint(xs)")

    assert run_text(text) == "[[]]\n"


def test_a_nested_empty_list_can_also_be_the_whole_value() -> None:
    text = in_main("let xs: List[List[Int]] = []\nprint(xs)")

    assert run_text(text) == "[]\n"


def test_an_empty_list_without_an_expected_type_is_rejected() -> None:
    diagnostics = diagnostics_of(in_main("let xs = []"))

    (error,) = diagnostics
    assert error.code == "E2011"
    assert error.label == "Cannot infer the type of an empty list without an expected type"
    assert "let xs: List[Int] = []" in error.hint


def test_printing_an_untyped_empty_list_is_rejected() -> None:
    assert check_codes(in_main("print([])")) == ["E2011"]


@pytest.mark.parametrize(
    "text",
    [
        "let xs = [1, \"a\"]",
        "let xs: List[Int] = [1, \"a\"]",
        "let xs: List[Int] = [1.0]",
        "let xs = [true, 1]",
        "let xs = [[1], [\"a\"]]",
    ],
)
def test_elements_must_have_the_same_type(text: str) -> None:
    diagnostics = diagnostics_of(in_main(text))

    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert "Expected" in diagnostics[0].label


def test_a_refined_element_can_widen_to_the_expected_base_element() -> None:
    text = with_main(
        'type Percent = Int where value >= 0 and value <= 100, "percent"',
        "let xs: List[Int] = [Percent(10), 20]\nprint(xs)",
    )

    assert run_text(text) == "[10, 20]\n"


def test_lists_are_invariant_across_element_types() -> None:
    text = with_main(
        'type Percent = Int where value >= 0 and value <= 100, "percent"',
        "let ints: List[Int] = [1]\n"
        "let texts: List[Text] = ints\n"
        "let percents: List[Percent] = [Percent(1)]\n"
        "let again: List[Int] = percents",
    )

    diagnostics = diagnostics_of(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011"]


def test_a_list_cannot_be_used_where_a_different_list_type_is_expected() -> None:
    text = with_main(
        "fn take(xs: List[Int]) {\n    print(xs)\n}",
        "let texts: List[Text] = [\"a\"]\ntake(texts)",
    )

    assert check_codes(text) == ["E2011"]


def test_equality_is_structural_and_returns_bool() -> None:
    text = in_main(
        "let a = [1, 2]\n"
        "let b = [1, 2]\n"
        "let c = [1, 3]\n"
        "print(a == b)\n"
        "print(a != b)\n"
        "print(a == c)\n"
        "print([[1], [2]] == [[1], [2]])"
    )

    assert run_text(text) == "true\nfalse\nfalse\ntrue\n"


def test_equality_of_empty_lists_uses_the_expected_side() -> None:
    text = in_main("let a: List[Int] = []\nlet b: List[Int] = []\nprint(a == b)\nprint([1] == [])")

    assert run_text(text) == "true\nfalse\n"


def test_equality_between_different_list_types_is_rejected() -> None:
    assert check_codes(in_main("let a = [1]\nlet b = [\"a\"]\nprint(a == b)")) == ["E2011"]


def test_the_type_of_an_equality_is_bool() -> None:
    text = in_main("let a = [1]\nlet result = a == a")
    analysis = analyze(Source("test.nex", text))

    assert analysis.diagnostics == ()
    let = analysis.program.functions[0].body.statements[1]
    assert analysis.types[id(let.value)] == "Bool"


def test_a_list_value_is_immutable_and_reassignment_does_not_change_the_old_value() -> None:
    text = in_main("var xs: List[Int] = [1, 2]\nlet old = xs\nxs = [3]\nprint(xs)\nprint(old)")

    assert run_text(text) == "[3]\n[1, 2]\n"


def test_print_and_to_text_use_the_canonical_list_form() -> None:
    text = in_main(
        "let numbers = [1, 2, 3]\n"
        "let nested = [[1], [2, 3]]\n"
        "let texts = [\"a\", \"b\"]\n"
        "print(numbers)\n"
        "print(nested)\n"
        "print(texts)\n"
        "print(to_text(numbers))"
    )

    assert run_text(text) == "[1, 2, 3]\n[[1], [2, 3]]\n[a, b]\n[1, 2, 3]\n"


def test_values_format_lists_recursively() -> None:
    value = (1, (2, 3), "a")

    assert format_value(value) == "[1, [2, 3], a]"
    assert show_value(value) == '[1, [2, 3], "a"]'


def test_main_cannot_return_a_list() -> None:
    diagnostics = diagnostics_of("fn main() gives List[Int] {\n    return []\n}\n")

    assert [diagnostic.code for diagnostic in diagnostics] == ["E2004"]


def test_the_checker_resolves_a_nested_list_type() -> None:
    checker = Checker()

    expected = type_model.list_of(type_model.list_of(type_model.INT))
    assert checker._current_type_model("List[List[Int]]") == expected
    assert checker._current_type_model("Range[Int]") is None

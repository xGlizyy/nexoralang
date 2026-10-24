"""D01/I4: the essential functions of List.

`List.length`, `List.get`, `List.append`, `List.concat` and `List.contains` have
internal parametric signatures: a `TypeVariable` stands for the element type and
each call binds it with `unify` (D01.5). The language still has no user generics
(D03), no indexing syntax and no `Option`/`Result`/records; `for` over lists is
covered in `test_for.py`.
"""

from __future__ import annotations

import pytest

from nexora.checker import BUILTINS, TYPE_FUNCTIONS
from nexora.diagnostics import Source
from nexora.pipeline import analyze

from helpers import check_codes, diagnostics_of, in_main, run_failure, run_text, with_main


def statement_value(analysis, index: int):
    return analysis.program.functions[0].body.statements[index].value


# List.length

@pytest.mark.parametrize(
    ("literal", "length"),
    [
        ("[1, 2, 3]", 3),
        ("[1.5, 2.5]", 2),
        ("[true, false]", 2),
        ('["a", "b", "c"]', 3),
        ("[[1], [2, 3]]", 2),
        ("[[[1]]]", 1),
    ],
)
def test_length_accepts_a_list_of_any_element_type(literal: str, length: int) -> None:
    assert run_text(in_main(f"print(List.length({literal}))")) == f"{length}\n"


def test_length_of_an_annotated_empty_list_is_zero() -> None:
    text = in_main("let xs: List[Int] = []\nprint(List.length(xs))")

    assert run_text(text) == "0\n"


def test_length_of_an_empty_literal_still_needs_an_element_type() -> None:
    diagnostics = diagnostics_of(in_main("print(List.length([]))"))

    (error,) = diagnostics
    assert error.code == "E2011"
    assert "empty list" in error.label
    assert "let xs: List[Int] = []" in error.hint


# List.get

@pytest.mark.parametrize(
    ("literal", "index", "value"),
    [
        ("[10, 20, 30]", 0, "10"),
        ("[10, 20, 30]", 2, "30"),
        ('["a", "b"]', 1, "b"),
        ("[true, false]", 0, "true"),
        ("[1.5, 2.5]", 1, "2.5"),
        ("[[1], [2, 3]]", 1, "[2, 3]"),
    ],
)
def test_get_returns_the_element_at_an_index(literal: str, index: int, value: str) -> None:
    text = in_main(f"let xs = {literal}\nprint(List.get(xs, {index}))")

    assert run_text(text) == f"{value}\n"


def test_get_accepts_both_bounds() -> None:
    text = in_main("let xs = [10, 20, 30]\nprint(List.get(xs, 0))\nprint(List.get(xs, 2))")

    assert run_text(text) == "10\n30\n"


def test_get_of_a_nested_list_returns_a_list() -> None:
    text = in_main(
        "let xs: List[List[Int]] = [[1], [2, 3]]\n"
        "let inner = List.get(xs, 1)\n"
        "print(List.length(inner))\n"
        "print(List.get(inner, 0))"
    )

    assert run_text(text) == "2\n2\n"


def test_get_returns_the_refined_element_type() -> None:
    text = with_main(
        'type Percent = Int where value >= 0 and value <= 100, "percent"',
        "let xs: List[Percent] = [Percent(10)]\n"
        "let p: Percent = List.get(xs, 0)\n"
        "print(p)",
    )

    assert run_text(text) == "10\n"


@pytest.mark.parametrize("index", ["2", "3", "-1"])
def test_get_outside_the_list_breaks_its_requires(index: str) -> None:
    output, error = run_failure(in_main(f"let xs = [1, 2]\nprint(List.get(xs, {index}))"))

    assert output == ""
    assert (error.code, error.category) == ("E4001", "contract")
    assert error.label == "This call breaks a 'needs' condition of 'List.get'"
    assert error.notes[0] == (
        "The condition of the built-in function is false: needs 0 <= i and i < List.length(xs)"
    )
    assert error.notes[1] == "Reason: An index must be inside the list"
    assert error.notes[2] == f"It was called with: xs = [1, 2], i = {index}"


def test_get_in_a_function_reports_the_call_that_broke_the_contract() -> None:
    functions = "fn at(xs: List[Int], i: Int) gives Int {\n    return List.get(xs, i)\n}"
    output, error = run_failure(with_main(functions, "print(at([1, 2], 5))"))

    assert output == ""
    assert error.code == "E4001"
    assert error.span.line == 2
    assert error.notes[-1] == "In 'at', called at line 6, column 11."


# List.append and List.concat

def test_append_builds_a_new_list_and_keeps_the_original() -> None:
    text = in_main(
        "let xs = [1, 2]\n"
        "let old = xs\n"
        "let ys = List.append(xs, 3)\n"
        "print(xs)\n"
        "print(old)\n"
        "print(ys)"
    )

    assert run_text(text) == "[1, 2]\n[1, 2]\n[1, 2, 3]\n"


def test_concat_builds_a_new_list_and_keeps_both_originals() -> None:
    text = in_main(
        "let xs = [1, 2]\n"
        "let ys = [3, 4]\n"
        "let joined = List.concat(xs, ys)\n"
        "print(xs)\n"
        "print(ys)\n"
        "print(joined)"
    )

    assert run_text(text) == "[1, 2]\n[3, 4]\n[1, 2, 3, 4]\n"


def test_append_and_concat_keep_the_element_type() -> None:
    text = in_main(
        "let xs = [1, 2]\n"
        "let grown = List.append(xs, 3)\n"
        "let joined = List.concat(xs, grown)"
    )
    analysis = analyze(Source("test.nex", text))

    assert analysis.diagnostics == ()
    assert analysis.types[id(statement_value(analysis, 1))] == "List[Int]"
    assert analysis.types[id(statement_value(analysis, 2))] == "List[Int]"


def test_append_and_concat_work_on_nested_lists() -> None:
    text = in_main(
        "let xs: List[List[Int]] = [[1], [2, 3]]\n"
        "print(List.append(xs, [4]))\n"
        "print(List.concat(xs, [[5]]))"
    )

    assert run_text(text) == "[[1], [2, 3], [4]]\n[[1], [2, 3], [5]]\n"


def test_append_and_concat_accept_an_annotated_empty_list() -> None:
    text = in_main(
        "let xs: List[Int] = []\n"
        "print(List.append(xs, 1))\n"
        "print(List.concat(xs, [2]))"
    )

    assert run_text(text) == "[1]\n[2]\n"


# List.contains

def test_contains_uses_structural_equality() -> None:
    text = in_main(
        "print(List.contains([1, 2, 3], 2))\n"
        "print(List.contains([1, 2, 3], 9))\n"
        'print(List.contains(["ab", "c"], "ab"))\n'
        'print(List.contains(["ab", "c"], "b"))\n'
        "print(List.contains([[1], [2, 3]], [2, 3]))\n"
        "print(List.contains([[1], [2, 3]], [3]))\n"
        "print(List.contains([true, false], false))"
    )

    assert run_text(text) == "true\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\n"


def test_contains_does_not_use_text_substring_search() -> None:
    text = in_main('let words = ["hello", "world"]\nprint(List.contains(words, "ell"))')

    assert run_text(text) == "false\n"


# Static checks and integration

@pytest.mark.parametrize(
    "call",
    [
        "List.length(1)",
        "List.length([1], [2])",
        "List.get([1], 0.0)",
        "List.get(1, 0)",
        "List.get([1])",
        "List.append([1], \"a\")",
        "List.concat([1], [\"a\"])",
        "List.concat([1], \"a\")",
        "List.contains([1], \"a\")",
    ],
)
def test_the_arguments_are_checked(call: str) -> None:
    diagnostics = diagnostics_of(in_main(f"print({call})"))

    assert len(diagnostics) == 1
    assert diagnostics[0].code in ("E2009", "E2011")


def test_the_functions_of_list_are_registered_under_their_type() -> None:
    assert TYPE_FUNCTIONS["List"] == ["append", "concat", "contains", "get", "length"]
    assert BUILTINS["List.get"].parametric is not None


def test_an_unknown_function_of_list_is_suggested_as_list_function() -> None:
    (error,) = diagnostics_of(in_main("print(List.lenght([1]))"))

    assert error.code == "E2008"
    assert error.label == "'List' has no function named 'lenght'"
    assert error.hint == "Did you mean 'List.length'?"
    assert error.notes == ("The functions of List: append, concat, contains, get, length.",)


def test_a_list_cannot_be_used_where_another_element_type_is_expected() -> None:
    text = with_main(
        "fn take(xs: List[Text]) {\n    print(xs)\n}",
        "let xs = [1, 2]\ntake(List.append(xs, 3))",
    )

    assert check_codes(text) == ["E2011"]

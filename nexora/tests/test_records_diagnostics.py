"""Los tres diagnósticos de los registros: E2023, E2024 y E2025.

Comprueba su título, su categoría, su posición y su orden (decisión 0014, 5).
"""

from __future__ import annotations

import pytest

from nexora.diagnostics import CATEGORIES, CODES
from helpers import check_codes, diagnostics_of, in_main, with_main

POINT = "type Point = { x: Int, y: Int }\n"


def test_the_three_codes_are_registered_with_their_title_and_category():
    assert CODES["E2023"] == "Invalid record construction"
    assert CATEGORIES["E2023"] == "type"
    assert CODES["E2024"] == "Invalid field access"
    assert CATEGORIES["E2024"] == "type"
    assert CODES["E2025"] == "Cannot reassign a field"
    assert CATEGORIES["E2025"] == "semantic"


@pytest.mark.parametrize("body, code", [
    ("let p = Point(x: 1)", "E2023"),
    ("let p = Point(x: 1, y: 2, z: 3)", "E2023"),
    ("let p = Point(x: 1, x: 2, y: 3)", "E2023"),
    ("let p = Point(x: 1, y: 2)\nprint(p.z)", "E2024"),
    ("let n = 1\nprint(n.x)", "E2024"),
    ("let p = Point(x: 1, y: 2)\np.x = 3", "E2025"),
])
def test_each_problem_is_reported_with_its_code(body, code):
    assert check_codes(with_main(POINT, body)) == [code]


def test_the_position_of_the_error_is_the_place_of_the_problem():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, y: 2)\nprint(p.z)"))
    assert error.span.line == 5
    assert error.span.column == 13


def test_every_missing_field_is_reported_once():
    errors = diagnostics_of(with_main(POINT, "let p = Point()"))
    assert [error.code for error in errors] == ["E2023", "E2023"]
    assert [error.label for error in errors] == [
        "The field 'x' of 'Point' is missing",
        "The field 'y' of 'Point' is missing",
    ]


def test_the_fields_that_do_not_exist_come_first_and_the_missing_ones_last():
    errors = diagnostics_of(with_main(POINT, "let p = Point(z: 1)"))
    assert [error.label for error in errors] == [
        "The record 'Point' has no field named 'z'",
        "The field 'x' of 'Point' is missing",
        "The field 'y' of 'Point' is missing",
    ]


def test_the_type_of_a_value_is_checked_separately_from_the_shape():
    errors = diagnostics_of(with_main(POINT, 'let p = Point(x: "one", y: 2)'))
    assert [error.code for error in errors] == ["E2011"]


def test_the_error_of_an_access_comes_before_the_error_of_the_immutability():
    # The field does not exist: there is nothing immutable to change (decision 0014, 5).
    assert check_codes(with_main(POINT, "let p = Point(x: 1, y: 2)\np.z = 3")) == ["E2024"]


def test_an_unknown_name_is_reported_before_anything_else():
    assert check_codes(with_main(POINT, "q.x = 3")) == ["E2005"]


def test_a_declaration_with_an_error_is_reported_once():
    assert check_codes(with_main("type A = { a: A }\n", "")) == ["E2016"]


def test_the_position_of_a_declaration_error_is_the_declaration():
    (error,) = diagnostics_of(with_main("type A = { a: A }\n", ""))
    assert error.span.line == 1
    assert error.span.column == 6


def test_the_note_of_a_cycle_writes_the_chain():
    (error,) = diagnostics_of(with_main("type A = { b: B }\ntype B = { a: A }\n", ""))
    assert error.notes == ("The cycle is: A -> B -> A",)


def test_a_record_without_fields_is_a_syntax_error():
    (error,) = diagnostics_of("type Point = { }\n")
    assert error.code == "E1101"


def test_a_record_without_a_name_is_a_syntax_error():
    (error,) = diagnostics_of(in_main("type = { x: Int }"))
    assert error.code == "E1101"

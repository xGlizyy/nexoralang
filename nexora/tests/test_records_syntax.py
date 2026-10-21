"""La gramática de los registros: cómo se declaran, cómo se construyen y cómo se leen.

Cada prueba mira una parte de la gramática de la sección 4.6 de la especificación
(decisión 0014).
"""

from __future__ import annotations

import pytest

from helpers import check_codes, diagnostics_of, in_main, parse_text, with_main

DECLARATION = "type Point = { x: Int, y: Int }\n"


def test_a_record_is_declared_with_its_fields():
    program, errors = parse_text(DECLARATION)
    assert errors == []
    (record,) = program.records
    assert record.name == "Point"
    assert [(field.name, field.type.name) for field in record.fields] == [("x", "Int"), ("y", "Int")]


def test_a_record_keeps_the_order_of_its_fields():
    program, errors = parse_text("type Point = { y: Int, x: Int }\n")
    assert errors == []
    (record,) = program.records
    assert [field.name for field in record.fields] == ["y", "x"]


def test_a_record_can_be_declared_in_several_lines():
    program, errors = parse_text("type Point = {\n    x: Int,\n    y: Int\n}\n")
    assert errors == []
    (record,) = program.records
    assert [field.name for field in record.fields] == ["x", "y"]


def test_the_brace_of_a_record_goes_on_the_same_line_as_the_equal():
    (error,) = diagnostics_of("type Point =\n    { x: Int }\n")
    assert error.code == "E1101"
    assert "same line" in error.label


def test_a_record_needs_at_least_one_field():
    (error,) = diagnostics_of("type Point = { }\n")
    assert error.code == "E1101"
    assert "at least one field" in error.label


def test_a_record_does_not_take_a_trailing_comma():
    (error,) = diagnostics_of("type Point = { x: Int, }\n")
    assert error.code == "E1101"
    assert "left out" in error.label


def test_a_field_needs_a_name_and_a_type():
    (error,) = diagnostics_of("type Point = { x }\n")
    assert error.code == "E1101"
    assert "':' and the type of the field 'x'" in error.label


def test_a_record_is_built_with_named_fields():
    program, errors = parse_text(with_main(DECLARATION, "let p = Point(x: 1, y: 2)"))
    assert errors == []
    construction = program.functions[0].body.statements[0].value
    assert construction.name == "Point"
    assert [(field.name, field.value.value) for field in construction.fields] == [("x", 1), ("y", 2)]


def test_the_fields_of_a_construction_can_be_written_in_any_order():
    program, errors = parse_text(with_main(DECLARATION, "let p = Point(y: 2, x: 1)"))
    assert errors == []
    construction = program.functions[0].body.statements[0].value
    assert [field.name for field in construction.fields] == ["y", "x"]


def test_a_record_is_built_without_the_names_of_its_fields():
    (error,) = diagnostics_of(with_main(DECLARATION, "let p = Point(1, 2)"))
    assert error.code == "E1101"
    assert "named fields" in (error.hint or "")


def test_a_construction_cannot_leave_a_field_out_after_a_comma():
    (error,) = diagnostics_of(with_main(DECLARATION, "let p = Point(x: 1,)"))
    assert error.code == "E1101"
    assert "left out" in error.label


def test_a_record_can_be_built_without_fields():
    # The syntax is fine: the fields that are missing are told by the checker (E2023).
    program, errors = parse_text(with_main(DECLARATION, "let p = Point()"))
    assert errors == []
    assert program.functions[0].body.statements[0].value.fields == ()


def test_a_field_is_read_with_a_dot():
    program, errors = parse_text(with_main(DECLARATION, "let n = p.x"))
    assert errors == []
    access = program.functions[0].body.statements[0].value
    assert access.name == "x"
    assert access.target.name == "p"


def test_fields_can_be_read_in_a_chain():
    program, errors = parse_text(with_main(
        "type Point = { x: Int }\ntype Line = { to: Point }\n",
        "let n = line.to.x",
    ))
    assert errors == []
    access = program.functions[0].body.statements[0].value
    assert access.name == "x"
    assert access.target.name == "to"
    assert access.target.target.name == "line"


def test_the_dot_of_a_field_goes_stuck_to_the_names():
    (error,) = diagnostics_of(with_main(DECLARATION, "let n = p . x"))
    assert error.code == "E1101"
    assert "without spaces" in error.label


def test_a_field_cannot_be_read_from_a_call():
    (error,) = diagnostics_of(with_main(DECLARATION, "let n = f().x"))
    assert error.code == "E1101"


def test_a_field_cannot_be_read_from_a_group():
    (error,) = diagnostics_of(with_main(DECLARATION, "let n = (p).x"))
    assert error.code == "E1101"


def test_a_field_cannot_be_read_from_a_list():
    (error,) = diagnostics_of(with_main(DECLARATION, "let n = [1].x"))
    assert error.code == "E1101"


def test_the_name_of_a_type_is_not_a_field():
    # 'Point.x' is a qualified call, like 'Text.length': the name before the dot is a type.
    (error,) = diagnostics_of(with_main(DECLARATION, "let n = Point.x"))
    assert error.code == "E1101"
    assert "Expected '(' to call 'Point.x'" in error.label


def test_a_field_cannot_be_given_a_new_value():
    program, errors = parse_text(with_main(DECLARATION, "p.x = 1"))
    assert errors == []
    assignment = program.functions[0].body.statements[0]
    assert assignment.name == "x"
    assert assignment.target.name == "p"


def test_reading_a_field_is_not_an_assignment():
    program, errors = parse_text(with_main(DECLARATION, "let n = p.x"))
    assert errors == []
    assert program.functions[0].body.statements[0].value.name == "x"


def test_a_type_cannot_be_declared_inside_a_function():
    (error,) = diagnostics_of(in_main("type Point = { x: Int }"))
    assert error.code == "E1101"
    assert "cannot be declared inside a function" in error.label


@pytest.mark.parametrize("declaration", [
    "type point = { x: Int }",
    "type Int = { x: Int }",
    "type Point = { x: Int }\ntype Point = { y: Int }",
])
def test_the_name_of_a_record_follows_the_rules_of_the_names_of_a_type(declaration):
    assert check_codes(with_main(declaration, "")) == ["E2016"]

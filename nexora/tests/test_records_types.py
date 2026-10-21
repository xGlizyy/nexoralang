"""Los tipos de un registro: sus campos, su identidad nominal y los ciclos.

Comprueba las reglas de la sección 4.6 de la especificación (decisión 0014): qué tipos
puede tener un campo, cuándo dos registros son el mismo tipo y qué pasa cuando un
registro se contiene a sí mismo.
"""

from __future__ import annotations

import pytest

from helpers import check_codes, diagnostics_of, in_main, run_text, with_main

POINT = "type Point = { x: Int, y: Int }\n"


def test_a_record_is_a_type_that_a_variable_can_have():
    assert run_text(with_main(POINT, "let p: Point = Point(x: 1, y: 2)\nprint(p.x)")) == "1\n"


def test_a_field_can_hold_any_type_of_the_language():
    text = with_main(
        "type Point = { x: Int, y: Int }\n"
        "type Boxed = { count: Int, ratio: Float, flag: Bool, label: Text, list: List[Int], "
        "small: Small, other: Point }\n"
        "type Small = Int where value < 10, \"Small numbers only\"\n",
        "let b = Boxed(count: 1, ratio: 0.5, flag: true, label: \"hi\", list: [1, 2], small: 2, "
        "other: Point(x: 0, y: 0))\n"
        "print(b.count + b.small)\n"
        "print(b.label)\n"
        "print(b.list)\n"
        "print(b.other)\n",
    )
    assert run_text(text) == "3\nhi\n[1, 2]\nPoint(x: 0, y: 0)\n"


def test_two_records_with_the_same_fields_are_different_types():
    text = with_main(
        "type Point = { x: Int, y: Int }\ntype Place = { x: Int, y: Int }\n",
        "let p = Point(x: 1, y: 2)\n"
        "let q: Place = p\n",
    )
    (error,) = diagnostics_of(text)
    assert error.code == "E2011"
    assert error.label == "Expected Place, found Point"


def test_two_values_of_the_same_record_are_compared_by_value():
    text = with_main(POINT, "print(Point(x: 1, y: 2) == Point(x: 1, y: 2))\nprint(Point(x: 1, y: 2) == Point(x: 1, y: 3))")
    assert run_text(text) == "true\nfalse\n"


def test_the_fields_of_a_record_keep_the_order_of_the_declaration():
    # The values are built in one order and printed in the order of the declaration.
    text = with_main("type Point = { x: Int, y: Int }\n", "print(Point(y: 2, x: 1))")
    assert run_text(text) == "Point(x: 1, y: 2)\n"


def test_a_record_can_hold_another_record():
    text = with_main(
        "type Point = { x: Int, y: Int }\ntype Segment = { from: Point, to: Point }\n",
        "let s = Segment(from: Point(x: 0, y: 0), to: Point(x: 1, y: 1))\nprint(s.to.x)\n",
    )
    assert run_text(text) == "1\n"


def test_a_list_can_hold_records():
    text = with_main(POINT, "let ps: List[Point] = [Point(x: 1, y: 2)]\nprint(List.length(ps))\nprint(List.get(ps, 0))")
    assert run_text(text) == "1\nPoint(x: 1, y: 2)\n"


def test_a_list_of_records_is_not_a_list_of_another_record():
    text = with_main(
        "type Point = { x: Int }\ntype Place = { x: Int }\n",
        "let ps: List[Place] = [Point(x: 1)]\n",
    )
    (error,) = diagnostics_of(text)
    assert error.code == "E2011"
    assert error.label == "Expected Place, found Point"


def test_a_record_can_use_one_declared_later():
    text = with_main(
        "type First = { second: Second }\ntype Second = { value: Int }\n",
        "let f = First(second: Second(value: 7))\nprint(f.second.value)\n",
    )
    assert run_text(text) == "7\n"


def test_a_record_cannot_contain_itself():
    (error,) = diagnostics_of(with_main("type A = { a: A }\n", ""))
    assert error.code == "E2016"
    assert "A -> A" in (error.notes[0] if error.notes else "")


def test_two_records_cannot_contain_each_other():
    (error,) = diagnostics_of(with_main("type A = { b: B }\ntype B = { a: A }\n", ""))
    assert error.code == "E2016"
    assert "A -> B -> A" in (error.notes[0] if error.notes else "")


def test_a_list_does_not_break_the_cycle():
    (error,) = diagnostics_of(with_main("type A = { items: List[A] }\n", ""))
    assert error.code == "E2016"
    assert "A -> A" in (error.notes[0] if error.notes else "")


def test_a_nested_list_does_not_break_the_cycle_either():
    # The dependency is read from the type as it was written, so a list inside a
    # list is still a dependency (decision 0014, 4).
    (error,) = diagnostics_of(with_main("type A = { items: List[List[A]] }\n", ""))
    assert error.code == "E2016"
    assert "A -> A" in (error.notes[0] if error.notes else "")


def test_a_nested_list_of_records_is_a_usable_type():
    text = with_main(
        "type Point = { x: Int }\ntype Box = { items: List[List[Point]] }\n",
        "let b = Box(items: [[Point(x: 1)]])\nprint(b.items)\n",
    )
    assert run_text(text) == "[[Point(x: 1)]]\n"


def test_a_record_with_a_field_of_a_refined_type_with_a_broken_condition():
    # The condition of the refined type is wrong: that error is reported once, and the
    # record cannot be used. The analysis must not fail with an internal error.
    text = with_main(
        "type Percent = Int where value > missing\ntype Box = { p: Percent }\n",
        "let b = Box(p: 1)\nprint(b.p)\n",
    )
    assert check_codes(text) == ["E2005"]


def test_a_record_with_a_field_of_a_refined_type_that_cannot_be_a_bool():
    text = with_main(
        "type Percent = Int where value\ntype Box = { p: Percent }\n",
        "let b = Box(p: 1)\nprint(b.p)\n",
    )
    assert check_codes(text) == ["E2011"]


def test_a_cycle_is_reported_once():
    assert check_codes(with_main("type A = { b: B }\ntype B = { a: A }\n", "")) == ["E2016"]


def test_a_field_cannot_be_repeated():
    (error,) = diagnostics_of(with_main("type Point = { x: Int, x: Int }\n", ""))
    assert error.code == "E2016"
    assert "declared more than once" in error.label


def test_the_type_of_a_field_has_to_exist():
    (error,) = diagnostics_of(with_main("type Point = { x: Missing }\n", ""))
    assert error.code == "E2012"
    assert "'Missing' is not a type" in error.label


def test_a_field_cannot_be_void():
    (error,) = diagnostics_of(with_main("type Point = { x: Void }\n", ""))
    assert error.code == "E2012"
    assert "Void" in error.label


def test_a_refined_type_cannot_be_built_on_a_record():
    (error,) = diagnostics_of(with_main(POINT + "type Distant = Point where value == value\n", ""))
    assert error.code == "E2016"


def test_the_name_of_a_record_cannot_be_used_for_a_variable():
    (error,) = diagnostics_of(with_main(POINT, "let Point = 1"))
    assert error.code == "E2006"
    assert "the name of a type" in error.label


def test_the_name_of_a_record_cannot_be_used_for_a_function():
    (error,) = diagnostics_of(POINT + "fn Point() -> Int {\n    return 0\n}\n" + in_main(""))
    assert error.code == "E2006"
    assert "the name of a type" in error.label


def test_a_record_is_not_a_value():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point"))
    assert error.code == "E2011"
    assert "is a type, not a value" in error.label
    assert "Point(field: value)" in (error.hint or "")


def test_the_name_of_a_record_cannot_be_a_refined_type():
    (error,) = diagnostics_of(with_main(POINT + "type Point = Int where value > 0\n", ""))
    assert error.code == "E2016"
    assert "declared more than once" in error.label


@pytest.mark.parametrize("declaration", [
    "type Point = { x: Int, x: Int }",
    "type Point = { a: Point }",
])
def test_a_record_that_cannot_be_used_is_not_a_type(declaration):
    # The declaration has an error, and the program that uses it says so only once.
    text = with_main(declaration, "let p: Point = Point(x: 1)")
    assert check_codes(text).count("E2016") == 1

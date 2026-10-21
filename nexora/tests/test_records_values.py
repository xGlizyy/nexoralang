"""Lo que un registro hace cuando el programa se ejecuta: construirlo, leer sus campos,
compararlo y no poder cambiarlo.

Comprueba la semántica de la sección 4.6 de la especificación (decisión 0014).
"""

from __future__ import annotations

from helpers import check_codes, diagnostics_of, run_text, with_main

POINT = "type Point = { x: Int, y: Int }\n"


def test_a_record_is_built_and_its_fields_are_read():
    text = with_main(POINT, "let p = Point(x: 1, y: 2)\nprint(p.x)\nprint(p.y)")
    assert run_text(text) == "1\n2\n"


def test_a_record_is_printed_with_its_fields():
    assert run_text(with_main(POINT, "print(Point(x: 1, y: 2))")) == "Point(x: 1, y: 2)\n"


def test_a_text_field_is_printed_without_quotes_and_described_with_them():
    # 'print' writes the value; the diagnostics write it as it would be in the source.
    from nexora.values import RecordValue, show_value
    from nexora.types import RecordIdentity

    assert run_text(with_main("type Named = { name: Text }\n", 'print(Named(name: "NEXORA"))')) \
        == "Named(name: NEXORA)\n"
    value = RecordValue(RecordIdentity(1), "Named", (("name", "NEXORA"),))
    assert show_value(value) == 'Named(name: "NEXORA")'


def test_the_fields_are_printed_in_the_order_of_the_declaration():
    assert run_text(with_main(POINT, "print(Point(y: 2, x: 1))")) == "Point(x: 1, y: 2)\n"


def test_two_values_of_the_same_record_are_equal_when_their_fields_are():
    text = with_main(POINT, "print(Point(x: 1, y: 2) == Point(x: 1, y: 2))\nprint(Point(x: 1, y: 2) == Point(x: 2, y: 1))")
    assert run_text(text) == "true\nfalse\n"


def test_two_values_of_different_records_are_not_compared():
    text = with_main(
        "type Point = { x: Int }\ntype Place = { x: Int }\n",
        "print(Point(x: 1) == Place(x: 1))",
    )
    (error,) = diagnostics_of(text)
    assert error.code == "E2011"


def test_a_record_can_go_through_a_function_and_come_back():
    text = with_main(
        POINT + "fn move(p: Point) -> Point {\n    return Point(x: p.x + 1, y: p.y)\n}\n",
        "let p = move(Point(x: 1, y: 2))\nprint(p)\n",
    )
    assert run_text(text) == "Point(x: 2, y: 2)\n"


def test_a_record_can_be_the_result_of_a_function():
    text = with_main(POINT + "fn origin() -> Point {\n    return Point(x: 0, y: 0)\n}\n", "print(origin())")
    assert run_text(text) == "Point(x: 0, y: 0)\n"


def test_a_record_can_be_read_inside_an_ensures():
    text = with_main(
        POINT + "fn check(p: Point) -> Int {\n    ensures result == p.x\n    return p.x\n}\n",
        "print(check(Point(x: 7, y: 0)))\n",
    )
    assert run_text(text) == "7\n"


def test_a_record_can_be_the_value_of_an_example():
    text = with_main(
        POINT + "fn origin() -> Point {\n    example origin() == Point(x: 0, y: 0)\n    return Point(x: 0, y: 0)\n}\n",
        "print(1)\n",
    )
    assert run_text(text) == "1\n"


def test_a_record_can_be_written_in_a_loop():
    text = with_main(
        POINT + "fn last(points: List[Point]) -> Point {\n    var result = Point(x: 0, y: 0)\n"
        "    for point in points {\n        invariant result.x >= 0\n        result = point\n    }\n    return result\n}\n",
        "print(last([Point(x: 1, y: 1), Point(x: 2, y: 2)]))\n",
    )
    assert run_text(text) == "Point(x: 2, y: 2)\n"


def test_a_field_cannot_be_given_a_new_value():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, y: 2)\np.x = 3"))
    assert error.code == "E2025"
    assert "cannot be given a new value" in error.label


def test_assigning_a_field_does_not_report_the_type_of_the_value():
    # The field cannot change anyway: its type is not compared (decision 0014, 5).
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, y: 2)\np.x = \"three\""))
    assert error.code == "E2025"


def test_assigning_a_field_that_does_not_exist_is_an_access_error():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, y: 2)\np.z = 3"))
    assert error.code == "E2024"
    assert "has no field named 'z'" in error.label


def test_assigning_a_field_of_something_that_is_not_a_record_is_an_access_error():
    (error,) = diagnostics_of(with_main(POINT, "let n = 1\nn.x = 3"))
    assert error.code == "E2024"
    assert "is not a record" in error.label


def test_assigning_a_field_of_a_name_that_does_not_exist_is_an_unknown_variable():
    (error,) = diagnostics_of(with_main(POINT, "q.x = 3"))
    assert error.code == "E2005"


def test_a_field_of_a_record_that_is_not_a_record_cannot_be_read():
    (error,) = diagnostics_of(with_main(POINT, "let n = 1\nprint(n.x)"))
    assert error.code == "E2024"
    assert "is not a record" in error.label


def test_a_field_that_does_not_exist_cannot_be_read():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, y: 2)\nprint(p.z)"))
    assert error.code == "E2024"
    assert "has no field named 'z'" in error.label
    assert "x, y" in (error.hint or "")


def test_a_field_of_an_unknown_name_cannot_be_read():
    (error,) = diagnostics_of(with_main(POINT, "print(q.x)"))
    assert error.code == "E2005"


def test_a_construction_needs_every_field():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1)"))
    assert error.code == "E2023"
    assert "field 'y'" in error.label


def test_a_construction_cannot_give_a_field_twice():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, x: 2, y: 3)"))
    assert error.code == "E2023"
    assert "given twice" in error.label


def test_a_construction_cannot_give_a_field_that_does_not_exist():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: 1, y: 2, z: 3)"))
    assert error.code == "E2023"
    assert "has no field named 'z'" in error.label


def test_the_value_of_a_field_has_to_have_the_type_of_the_field():
    (error,) = diagnostics_of(with_main(POINT, "let p = Point(x: \"one\", y: 2)"))
    assert error.code == "E2011"
    assert error.label == "Expected Int, found Text"


def test_a_construction_without_fields_reports_every_missing_field():
    assert check_codes(with_main(POINT, "let p = Point()")) == ["E2023", "E2023"]

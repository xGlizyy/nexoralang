"""The static type system: inference, annotations, operators and conversions."""

import pytest

from nexora.diagnostics import Source
from nexora.pipeline import analyze

from helpers import check_codes, diagnostics_of, in_main, run_failure, run_text


def type_of(expression: str, setup: str = "") -> str | None:
    """The type the checker computes for an expression (None if it is not well typed)."""
    analysis = analyze(Source("test.nex", in_main(f"{setup}\nlet probe = {expression}")))
    let = analysis.program.functions[0].body.statements[-1]
    return analysis.types.get(id(let.value))


def result(expression: str) -> str:
    return run_text(in_main(f"print({expression})")).rstrip("\n")


# Inference

@pytest.mark.parametrize("literal, expected", [
    ('"NEXORA"', "Text"), ("25", "Int"), ("19.99", "Float"), ("true", "Bool"), ("false", "Bool"),
])
def test_literals_have_a_type(literal, expected):
    assert type_of(literal) == expected


def test_variables_take_the_type_of_their_value():
    setup = 'let name = "NEXORA"\nlet age = 25\nlet price = 19.99\nlet active = true'
    assert [type_of(name, setup) for name in ("name", "age", "price", "active")] == ["Text", "Int", "Float", "Bool"]


def test_inferred_types_are_enforced_later():
    assert check_codes(in_main('let age = 25\nlet next = age + "1"')) == ["E2011"]


# Annotations

@pytest.mark.parametrize("declaration", [
    'let name: Text = "NEXORA"', "let age: Int = 25", "let price: Float = 19.99", "let active: Bool = true",
    "let sum: Int = 1 + 2", "let ok: Bool = 1 < 2", 'let s: Text = "a" + "b"',
])
def test_annotations_that_match_the_value(declaration):
    assert check_codes(in_main(declaration)) == []


@pytest.mark.parametrize("declaration, expected, found", [
    ('let age: Int = "twenty"', "Int", "Text"),
    ("let price: Float = 5", "Float", "Int"),
    ("let count: Int = 5.0", "Int", "Float"),
    ("let name: Text = 5", "Text", "Int"),
    ("let active: Bool = 1", "Bool", "Int"),
    ('let active: Bool = "true"', "Bool", "Text"),
    ("let n: Int = true", "Int", "Bool"),
    ("let n: Int = 1 < 2", "Int", "Bool"),
])
def test_annotations_that_do_not_match_the_value(declaration, expected, found):
    (error,) = diagnostics_of(in_main(declaration))
    assert error.code == "E2011" and error.category == "type"
    assert error.label == f"Expected {expected}, found {found}"


def test_annotation_mismatch_points_at_the_value():
    (error,) = diagnostics_of(in_main('let age: Int = "twenty"'))
    assert (error.span.line, error.span.column, error.span.end_column) == (2, 20, 28)
    assert error.notes == ("'age' is declared as Int.",)


def test_no_implicit_conversion_but_a_fix_is_suggested_when_one_exists():
    (error,) = diagnostics_of(in_main("let price: Float = 5"))
    assert error.hint == "Convert the Int explicitly with to_float(...)."
    (error,) = diagnostics_of(in_main("let count: Int = 5.0"))
    assert error.hint == "Convert the Float explicitly with to_int(...), which drops the fractional part."
    (error,) = diagnostics_of(in_main("let name: Text = 5"))
    assert error.hint == "Convert the value explicitly with to_text(...)."
    # No conversion exists from Text to Int, so none is suggested.
    (error,) = diagnostics_of(in_main('let age: Int = "twenty"'))
    assert error.hint is None


def test_the_annotation_decides_the_type_used_afterwards():
    # One error, not two: 'age' is an Int for the rest of the function.
    assert check_codes(in_main('let age: Int = "twenty"\nlet next = age + 1\nprint(next)')) == ["E2011"]


@pytest.mark.parametrize("name, code", [("Void", "E2012"), ("String", "E2012"), ("Number", "E2012"), ("int", "E2012")])
def test_invalid_annotation_types(name, code):
    assert check_codes(in_main(f"let x: {name} = 1")) == [code]


def test_unknown_type_suggestions():
    (error,) = diagnostics_of(in_main('let x: String = "a"'))
    assert error.hint == "The text type is called Text."
    (error,) = diagnostics_of(in_main("let x: Flaot = 1.0"))
    assert error.hint == "Did you mean 'Float'?"


def test_syntax_errors_and_type_errors_are_different_categories():
    (syntax,) = diagnostics_of(in_main("let age: Int ="))
    (types,) = diagnostics_of(in_main('let age: Int = "x"'))
    assert (syntax.category, types.category) == ("syntax", "type")


# Operators: types

@pytest.mark.parametrize("expression, expected", [
    ("1 + 2", "Int"), ("1 - 2", "Int"), ("1 * 2", "Int"), ("1 / 2", "Int"),
    ("1.5 + 2.5", "Float"), ("1.5 / 2.0", "Float"), ('"a" + "b"', "Text"),
    ("-1", "Int"), ("-1.5", "Float"),
    ("1 == 2", "Bool"), ("1 != 2", "Bool"), ("1.5 == 1.5", "Bool"), ('"a" == "b"', "Bool"), ("true != false", "Bool"),
    ("1 < 2", "Bool"), ("1 <= 2", "Bool"), ("1.5 > 2.5", "Bool"), ("1.5 >= 2.5", "Bool"),
    ("true and false", "Bool"), ("true or false", "Bool"), ("not true", "Bool"),
    ("1 < 2 and 2 < 3", "Bool"), ("not (1 == 2)", "Bool"), ("(1 + 2) * 3 == 9", "Bool"),
])
def test_operator_result_types(expression, expected):
    assert type_of(expression) == expected


@pytest.mark.parametrize("expression", [
    # Int and Float never mix.
    "1 + 2.5", "2.5 * 2", "1 < 2.5", "1 == 1.0", "1.0 != 1",
    # Numbers and Bool.
    "1 + true", "true * 2", "true < false", "1 == true", "-true",
    # Text only supports '+' and equality, with Text.
    '"a" + 1', '1 + "a"', '"a" - "b"', '"a" * 2', '"a" < "b"', '"a" == 1', '-"a"',
    # Logic only works on Bool.
    "1 and 2", "true and 1", '"a" or true', "not 1", 'not "a"', "1 or 0",
])
def test_operations_on_incompatible_types(expression):
    (error,) = diagnostics_of(in_main(f"let x = {expression}"))
    assert error.code == "E2011" and error.category == "type"


def test_operator_errors_name_both_types_and_explain_the_rule():
    (error,) = diagnostics_of(in_main("let x = 10 + 2.5"))
    assert error.label == "Cannot apply '+' to Int and Float"
    assert error.hint == "Int and Float are never mixed. Convert one side: to_float(x) turns an Int into a Float."
    (error,) = diagnostics_of(in_main("let x = true + 1"))
    assert error.label == "Cannot apply '+' to Bool and Int"
    (error,) = diagnostics_of(in_main("let x = 1 and true"))
    assert error.hint == "'and' combines two Bool values."


def test_not_binds_tighter_than_comparison():
    # 'not a == b' means '(not a) == b', which is a type error for numbers; the hint says how to write it.
    (error,) = diagnostics_of(in_main("let x = not 1 == 2"))
    assert error.label == "Cannot apply 'not' to Int"
    assert "not (a == b)" in error.hint
    assert type_of("not true == false") == "Bool"


def test_conditions_must_be_bool():
    (error,) = diagnostics_of(in_main("let n = 1\nif n {\n    print(n)\n}"))
    assert error.code == "E2011"
    assert error.label == "The condition of 'if' must be Bool, found Int"
    assert error.hint == "A number is not a condition. Compare it explicitly, for example: x != 0"
    assert check_codes(in_main('if "yes" {\n}')) == ["E2011"]


# Operators: values

@pytest.mark.parametrize("expression, expected", [
    ("1 == 1", "true"), ("1 == 2", "false"), ("1 != 2", "true"), ("2.5 == 2.5", "true"),
    ('"a" == "a"', "true"), ('"a" != "a"', "false"), ('"a" == "A"', "false"),
    ("true == true", "true"), ("true != false", "true"),
    ("1 < 2", "true"), ("2 < 2", "false"), ("2 <= 2", "true"), ("3 > 2", "true"), ("2 >= 3", "false"),
    ("1.5 < 2.5", "true"), ("-1 < 0", "true"), ("2.5 >= 2.5", "true"),
    ("true and true", "true"), ("true and false", "false"), ("false or true", "true"), ("false or false", "false"),
    ("not true", "false"), ("not false", "true"), ("not not true", "true"),
    ("1 + 2 * 3 == 7", "true"), ("1 < 2 and 2 < 3", "true"), ("1 > 2 or 2 > 1", "true"),
    ("true or false and false", "true"), ("(true or false) and false", "false"),
    ("not (1 == 2)", "true"), ("10 - 4 > 2 * 2", "true"),
])
def test_comparison_and_logic_values(expression, expected):
    assert result(expression) == expected


def test_and_or_only_evaluate_the_right_side_when_needed():
    assert result("false and 1 / 0 == 1") == "false"
    assert result("true or 1 / 0 == 1") == "true"
    _, error = run_failure(in_main("print(true and 1 / 0 == 1)"))
    assert error.code == "E3001"


# Division

def test_int_division_gives_an_int_and_float_division_a_float():
    assert type_of("7 / 2") == "Int" and result("7 / 2") == "3"
    assert type_of("7.0 / 2.0") == "Float" and result("7.0 / 2.0") == "3.5"
    assert result("-7 / 2") == "-3"


@pytest.mark.parametrize("expression", ["1 / 0", "1.0 / 0.0", "1 / (1 - 1)"])
def test_division_by_zero_is_a_runtime_error_that_check_cannot_see(expression):
    assert check_codes(in_main(f"print({expression})")) == []
    _, error = run_failure(in_main(f"print({expression})"))
    assert (error.code, error.category) == ("E3001", "runtime")


# Conversions

@pytest.mark.parametrize("expression, expected_type, expected", [
    ("to_float(3)", "Float", "3.0"), ("to_float(-2)", "Float", "-2.0"),
    ("to_int(3.9)", "Int", "3"), ("to_int(-3.9)", "Int", "-3"), ("to_int(0.5)", "Int", "0"),
    ("to_text(42)", "Text", "42"), ("to_text(2.5)", "Text", "2.5"), ("to_text(true)", "Text", "true"),
    ('to_text("a")', "Text", "a"),
    ('"n = " + to_text(1 + 2)', "Text", "n = 3"),
    ("to_float(7) / 2.0", "Float", "3.5"),
    ("to_int(7.5) + 1", "Int", "8"),
])
def test_explicit_conversions(expression, expected_type, expected):
    assert type_of(expression) == expected_type
    assert result(expression) == expected


@pytest.mark.parametrize("call", [
    "to_float(1.5)", 'to_float("1")', "to_float(true)", "to_int(1)", 'to_int("1")', "to_int(true)",
])
def test_conversions_only_accept_their_source_type(call):
    assert check_codes(in_main(f"let x = {call}")) == ["E2011"]


def test_conversion_arity():
    assert check_codes(in_main("let x = to_text()")) == ["E2009"]
    assert check_codes(in_main("let x = to_int(1.0, 2.0)")) == ["E2009"]


def test_conversion_results_must_be_used():
    assert check_codes(in_main("to_text(1)")) == ["E2010"]


def test_to_int_out_of_range_is_a_runtime_error():
    huge = "1" + "0" * 30 + ".0"
    _, error = run_failure(in_main(f"print(to_int({huge}))"))
    assert error.code == "E3005"
    assert result("to_int(9007199254740992.0)") == "9007199254740992"


def test_builtin_names_cannot_be_reused():
    assert check_codes(in_main("let to_text = 1")) == ["E2006"]
    assert check_codes("fn to_int(x: Float) -> Int {\n    return 1\n}\nfn main() -> Void {}") == ["E2002"]

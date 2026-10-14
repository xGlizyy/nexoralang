"""Contracts: 'requires' and 'ensures', and the explanation that can follow a condition."""

import pytest

from helpers import check_codes, diagnostics_of, parse_text, run_failure, run_text, with_main

DIVIDE = "fn divide(a: Float, b: Float) -> Float {\n    requires b != 0.0\n    return a / b\n}"
POSITIVE = "fn positive(value: Int) -> Bool {\n    ensures result == true\n    return value > 0\n}"


def function(contracts: str, body: str = "return n", signature: str = "f(n: Int) -> Int") -> str:
    lines = "\n".join(f"    {line}" for line in (contracts + "\n" + body).strip().splitlines())
    return f"fn {signature} {{\n{lines}\n}}"


# Syntax

def test_contracts_are_parsed_in_order_before_the_body():
    program, errors = parse_text(function("requires n > 0\nensures result >= n\nrequires n < 100"))
    assert errors == []
    parsed = program.functions[0]
    assert [contract.clause for contract in parsed.contracts] == ["requires", "ensures", "requires"]
    assert [type(statement).__name__ for statement in parsed.body.statements] == ["Return"]
    assert (parsed.contracts[0].span.line, parsed.contracts[0].span.column) == (2, 5)


def test_a_contract_after_a_statement_is_a_syntax_error():
    (error,) = diagnostics_of(with_main(function("", "let x = n\nrequires n > 0\nreturn x"), "print(f(1))"))
    assert (error.code, error.category) == ("E1106", "syntax")


# Static checks

def test_valid_contracts_pass_the_check():
    assert check_codes(with_main(DIVIDE + "\n" + POSITIVE, "print(divide(1.0, 2.0))\nprint(positive(1))")) == []


@pytest.mark.parametrize("contract, label", [
    ("requires n", "The condition of 'requires' must be Bool, found Int"),
    ("requires n + 1", "The condition of 'requires' must be Bool, found Int"),
    ('requires "yes"', "The condition of 'requires' must be Bool, found Text"),
    ("ensures result", "The condition of 'ensures' must be Bool, found Int"),
    ("ensures result + n", "The condition of 'ensures' must be Bool, found Int"),
])
def test_a_contract_condition_must_be_bool(contract, label):
    (error,) = diagnostics_of(with_main(function(contract), "print(f(1))"))
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == label


@pytest.mark.parametrize("contract", ["requires n > 0.5", 'requires n == "1"', "ensures result == true", "requires not n"])
def test_type_errors_inside_contract_expressions(contract):
    assert check_codes(with_main(function(contract), "print(f(1))")) == ["E2011"]


def test_contracts_only_see_the_parameters():
    source = with_main(function("requires local > 0", "let local = n\nreturn local"), "print(f(1))")
    assert check_codes(source) == ["E2005"]
    assert check_codes(with_main(function("requires missing > 0"), "print(f(1))")) == ["E2005"]


def test_result_exists_only_in_ensures_of_a_function_that_returns_a_value():
    (error,) = diagnostics_of(with_main(function("requires result > 0"), "print(f(1))"))
    assert error.code == "E2005"
    assert error.hint == "'result' only exists inside an 'ensures' clause of a function that returns a value."

    void = function("ensures result == 0", 'print("x")', "f(n: Int) -> Void")
    assert check_codes(with_main(void, "f(1)")) == ["E2005"]
    # In the body, 'result' is an ordinary name.
    assert check_codes(with_main(function("", "let result = n\nreturn result"), "print(f(1))")) == []
    assert check_codes(with_main(function("", "return result"), "print(f(1))")) == ["E2005"]


def test_result_has_the_return_type():
    text = function('ensures result == "ok"', 'return "ok"', "f(n: Int) -> Text")
    assert check_codes(with_main(text, "print(f(1))")) == []
    assert check_codes(with_main(function('ensures result == "ok"'), "print(f(1))")) == ["E2011"]


def test_contracts_may_call_functions():
    functions = "fn is_small(n: Int) -> Bool {\n    return n < 10\n}\n" + function("requires is_small(n)")
    assert run_text(with_main(functions, "print(f(3))")) == "3\n"
    assert check_codes(with_main(function("requires unknown(n)"), "print(f(1))")) == ["E2008"]


def test_a_void_call_is_not_a_condition():
    functions = 'fn log(n: Int) -> Void {\n    print(n)\n}\n' + function("requires log(n)")
    assert check_codes(with_main(functions, "print(f(1))")) == ["E2011"]


# Preconditions at run time

def test_requires_that_holds_lets_the_call_through():
    assert run_text(with_main(DIVIDE, "print(divide(9.0, 3.0))")) == "3.0\n"


def test_requires_that_fails_stops_before_the_body_runs():
    functions = 'fn guarded(n: Int) -> Int {\n    requires n > 0\n    print("body ran")\n    return n\n}'
    output, error = run_failure(with_main(functions, 'print("before")\nprint(guarded(0))\nprint("after")'))
    assert output == "before\n"
    assert (error.code, error.category, error.message) == ("E4001", "contract", "Precondition violated")


def test_precondition_diagnostic_blames_the_call_and_shows_the_values():
    _, error = run_failure(with_main(DIVIDE, "let zero = 0.0\nprint(divide(1.0, zero))"))
    assert error.label == "This call breaks a 'requires' condition of 'divide'"
    # The position is the call, in main.
    assert (error.span.line, error.span.column, error.span.end_column) == (8, 11, 28)
    assert error.notes == (
        "The condition at line 2 is false: requires b != 0.0",
        "It was called with: a = 1.0, b = 0.0",
    )


def test_precondition_is_checked_on_every_call():
    functions = function("requires n < 3", "return n")
    output, error = run_failure(with_main(functions, "print(f(1))\nprint(f(2))\nprint(f(3))\nprint(f(4))"))
    assert output == "1\n2\n"
    assert error.span.line == 9


def test_several_requires_are_checked_in_order():
    functions = function("requires n > 0\nrequires n < 10")
    _, error = run_failure(with_main(functions, "print(f(50))"))
    assert error.notes[0] == "The condition at line 3 is false: requires n < 10"
    _, error = run_failure(with_main(functions, "print(f(-1))"))
    assert error.notes[0] == "The condition at line 2 is false: requires n > 0"


def test_violation_through_another_function_lists_the_calls():
    functions = DIVIDE + "\nfn average(total: Float, count: Float) -> Float {\n    return divide(total, count)\n}"
    _, error = run_failure(with_main(functions, "print(average(9.0, 0.0))"))
    assert error.span.line == 6
    assert error.notes[-1] == "In 'average', called at line 10, column 11."


# Postconditions at run time

def test_ensures_that_holds():
    assert run_text(with_main(POSITIVE, "print(positive(5))")) == "true\n"


def test_ensures_that_fails_after_the_body_ran():
    output, error = run_failure(with_main(POSITIVE, 'print("before")\nprint(positive(-5))\nprint("after")'))
    assert output == "before\n"
    assert (error.code, error.category, error.message) == ("E4002", "contract", "Postcondition violated")
    assert error.label == "'positive' breaks its own 'ensures' condition"
    # The position is the clause: the function, not its caller, is at fault.
    assert (error.span.line, error.span.column) == (2, 5)
    assert error.notes == (
        "'positive' finished, but its condition is false: ensures result == true",
        "It returned: result = false",
        "It was called with: value = -5",
        "In 'positive', called at line 8, column 11.",
    )


def test_result_is_the_returned_value_and_parameters_keep_their_values():
    functions = function("ensures result == n * 2", "return n + n")
    assert run_text(with_main(functions, "print(f(21))")) == "42\n"
    wrong = function("ensures result == n * 2", "return n + 1")
    _, error = run_failure(with_main(wrong, "print(f(5))"))
    assert "It returned: result = 6" in error.notes


def test_ensures_is_checked_on_every_return_path():
    functions = function("ensures result > 0", "if n > 10 {\n    return n\n}\nreturn n - 100")
    assert run_text(with_main(functions, "print(f(11))")) == "11\n"
    _, error = run_failure(with_main(functions, "print(f(5))"))
    assert error.code == "E4002"


def test_ensures_on_a_void_function_uses_only_parameters():
    functions = function("ensures n > 0", 'print("ran")', "f(n: Int) -> Void")
    assert run_text(with_main(functions, "f(1)")) == "ran\n"
    output, error = run_failure(with_main(functions, "f(0)"))
    assert output == "ran\n" and error.code == "E4002"


def test_requires_runs_before_ensures():
    functions = function("ensures result > 100\nrequires n > 0")
    _, error = run_failure(with_main(functions, "print(f(-1))"))
    assert error.code == "E4001"


def test_text_values_are_quoted_in_contract_notes():
    functions = function('requires name != ""', "return name", "f(name: Text) -> Text")
    _, error = run_failure(with_main(functions, 'print(f(""))'))
    assert error.notes == ('The condition at line 2 is false: requires name != ""', 'It was called with: name = ""')


def test_contracts_on_recursive_functions():
    functions = function(
        "requires n >= 0\nensures result >= 1",
        "if n == 0 {\n    return 1\n}\nreturn n * f(n - 1)",
    )
    assert run_text(with_main(functions, "print(f(5))")) == "120\n"
    _, error = run_failure(with_main(functions, "print(f(-1))"))
    assert error.code == "E4001"


def test_a_runtime_error_inside_a_condition_is_not_a_contract_violation():
    functions = function("requires 10 / n > 1")
    _, error = run_failure(with_main(functions, "print(f(0))"))
    assert (error.code, error.category) == ("E3001", "runtime")


def test_check_does_not_claim_a_contract_holds():
    # A condition that can never be true is still accepted by the static check:
    # only its types are verified there. The violation is found when the call runs.
    functions = function("requires n > 0 and n < 0")
    source = with_main(functions, "print(f(1))")
    assert check_codes(source) == []
    _, error = run_failure(source)
    assert error.code == "E4001"


@pytest.mark.parametrize("condition, shown", [
    ("not (n == 0)", "requires not (n == 0)"),
    ("-n < 0", "requires -n < 0"),
    ("n * 2 > 0 and n != 0", "requires n * 2 > 0 and n != 0"),
    ("is_positive(n)", "requires is_positive(n)"),
    ("is_positive(n - 1) or false", "requires is_positive(n - 1) or false"),
    ('to_text(n) != "0"', 'requires to_text(n) != "0"'),
    ("to_float(n) > 0.5", "requires to_float(n) > 0.5"),
])
def test_the_broken_condition_is_shown_as_it_was_written(condition, shown):
    functions = "fn is_positive(n: Int) -> Bool {\n    return n > 0\n}\n" + function(f"requires {condition}")
    _, error = run_failure(with_main(functions, "print(f(0))"))
    assert error.code == "E4001"
    assert error.notes[0] == f"The condition at line 5 is false: {shown}"


def test_violation_of_a_function_without_parameters_lists_no_values():
    functions = "fn never() -> Int {\n    requires 1 > 2\n    return 1\n}"
    _, error = run_failure(with_main(functions, "print(never())"))
    assert error.notes == ("The condition at line 2 is false: requires 1 > 2",)


# Explanations

def test_an_explanation_follows_the_condition_after_a_comma():
    program, errors = parse_text(function('requires n > 0, "Counting starts at one"\nensures result >= n'))
    assert errors == []
    first, second = program.functions[0].contracts
    assert (first.message, second.message) == ("Counting starts at one", None)
    # The clause covers the explanation too.
    assert (first.span.line, first.span.column, first.span.end_column) == (2, 5, 45)


@pytest.mark.parametrize("clause, label", [
    ("requires n > 0,", "Expected a text after ',' explaining the rule of 'requires', found the end of line"),
    ("requires n > 0, n", "Expected a text after ',' explaining the rule of 'requires', found the name 'n'"),
    ('ensures result > 0, ""', "The explanation of 'ensures' is empty"),
    ('requires n > 0, "   "', "The explanation of 'requires' is empty"),
    ('requires n > 0, "a" "b"', "Expected the end of the line after this statement, found a text literal"),
])
def test_an_explanation_is_one_non_empty_text(clause, label):
    (error,) = diagnostics_of(with_main(function(clause), "print(f(1))"))
    assert (error.code, error.label) == ("E1101", label)


def test_a_broken_requires_shows_its_explanation():
    divide = 'fn divide(a: Float, b: Float) -> Float {\n    requires b != 0.0, "Dividing by zero has no result"\n' \
             "    return a / b\n}"
    _, error = run_failure(with_main(divide, "print(divide(1.0, 0.0))"))
    assert error.code == "E4001"
    assert error.notes == (
        "The condition at line 2 is false: requires b != 0.0",
        "Reason: Dividing by zero has no result",
        "It was called with: a = 1.0, b = 0.0",
    )


def test_a_broken_ensures_shows_its_explanation():
    text = function('ensures result > n, "The next number is bigger"', "return n")
    _, error = run_failure(with_main(text, "print(f(3))"))
    assert error.code == "E4002"
    assert error.notes[:3] == (
        "'f' finished, but its condition is false: ensures result > n",
        "Reason: The next number is bigger",
        "It returned: result = 3",
    )


def test_an_explanation_does_not_change_what_is_checked():
    text = function('requires n > 0, "Positive"')
    assert run_text(with_main(text, "print(f(5))")) == "5\n"
    assert check_codes(with_main(function('requires n, "Not a condition"'), "print(f(1))")) == ["E2011"]

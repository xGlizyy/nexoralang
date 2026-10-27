"""Contracts: 'needs' and 'promises', and the explanation that can follow a condition."""

import pytest

from helpers import check_codes, diagnostics_of, parse_text, run_failure, run_text, with_main

DIVIDE = "fn divide(a: Float, b: Float) gives Float\n    needs b != 0.0\n{\n    return a / b\n}"
POSITIVE = "fn positive(value: Int) gives Bool\n    promises result == true\n{\n    return value > 0\n}"


def function(contracts: str, body: str = "return n", signature: str = "f(n: Int) gives Int") -> str:
    """A function in the syntax of 0.12: `contracts` go in its header, `body` in its body."""
    clauses = "\n".join(f"    {line}" for line in contracts.strip().splitlines())
    lines = "\n".join(f"    {line}" for line in body.strip().splitlines())
    if not clauses:
        return f"fn {signature} {{\n{lines}\n}}"
    return f"fn {signature}\n{clauses}\n{{\n{lines}\n}}"


# Syntax

def test_contracts_are_parsed_in_order_before_the_body():
    program, errors = parse_text(function("needs n > 0\npromises result >= n\nneeds n < 100"))
    assert errors == []
    parsed = program.functions[0]
    assert [contract.clause for contract in parsed.contracts] == ["needs", "promises", "needs"]
    assert [type(statement).__name__ for statement in parsed.body.statements] == ["Return"]
    assert (parsed.contracts[0].span.line, parsed.contracts[0].span.column) == (2, 5)


def test_a_contract_after_a_statement_is_a_syntax_error():
    (error,) = diagnostics_of(with_main(function("", "let x = n\nneeds n > 0\nreturn x"), "print(f(1))"))
    assert (error.code, error.category) == ("E1106", "syntax")


# Static checks

def test_valid_contracts_pass_the_check():
    assert check_codes(with_main(DIVIDE + "\n" + POSITIVE, "print(divide(1.0, 2.0))\nprint(positive(1))")) == []


@pytest.mark.parametrize("contract, label", [
    ("needs n", "The condition of 'needs' must be Bool, found Int"),
    ("needs n + 1", "The condition of 'needs' must be Bool, found Int"),
    ('needs "yes"', "The condition of 'needs' must be Bool, found Text"),
    ("promises result", "The condition of 'promises' must be Bool, found Int"),
    ("promises result + n", "The condition of 'promises' must be Bool, found Int"),
])
def test_a_contract_condition_must_be_bool(contract, label):
    (error,) = diagnostics_of(with_main(function(contract), "print(f(1))"))
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == label


@pytest.mark.parametrize("contract", ["needs n > 0.5", 'needs n == "1"', "promises result == true", "needs not n"])
def test_type_errors_inside_contract_expressions(contract):
    assert check_codes(with_main(function(contract), "print(f(1))")) == ["E2011"]


def test_contracts_only_see_the_parameters():
    source = with_main(function("needs local > 0", "let local = n\nreturn local"), "print(f(1))")
    assert check_codes(source) == ["E2005"]
    assert check_codes(with_main(function("needs missing > 0"), "print(f(1))")) == ["E2005"]


def test_result_exists_only_in_ensures_of_a_function_that_returns_a_value():
    (error,) = diagnostics_of(with_main(function("needs result > 0"), "print(f(1))"))
    assert error.code == "E2005"
    assert error.hint == "'result' only exists inside a 'promises' clause of a function that gives a value."

    void = function("promises result == 0", 'print("x")', "f(n: Int)")
    assert check_codes(with_main(void, "f(1)")) == ["E2005"]
    # In the body, 'result' is an ordinary name.
    assert check_codes(with_main(function("", "let result = n\nreturn result"), "print(f(1))")) == []
    assert check_codes(with_main(function("", "return result"), "print(f(1))")) == ["E2005"]


def test_result_has_the_return_type():
    text = function('promises result == "ok"', 'print(n)\nreturn "ok"', "f(n: Int) gives Text")
    assert check_codes(with_main(text, "print(f(1))")) == []
    assert check_codes(with_main(function('promises result == "ok"'), "print(f(1))")) == ["E2011"]


def test_contracts_may_call_functions():
    functions = "fn is_small(n: Int) gives Bool {\n    return n < 10\n}\n" + function("needs is_small(n)")
    assert run_text(with_main(functions, "print(f(3))")) == "3\n"
    assert check_codes(with_main(function("needs unknown(n)"), "print(f(1))")) == ["E2008"]


def test_a_void_call_is_not_a_condition():
    functions = 'fn log(n: Int) {\n    print(n)\n}\n' + function("needs log(n)")
    assert check_codes(with_main(functions, "print(f(1))")) == ["E2011"]


# Preconditions at run time

def test_requires_that_holds_lets_the_call_through():
    assert run_text(with_main(DIVIDE, "print(divide(9.0, 3.0))")) == "3.0\n"


def test_requires_that_fails_stops_before_the_body_runs():
    functions = 'fn guarded(n: Int) gives Int\n    needs n > 0\n{\n    print("body ran")\n    return n\n}'
    output, error = run_failure(with_main(functions, 'print("before")\nprint(guarded(0))\nprint("after")'))
    assert output == "before\n"
    assert (error.code, error.category, error.message) == ("E4001", "contract", "Precondition violated")


def test_precondition_diagnostic_blames_the_call_and_shows_the_values():
    _, error = run_failure(with_main(DIVIDE, "let zero = 0.0\nprint(divide(1.0, zero))"))
    assert error.label == "This call breaks a 'needs' condition of 'divide'"
    # The position is the call, in main.
    assert (error.span.line, error.span.column, error.span.end_column) == (9, 11, 28)
    assert error.notes == (
        "The condition at line 2 is false: needs b != 0.0",
        "It was called with: a = 1.0, b = 0.0",
    )


def test_precondition_is_checked_on_every_call():
    functions = function("needs n < 3", "return n")
    output, error = run_failure(with_main(functions, "print(f(1))\nprint(f(2))\nprint(f(3))\nprint(f(4))"))
    assert output == "1\n2\n"
    assert error.span.line == 10


def test_several_requires_are_checked_in_order():
    functions = function("needs n > 0\nneeds n < 10")
    _, error = run_failure(with_main(functions, "print(f(50))"))
    assert error.notes[0] == "The condition at line 3 is false: needs n < 10"
    _, error = run_failure(with_main(functions, "print(f(-1))"))
    assert error.notes[0] == "The condition at line 2 is false: needs n > 0"


def test_violation_through_another_function_lists_the_calls():
    functions = DIVIDE + "\nfn average(total: Float, count: Float) gives Float {\n    return divide(total, count)\n}"
    _, error = run_failure(with_main(functions, "print(average(9.0, 0.0))"))
    assert error.span.line == 7
    assert error.notes[-1] == "In 'average', called at line 11, column 11."


# Postconditions at run time

def test_ensures_that_holds():
    assert run_text(with_main(POSITIVE, "print(positive(5))")) == "true\n"


def test_ensures_that_fails_after_the_body_ran():
    output, error = run_failure(with_main(POSITIVE, 'print("before")\nprint(positive(-5))\nprint("after")'))
    assert output == "before\n"
    assert (error.code, error.category, error.message) == ("E4002", "contract", "Postcondition violated")
    assert error.label == "'positive' breaks its own 'promises' condition"
    # The position is the clause: the function, not its caller, is at fault.
    assert (error.span.line, error.span.column) == (2, 5)
    assert error.notes == (
        "'positive' finished, but its condition is false: promises result == true",
        "It returned: result = false",
        "It was called with: value = -5",
        "In 'positive', called at line 9, column 11.",
    )


def test_result_is_the_returned_value_and_parameters_keep_their_values():
    functions = function("promises result == n * 2", "return n + n")
    assert run_text(with_main(functions, "print(f(21))")) == "42\n"
    wrong = function("promises result == n * 2", "return n + 1")
    _, error = run_failure(with_main(wrong, "print(f(5))"))
    assert "It returned: result = 6" in error.notes


def test_ensures_is_checked_on_every_return_path():
    functions = function("promises result > 0", "if n > 10 {\n    return n\n}\nreturn n - 100")
    assert run_text(with_main(functions, "print(f(11))")) == "11\n"
    _, error = run_failure(with_main(functions, "print(f(5))"))
    assert error.code == "E4002"


def test_ensures_on_a_void_function_uses_only_parameters():
    functions = function("promises n > 0", 'print("ran")', "f(n: Int)")
    assert run_text(with_main(functions, "f(1)")) == "ran\n"
    output, error = run_failure(with_main(functions, "f(0)"))
    assert output == "ran\n" and error.code == "E4002"


def test_requires_runs_before_ensures():
    functions = function("promises result > 100\nneeds n > 0")
    _, error = run_failure(with_main(functions, "print(f(-1))"))
    assert error.code == "E4001"


def test_text_values_are_quoted_in_contract_notes():
    functions = function('needs name != ""', "return name", "f(name: Text) gives Text")
    _, error = run_failure(with_main(functions, 'print(f(""))'))
    assert error.notes == ('The condition at line 2 is false: needs name != ""', 'It was called with: name = ""')


def test_contracts_on_recursive_functions():
    functions = function(
        "needs n >= 0\npromises result >= 1",
        "if n == 0 {\n    return 1\n}\nreturn n * f(n - 1)",
    )
    assert run_text(with_main(functions, "print(f(5))")) == "120\n"
    _, error = run_failure(with_main(functions, "print(f(-1))"))
    assert error.code == "E4001"


def test_a_runtime_error_inside_a_condition_is_not_a_contract_violation():
    functions = function("needs 10 / n > 1")
    _, error = run_failure(with_main(functions, "print(f(0))"))
    assert (error.code, error.category) == ("E3001", "runtime")


def test_check_does_not_claim_a_contract_holds():
    # A condition that can never be true is still accepted by the static check:
    # only its types are verified there. The violation is found when the call runs.
    functions = function("needs n > 0 and n < 0")
    source = with_main(functions, "print(f(1))")
    assert check_codes(source) == []
    _, error = run_failure(source)
    assert error.code == "E4001"


@pytest.mark.parametrize("condition, shown", [
    ("not (n == 0)", "needs not (n == 0)"),
    ("-n < 0", "needs -n < 0"),
    ("n * 2 > 0 and n != 0", "needs n * 2 > 0 and n != 0"),
    ("is_positive(n)", "needs is_positive(n)"),
    ("is_positive(n - 1) or false", "needs is_positive(n - 1) or false"),
    ('to_text(n) != "0"', 'needs to_text(n) != "0"'),
    ("to_float(n) > 0.5", "needs to_float(n) > 0.5"),
])
def test_the_broken_condition_is_shown_as_it_was_written(condition, shown):
    functions = "fn is_positive(n: Int) gives Bool {\n    return n > 0\n}\n" + function(f"needs {condition}")
    _, error = run_failure(with_main(functions, "print(f(0))"))
    assert error.code == "E4001"
    assert error.notes[0] == f"The condition at line 5 is false: {shown}"


def test_violation_of_a_function_without_parameters_lists_no_values():
    functions = "fn never() gives Int\n    needs 1 > 2\n{\n    return 1\n}"
    _, error = run_failure(with_main(functions, "print(never())"))
    assert error.notes == ("The condition at line 2 is false: needs 1 > 2",)


# Explanations

def test_an_explanation_follows_the_condition_after_a_comma():
    program, errors = parse_text(function('needs n > 0, "Counting starts at one"\npromises result >= n'))
    assert errors == []
    first, second = program.functions[0].contracts
    assert (first.message, second.message) == ("Counting starts at one", None)
    # The clause covers the explanation too.
    assert (first.span.line, first.span.column, first.span.end_column) == (2, 5, 42)


@pytest.mark.parametrize("clause, label", [
    ("needs n > 0,", "Expected a text after ',' explaining the rule of 'needs', found the end of line"),
    ("needs n > 0, n", "Expected a text after ',' explaining the rule of 'needs', found the name 'n'"),
    ('promises result > 0, ""', "The explanation of 'promises' is empty"),
    ('needs n > 0, "   "', "The explanation of 'needs' is empty"),
    ('needs n > 0, "a" "b"', "Expected the end of the line after this statement, found a text literal"),
])
def test_an_explanation_is_one_non_empty_text(clause, label):
    (error,) = diagnostics_of(with_main(function(clause), "print(f(1))"))
    assert (error.code, error.label) == ("E1101", label)


def test_a_broken_requires_shows_its_explanation():
    divide = 'fn divide(a: Float, b: Float) gives Float\n' \
             '    needs b != 0.0, "Dividing by zero has no result"\n' \
             '{\n' \
             '    return a / b\n' \
             '}'
    _, error = run_failure(with_main(divide, "print(divide(1.0, 0.0))"))
    assert error.code == "E4001"
    assert error.notes == (
        "The condition at line 2 is false: needs b != 0.0",
        "Reason: Dividing by zero has no result",
        "It was called with: a = 1.0, b = 0.0",
    )


def test_a_broken_ensures_shows_its_explanation():
    text = function('promises result > n, "The next number is bigger"', "return n")
    _, error = run_failure(with_main(text, "print(f(3))"))
    assert error.code == "E4002"
    assert error.notes[:3] == (
        "'f' finished, but its condition is false: promises result > n",
        "Reason: The next number is bigger",
        "It returned: result = 3",
    )


def test_an_explanation_does_not_change_what_is_checked():
    text = function('needs n > 0, "Positive"')
    assert run_text(with_main(text, "print(f(5))")) == "5\n"
    assert check_codes(with_main(function('needs n, "Not a condition"'), "print(f(1))")) == ["E2011"]

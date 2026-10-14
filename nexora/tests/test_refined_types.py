"""Refined types: `type Name = Base where condition`.

The property every test here protects: a value whose static type is a refined type satisfies
its condition. Constants are checked by the static analysis (E2017); any other value only gets
a refined type through the explicit check `Name(x)`, which runs when the program does (E4003).
"""

import pytest

from helpers import check_codes, diagnostics_of, parse_text, run_failure, run_text, with_main

PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"'


def program(declarations: str, body: str) -> str:
    return with_main(declarations, body)


# Syntax

def test_a_type_declaration_is_parsed_at_the_top_level():
    parsed, errors = parse_text(PERCENT + "\n\nfn main() -> Void {\n}\n")
    assert errors == []
    (declaration,) = parsed.types
    assert (declaration.name, declaration.base.name) == ("Percent", "Int")
    assert declaration.message == "A percentage goes from 0 to 100"
    assert type(declaration.condition).__name__ == "Binary"
    assert [function.name for function in parsed.functions] == ["main"]


def test_types_and_functions_can_be_declared_in_any_order():
    text = "fn main() -> Void {\n    print(half(40))\n}\n\nfn half(p: Percent) -> Int {\n    return p / 2\n}\n\n" + PERCENT
    assert run_text(text) == "20\n"


@pytest.mark.parametrize("declaration, label", [
    ("type Percent = Int", "Expected 'where' and the condition that the values of 'Percent' satisfy, "
                           "found the end of line"),
    ("type Percent Int where value > 0", "Expected '=' after the type name 'Percent', found the name 'Int'"),
    ("type Percent = Int where", "Expected a condition after 'where', found the end of line"),
    ("type = Int where value > 0", "Expected a type name after 'type', found '='"),
    ("type Percent = Int where value > 0,", "Expected a text after ',' explaining the rule of 'where', "
                                            "found the end of line"),
])
def test_malformed_type_declarations(declaration, label):
    (error,) = diagnostics_of(declaration + "\n\nfn main() -> Void {\n}\n")
    assert (error.code, error.label) == ("E1101", label)


def test_a_type_cannot_be_declared_inside_a_function():
    (error,) = diagnostics_of("fn main() -> Void {\n    type Small = Int where value < 10\n}\n")
    assert (error.code, error.label) == ("E1101", "A type cannot be declared inside a function")


def test_where_outside_a_type_declaration_is_a_syntax_error():
    (error,) = diagnostics_of("fn main() -> Void {\n    where\n}\n")
    assert error.code == "E1101"
    assert error.label == "'where' can only follow the base type in a type declaration"


def test_type_and_where_are_keywords_now():
    assert check_codes("fn main() -> Void {\n    let type = 1\n}\n") == ["E1101"]
    assert check_codes("fn main() -> Void {\n    let where = 1\n}\n") == ["E1101"]


# Declarations

@pytest.mark.parametrize("declaration, code, label", [
    ("type Int = Int where value > 0", "E2016", "'Int' is a built-in type and cannot be declared again"),
    ("type percent = Int where value > 0", "E2016", "The type name 'percent' must start with a capital letter"),
    ("type Wrong = Integer where value > 0", "E2012", "'Integer' is not a type"),
    ("type Nothing = Void where value > 0", "E2012", "The type 'Nothing' cannot have the type Void"),
])
def test_invalid_type_declarations(declaration, code, label):
    (error,) = diagnostics_of(declaration + "\n\nfn main() -> Void {\n}\n")
    assert (error.code, error.label) == (code, label)


def test_a_type_declared_twice():
    errors = diagnostics_of(PERCENT + "\n" + PERCENT + "\n\nfn main() -> Void {\n}\n")
    assert [(error.code, error.label) for error in errors] == [
        ("E2016", "The type 'Percent' is declared more than once"),
    ]
    assert errors[0].span.line == 2


def test_a_chain_of_types_that_never_reaches_a_built_in_type():
    text = "type A = B where value > 0\ntype B = A where value > 0\n\nfn main() -> Void {\n}\n"
    assert check_codes(text) == ["E2016", "E2016"]


def test_type_names_cannot_be_reused_for_values_or_functions():
    assert check_codes(program(PERCENT, "let Percent = 3")) == ["E2006"]
    assert check_codes(program(PERCENT + "\nfn Percent() -> Int {\n    return 1\n}", "")) == ["E2006"]
    (error,) = diagnostics_of(program(PERCENT, "print(Percent)"))
    assert (error.code, error.label) == ("E2011", "'Percent' is a type, not a value")


# The condition

def test_the_condition_must_be_bool():
    (error,) = diagnostics_of(program("type Odd = Int where value + 1", ""))
    assert (error.code, error.label) == ("E2011", "The condition of 'where' in 'Odd' must be Bool, found Int")


def test_value_is_the_only_name_in_the_condition():
    (error,) = diagnostics_of(program("type Small = Int where value < limit", ""))
    assert (error.code, error.label) == ("E2005", "There is no variable named 'limit' here")
    assert error.hint == "In the condition of 'Small', the only name is 'value': the value being checked."


def test_value_has_the_base_type():
    assert check_codes(program("type Short = Text where value != \"\"", 'let s: Short = "a"\nprint(s)')) == []
    assert check_codes(program("type Wrong = Text where value > 0", "")) == ["E2011"]


def test_the_condition_cannot_call_functions_of_the_program():
    functions = "type Positive = Int where check(value)\nfn check(n: Int) -> Bool {\n    return n > 0\n}"
    (error,) = diagnostics_of(program(functions, ""))
    assert (error.code, error.category) == ("E2018", "semantic")
    assert error.label == "The condition of 'Positive' cannot call the function 'check'"


def test_the_condition_cannot_check_against_another_refined_type():
    text = program(PERCENT + "\ntype Half = Int where Percent(value) == value", "")
    assert check_codes(text) == ["E2018"]


def test_the_condition_can_use_built_in_conversions():
    text = program("type Cheap = Int where to_float(value) < 9.5", "let price: Cheap = 9\nprint(price)")
    assert run_text(text) == "9\n"


# Constants are checked without running

@pytest.mark.parametrize("statement", ["let p: Percent = 0", "let p: Percent = 100", "let p: Percent = (50)"])
def test_a_constant_that_satisfies_the_condition(statement):
    assert check_codes(program(PERCENT, statement + "\nprint(p)")) == []


@pytest.mark.parametrize("statement, written", [
    ("let p: Percent = 101", "101"),
    ("let p: Percent = -1", "-1"),
    ("let p: Percent = -(5)", "-5"),
])
def test_a_constant_that_breaks_the_condition(statement, written):
    (error,) = diagnostics_of(program(PERCENT, statement + "\nprint(p)"))
    assert (error.code, error.category) == ("E2017", "type")
    assert error.label == f"{written} is not a valid Percent"
    assert error.notes == (
        "The condition of 'Percent' is false: where value >= 0 and value <= 100",
        f"The value: {written}",
        "Reason: A percentage goes from 0 to 100",
    )


def test_constants_are_checked_as_arguments_and_return_values():
    functions = PERCENT + "\nfn half(p: Percent) -> Percent {\n    return 120\n}"
    errors = diagnostics_of(program(functions, "print(half(150))"))
    assert [(error.code, error.span.line) for error in errors] == [("E2017", 3), ("E2017", 7)]


def test_a_constant_that_makes_the_condition_fail_while_evaluating():
    (error,) = diagnostics_of(program("type Inverse = Float where 1.0 / value > 0.0", "let x: Inverse = 0.0"))
    assert error.code == "E2017"
    assert error.label == "0.0 cannot be checked against the condition of 'Inverse'"
    assert error.notes == ("Evaluating the condition stops with: The right-hand side of this division is zero",)


def test_a_text_constant_is_quoted_in_the_diagnostic():
    (error,) = diagnostics_of(program('type Name = Text where value != ""', 'let n: Name = ""'))
    assert error.label == '"" is not a valid Name'


# Values computed while running

def test_a_computed_value_needs_an_explicit_check():
    (error,) = diagnostics_of(program(PERCENT, "let n = 50\nlet p: Percent = n"))
    assert (error.code, error.label) == ("E2011", "Expected Percent, found Int")
    assert error.hint.startswith("Check the value explicitly with Percent(...).")


def test_an_explicit_check_that_holds():
    assert run_text(program(PERCENT, "let n = 30\nlet p = Percent(n + 20)\nprint(p)")) == "50\n"


def test_an_explicit_check_that_fails_stops_the_program():
    output, error = run_failure(program(PERCENT, 'print("before")\nlet n = 60\nlet p = Percent(n * 2)\nprint(p)'))
    assert output == "before\n"
    assert (error.code, error.category) == ("E4003", "contract")
    assert error.label == "This value is not a valid Percent"
    assert (error.span.line, error.span.column) == (6, 13)
    assert error.notes == (
        "The condition of 'Percent' is false: where value >= 0 and value <= 100",
        "The value: 120",
        "Reason: A percentage goes from 0 to 100",
    )


def test_the_check_of_a_constant_happens_before_running():
    assert check_codes(program(PERCENT, "print(Percent(300))")) == ["E2017"]


@pytest.mark.parametrize("call, code", [
    ("Percent()", "E2009"),
    ("Percent(1, 2)", "E2009"),
    ('Percent("ten")', "E2011"),
    ("Percent(1.5)", "E2011"),
])
def test_an_explicit_check_takes_one_value_of_the_base_type(call, code):
    assert check_codes(program(PERCENT, f"print({call})")) == [code]


def test_the_violation_lists_the_calls_that_led_to_it():
    functions = PERCENT + "\nfn as_percent(n: Int) -> Percent {\n    return Percent(n)\n}"
    _, error = run_failure(program(functions, "print(as_percent(500))"))
    assert error.code == "E4003"
    assert error.notes[-1] == "In 'as_percent', called at line 7, column 11."


# Using refined values

def test_a_refined_value_is_accepted_where_its_base_type_is_expected():
    functions = PERCENT + "\nfn double(n: Int) -> Int {\n    return n * 2\n}"
    assert run_text(program(functions, "let p: Percent = 40\nprint(double(p))\nprint(to_float(p))")) == "80\n40.0\n"


def test_operations_on_refined_values_give_the_base_type():
    text = program(PERCENT, "let p: Percent = 80\nlet q: Percent = 70\nlet total = p + q\nprint(total)")
    assert run_text(text) == "150\n"
    (error,) = diagnostics_of(program(PERCENT, "let p: Percent = 80\nlet q: Percent = p + 1"))
    assert (error.code, error.label) == ("E2011", "Expected Percent, found Int")


def test_a_base_value_is_not_accepted_where_a_refined_type_is_expected():
    functions = PERCENT + "\nfn show(p: Percent) -> Void {\n    print(p)\n}"
    assert check_codes(program(functions, "let n = 3\nshow(n)")) == ["E2011"]
    assert run_text(program(functions, "let n = 3\nshow(Percent(n))")) == "3\n"


def test_two_refined_types_of_the_same_base_are_different_types():
    declarations = PERCENT + '\ntype Grade = Int where value >= 0 and value <= 10'
    assert check_codes(program(declarations, "let g: Grade = 7\nlet p: Percent = g")) == ["E2011"]
    assert run_text(program(declarations, "let g: Grade = 7\nlet p = Percent(g * 10)\nprint(p)")) == "70\n"


def test_a_refined_bool_is_a_condition():
    text = program("type Accepted = Bool where value", "let ok: Accepted = true\nif ok {\n    print(1)\n}")
    assert run_text(text) == "1\n"
    assert check_codes(program("type Accepted = Bool where value", "let ok: Accepted = false")) == ["E2017"]


def test_result_has_the_refined_return_type():
    functions = PERCENT + '\nfn full() -> Percent {\n    ensures result == 100, "Full is everything"\n    return 100\n}'
    assert run_text(program(functions, "print(full())")) == "100\n"


def test_main_cannot_return_a_refined_type():
    assert check_codes(PERCENT + "\nfn main() -> Percent {\n    return 1\n}\n") == ["E2004"]


# Chains of refined types

CHAIN = PERCENT + '\ntype Pass = Percent where value >= 50, "Passing starts at half"'


def test_a_refinement_of_a_refinement_satisfies_both_conditions():
    assert run_text(program(CHAIN, "let p: Pass = 70\nprint(p)")) == "70\n"
    (error,) = diagnostics_of(program(CHAIN, "let p: Pass = 40"))
    assert error.notes == (
        "The condition of 'Pass' is false: where value >= 50",
        "The value: 40",
        "Reason: Passing starts at half",
    )


def test_the_parent_condition_is_checked_first():
    (error,) = diagnostics_of(program(CHAIN, "let p: Pass = 150"))
    assert error.notes[0] == "'Pass' refines 'Percent', and the condition of 'Percent' is false: " \
                             "where value >= 0 and value <= 100"
    _, failure = run_failure(program(CHAIN, "let n = 150\nlet p = Pass(n)"))
    assert failure.code == "E4003"
    assert failure.notes[0].startswith("'Pass' refines 'Percent'")


def test_a_refinement_is_accepted_where_its_parent_is_expected():
    functions = CHAIN + "\nfn show(p: Percent) -> Void {\n    print(p)\n}"
    assert run_text(program(functions, "let p: Pass = 90\nshow(p)")) == "90\n"
    assert check_codes(program(functions.replace("show(p: Percent)", "show(p: Pass)"),
                               "let p: Percent = 90\nshow(p)")) == ["E2011"]


def test_a_type_built_on_an_invalid_type_is_not_usable():
    text = program("type Odd = Int where value + 1\ntype Small = Odd where value < 10", "let s: Small = 3")
    # The broken condition is reported once; the types built on it are silently unusable.
    assert check_codes(text) == ["E2011"]


# The guarantee

def test_check_never_claims_that_a_computed_value_is_valid():
    # Passes the check, fails when it runs: the analysis does not reason about computed values.
    text = program(PERCENT, "let n = 99\nlet p = Percent(n + 2)")
    assert check_codes(text) == []
    _, error = run_failure(text)
    assert error.code == "E4003"


# Attacks on the guarantee (the review of 0.3.0). Each one tries to give a refined type to a value
# that was never checked, or to make the static check and the run disagree.

@pytest.mark.parametrize("statement", [
    "let p: Percent = -(-(150))",
    "let p: Percent = ((150))",
    "print(Percent(-(-(150))))",
])
def test_disguised_constants_are_still_checked(statement):
    assert check_codes(program(PERCENT, statement)) == ["E2017"]


@pytest.mark.parametrize("statement", [
    "let p: Percent = 50 + 100",       # an operation is not a constant
    "let n = 150\nlet p: Percent = n",
    "let q: Pass = 70\nlet p: Percent = q\nlet r: Pass = p",   # back down from the parent
])
def test_no_unchecked_path_into_a_refined_type(statement):
    declarations = PERCENT + '\ntype Pass = Percent where value >= 50'
    assert "E2011" in check_codes(program(declarations, statement))


def test_a_function_cannot_return_its_base_type_as_the_refined_type():
    text = PERCENT + "\nfn f(n: Int) -> Percent {\n    return n\n}\n\nfn main() -> Void {\n}\n"
    assert check_codes(text) == ["E2011"]


@pytest.mark.parametrize("declaration, constant, runtime_value", [
    ("type Pos = Float where value > 0.0", "-0.0", "-0.0"),
    ("type Small = Float where value < 0.1 + 0.2", "0.30000000000000004", "0.30000000000000004"),
    ("type Inv = Int where value != 0 and 10 / value > 1", "0", "0"),
])
def test_the_static_check_and_the_run_agree(declaration, constant, runtime_value):
    name = declaration.split()[1]
    assert check_codes(program(declaration, f"let x: {name} = {constant}")) == ["E2017"]
    _, error = run_failure(program(declaration, f"let v = {runtime_value}\nprint({name}(v))"))
    assert error.code == "E4003"


# Fixes of 0.3.1

def test_a_runtime_error_inside_a_condition_says_where_the_check_was_asked():
    text = program("type Huge = Int where value * value > 0", "let n = 9223372036854775807\nprint(Huge(n))")
    _, error = run_failure(text)
    assert (error.code, error.span.line) == ("E3002", 1)
    assert "While checking that a value is a valid Huge, at line 5, column 11." in error.notes


def test_an_invalid_condition_is_reported_once_and_not_at_every_use():
    functions = "type Bad = Int where value + 1\nfn f(x: Bad) -> Int {\n    return x + 1\n}"
    errors = diagnostics_of(program(functions, "print(f(3))\nlet y: Bad = 4"))
    assert [(error.code, error.span.line) for error in errors] == [("E2011", 1)]


def test_an_explanation_is_one_line():
    (error,) = diagnostics_of(program('type Even = Int where value / 2 * 2 == value, "One\\ntwo"', ""))
    assert (error.code, error.label) == ("E1101", "An explanation is a single line: it cannot contain '\\n'")
    (error,) = diagnostics_of('fn f(n: Int) -> Int {\n    requires n > 0, "a\\nb"\n    return n\n}\n\n'
                              "fn main() -> Void {\n}\n")
    assert error.code == "E1101"


def chain_program(types: int, terms: int, uses: int) -> str:
    chain = "".join(
        f"type T{i} = {'Int' if i == 0 else f'T{i - 1}'} where " + " and ".join(["value >= 0"] * terms) + "\n"
        for i in range(types)
    )
    body = "\n".join(f"    let v{i}: T{types - 1} = {i}" for i in range(uses))
    return chain + "fn main() -> Void {\n" + body + "\n}\n"


def test_the_cost_of_checking_constants_is_bounded():
    import time

    # Fits the playground's 64 KiB; in 0.3.0 its check took longer than the playground's 2 seconds.
    text = chain_program(60, 40, 1000)
    start = time.perf_counter()
    errors = diagnostics_of(text)
    assert time.perf_counter() - start < 1.0
    assert [error.code for error in errors] == ["E2019"]
    assert errors[0].label == "Checking constants against refined types needs more than 100000 steps"


def test_ordinary_programs_are_far_from_the_limit():
    assert check_codes(chain_program(5, 3, 300)) == []

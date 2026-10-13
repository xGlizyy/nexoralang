import pytest

from helpers import in_main, run_failure, run_text


def result(expression: str) -> str:
    """What `print(expression)` writes, without the final line break."""
    return run_text(in_main(f"print({expression})")).rstrip("\n")


# Output

def test_hello():
    program = 'fn main() -> Void {\n    let message = "Hello from NEXORA"\n    print(message)\n}\n'
    assert run_text(program) == "Hello from NEXORA\n"


def test_print_formats_each_type():
    assert result('"Hello"') == "Hello"
    assert result("42") == "42"
    assert result("true") == "true"
    assert result("false") == "false"
    assert result("3.14") == "3.14"
    assert result("2.0") == "2.0"
    assert result('""') == ""


def test_print_writes_strings_as_they_are():
    assert result(r'"a\tb \"q\" \\ \{"') == 'a\tb "q" \\ {'
    assert run_text(in_main(r'print("one\ntwo")')) == "one\ntwo\n"
    assert result('"año ✓"') == "año ✓"


def test_statements_run_in_order():
    assert run_text(in_main("print(1)\nprint(2)\nprint(3)")) == "1\n2\n3\n"


def test_empty_main_prints_nothing():
    assert run_text("fn main() -> Void {}") == ""


# Variables and scopes

def test_variables_hold_their_values():
    body = 'let name = "NEXORA"\nlet age = 1\nlet active = true\nprint(name)\nprint(age)\nprint(active)'
    assert run_text(in_main(body)) == "NEXORA\n1\ntrue\n"


def test_variables_can_be_built_from_other_variables():
    assert run_text(in_main("let a = 2\nlet b = a * 10\nlet c = b + a\nprint(c)")) == "22\n"


def test_block_reads_outer_variables_and_keeps_its_own():
    body = "let outer = 1\n{\n    let inner = outer + 1\n    print(inner)\n}\nprint(outer)"
    assert run_text(in_main(body)) == "2\n1\n"


def test_sibling_blocks_have_separate_variables():
    assert run_text(in_main("{\n    let x = 1\n    print(x)\n}\n{\n    let x = 2\n    print(x)\n}")) == "1\n2\n"


# Arithmetic

@pytest.mark.parametrize("expression, expected", [
    ("10 + 5", "15"),
    ("10 - 5", "5"),
    ("4 * 3", "12"),
    ("10 / 2", "5"),
    ("2 + 3 * 4", "14"),
    ("(2 + 3) * 4", "20"),
    ("10 - 4 - 3", "3"),
    ("100 / 10 / 5", "2"),
    ("-5 + 2", "-3"),
    ("--5", "5"),
    ("2 * -3", "-6"),
    ("1_000 * 1_000", "1000000"),
])
def test_int_arithmetic(expression, expected):
    assert result(expression) == expected


@pytest.mark.parametrize("expression, expected", [
    ("7 / 2", "3"),
    ("-7 / 2", "-3"),
    ("7 / -2", "-3"),
    ("-7 / -2", "3"),
    ("1 / 2", "0"),
    ("0 / 5", "0"),
])
def test_int_division_rounds_toward_zero(expression, expected):
    assert result(expression) == expected


@pytest.mark.parametrize("expression, expected", [
    ("1.5 + 2.25", "3.75"),
    ("5.0 - 0.5", "4.5"),
    ("1.5 * 2.0", "3.0"),
    ("7.0 / 2.0", "3.5"),
    ("10.0 / 4.0", "2.5"),
    ("-1.5", "-1.5"),
    ("0.1 + 0.2", "0.30000000000000004"),
])
def test_float_arithmetic(expression, expected):
    assert result(expression) == expected


def test_string_concatenation():
    assert result('"Hello, " + "NEXORA"') == "Hello, NEXORA"
    assert run_text(in_main('let a = "x"\nlet b = a + a + a\nprint(b)')) == "xxx\n"


# Run-time errors

@pytest.mark.parametrize("expression", ["1 / 0", "1 / (2 - 2)", "1.0 / 0.0", "5.0 / (1.0 - 1.0)"])
def test_division_by_zero(expression):
    output, error = run_failure(in_main(f'print("before")\nprint({expression})\nprint("after")'))
    assert error.code == "E3001"
    assert error.span.line == 3
    # What ran before the failure is kept; nothing after it runs.
    assert output == "before\n"


def test_division_by_zero_points_at_the_divisor():
    _, error = run_failure(in_main("let zero = 0\nprint(10 / zero)"))
    assert (error.span.line, error.span.column, error.span.end_column) == (3, 16, 20)


@pytest.mark.parametrize("expression", [
    "9223372036854775807 + 1",
    "-9223372036854775807 - 2",
    "9223372036854775807 * 2",
    "4611686018427387904 * 2",
])
def test_int_overflow_is_an_error_not_a_wrong_result(expression):
    _, error = run_failure(in_main(f"print({expression})"))
    assert error.code == "E3002"


def test_int_limits_are_reachable():
    assert result("9223372036854775807") == "9223372036854775807"
    assert result("-9223372036854775807 - 1") == "-9223372036854775808"


def test_float_overflow_is_an_error():
    huge = "1" + "0" * 200 + ".0"
    _, error = run_failure(in_main(f"let big = {huge}\nprint(big * big)"))
    assert error.code == "E3003"


def test_execution_is_deterministic():
    program = in_main('let a = 7 / 2\nlet b = 0.1 + 0.2\nprint(a)\nprint(b)\nprint("x" + "y")')
    assert run_text(program) == run_text(program) == "3\n0.30000000000000004\nxy\n"

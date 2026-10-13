"""User-defined functions: parameters, return values, calls, 'if' and recursion."""

import pytest

from nexora.interpreter import MAX_CALL_DEPTH

from helpers import check_codes, diagnostics_of, in_main, parse_text, run_failure, run_text, with_main

ADD = "fn add(a: Int, b: Int) -> Int {\n    return a + b\n}"


def only(text: str):
    (error,) = diagnostics_of(text)
    return error


# Parsing

def test_function_with_parameters_is_parsed():
    program, errors = parse_text(ADD)
    assert errors == []
    function = program.functions[0]
    assert [(param.name, param.type.name) for param in function.params] == [("a", "Int"), ("b", "Int")]
    assert function.return_type.name == "Int"
    assert function.contracts == ()
    (statement,) = function.body.statements
    assert type(statement).__name__ == "Return"


def test_parameters_may_span_lines():
    program, errors = parse_text("fn f(\n    a: Int,\n    b: Text\n) -> Void {}")
    assert errors == [] and len(program.functions[0].params) == 2


# Calls

def test_the_reference_example():
    program = with_main(ADD, "let result: Int = add(2, 3)\nprint(result)")
    assert run_text(program) == "5\n"


def test_arguments_are_evaluated_left_to_right_and_bound_by_position():
    program = with_main(
        "fn show(label: Text, value: Int) -> Int {\n    print(label)\n    return value\n}\n"
        "fn sub(a: Int, b: Int) -> Int {\n    return a - b\n}",
        'print(sub(show("first", 10), show("second", 3)))',
    )
    assert run_text(program) == "first\nsecond\n7\n"


def test_functions_can_be_declared_in_any_order():
    program = "fn main() -> Void {\n    print(twice(4))\n}\n\nfn twice(n: Int) -> Int {\n    return n * 2\n}\n"
    assert run_text(program) == "8\n"


def test_calls_nest_and_compose():
    program = with_main(ADD, "print(add(add(1, 2), add(3, 4)) * 2)")
    assert run_text(program) == "20\n"


def test_each_call_has_its_own_variables():
    functions = "fn inner(x: Int) -> Int {\n    let local = x * 2\n    return local\n}"
    assert run_text(with_main(functions, "let local = 1\nprint(inner(5))\nprint(local)")) == "10\n1\n"


def test_a_function_does_not_see_the_variables_of_its_caller():
    functions = "fn peek() -> Int {\n    return secret\n}"
    assert check_codes(with_main(functions, "let secret = 1\nprint(peek())")) == ["E2005"]


@pytest.mark.parametrize("call, count_text", [
    ("add(1)", "'add' takes 2 arguments, but 1 was given"),
    ("add()", "'add' takes 2 arguments, but 0 were given"),
    ("add(1, 2, 3)", "'add' takes 2 arguments, but 3 were given"),
])
def test_wrong_number_of_arguments(call, count_text):
    error = only(with_main(ADD, f"print({call})"))
    assert (error.code, error.category) == ("E2009", "type")
    assert error.label == count_text
    assert error.notes == ("Its signature is: fn add(a: Int, b: Int) -> Int",)


def test_wrong_argument_type():
    error = only(with_main(ADD, 'print(add(1, "2"))'))
    assert error.code == "E2011"
    assert error.label == "Expected Int, found Text"
    assert (error.span.line, error.span.column) == (6, 18)
    assert error.notes == ("This is the argument for 'b' in: fn add(a: Int, b: Int) -> Int",)


def test_each_wrong_argument_is_reported():
    assert check_codes(with_main(ADD, "print(add(1.5, true))")) == ["E2011", "E2011"]


def test_int_is_not_accepted_where_float_is_expected():
    functions = "fn half(value: Float) -> Float {\n    return value / 2.0\n}"
    error = only(with_main(functions, "print(half(4))"))
    assert error.label == "Expected Float, found Int"
    assert error.hint == "Convert the Int explicitly with to_float(...)."
    assert run_text(with_main(functions, "print(half(to_float(4)))")) == "2.0\n"


def test_unknown_function():
    error = only(with_main(ADD, "print(ad(1, 2))"))
    assert error.code == "E2008"
    assert error.label == "There is no function named 'ad'"
    assert error.hint == "Did you mean 'add'?"
    assert only(in_main("launch()")).hint is None


def test_the_result_type_of_a_call_is_checked():
    assert check_codes(with_main(ADD, 'let s: Text = add(1, 2)')) == ["E2011"]
    assert check_codes(with_main(ADD, "let n = add(1, 2) + 0.5")) == ["E2011"]


def test_a_returned_value_must_be_used():
    error = only(with_main(ADD, "add(1, 2)"))
    assert error.code == "E2010"
    assert error.label == "The Int returned by 'add' is never used"


def test_a_function_is_not_a_value():
    assert check_codes(with_main(ADD, "let f = add")) == ["E2011"]


# Declarations

def test_duplicate_function():
    error = only(ADD + "\n" + ADD + "\nfn main() -> Void {}")
    assert error.code == "E2002"
    assert error.span.line == 4


def test_duplicate_parameter():
    error = only("fn f(a: Int, a: Int) -> Void {}\nfn main() -> Void {}")
    assert error.code == "E2006"
    assert (error.span.line, error.span.column) == (1, 14)


@pytest.mark.parametrize("declaration, code", [
    ("fn f(a: Void) -> Void {}", "E2012"),       # a parameter has to hold a value
    ("fn f(a: Number) -> Void {}", "E2012"),     # unknown parameter type
    ("fn f() -> Number {}", "E2012"),            # unknown return type
    ("fn f(result: Int) -> Void {}", "E2013"),   # 'result' is the return value in 'ensures'
    ("fn f(print: Int) -> Void {}", "E2006"),    # a parameter cannot take the name of a function
    ("fn f(f: Int) -> Void {}", "E2006"),
])
def test_invalid_declarations(declaration, code):
    assert check_codes(declaration + "\nfn main() -> Void {}") == [code]


def test_one_namespace_for_functions_and_variables():
    assert check_codes(with_main(ADD, "let add = 1")) == ["E2006"]
    functions = "fn f(a: Int) -> Int {\n    let a = 2\n    return a\n}"
    assert check_codes(with_main(functions, "print(f(1))")) == ["E2006"]


def test_parameters_are_immutable():
    functions = "fn f(a: Int) -> Int {\n    a = 2\n    return a\n}"
    assert check_codes(with_main(functions, "print(f(1))")) == ["E2007"]


# Return

def test_return_type_mismatch():
    error = only(with_main('fn f() -> Int {\n    return "text"\n}', "print(f())"))
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == "Expected Int, found Text"
    assert error.notes == ("'f' is declared to return Int.",)
    assert (error.span.line, error.span.column) == (2, 12)


def test_missing_return():
    error = only(with_main("fn f() -> Int {\n    let x = 1\n}", "print(f())"))
    assert error.code == "E2014"
    assert (error.span.line, error.span.column) == (1, 4)


def test_return_without_a_value_in_a_function_that_returns_one():
    assert check_codes(with_main("fn f() -> Int {\n    return\n}", "print(f())")) == ["E2011"]


def test_return_with_a_value_in_a_void_function():
    error = only(with_main("fn f() -> Void {\n    return 1\n}", "f()"))
    assert error.code == "E2011"
    assert error.label == "'f' returns Void, so 'return' cannot be followed by a value"
    assert check_codes(in_main("return 1")) == ["E2011"]


def test_void_functions():
    functions = 'fn log(message: Text) -> Void {\n    print("log: " + message)\n}'
    assert run_text(with_main(functions, 'log("a")\nlog("b")')) == "log: a\nlog: b\n"
    # A Void call has no value to store, print, pass on or return.
    assert check_codes(with_main(functions, 'let x = log("a")')) == ["E2011"]
    assert check_codes(with_main(functions, 'print(log("a"))')) == ["E2011"]
    assert check_codes(with_main(functions, 'let x = log("a") + 1')) == ["E2011"]


def test_bare_return_leaves_a_void_function_early():
    functions = 'fn f(stop: Bool) -> Void {\n    print("a")\n    if stop {\n        return\n    }\n    print("b")\n}'
    assert run_text(with_main(functions, "f(true)\nf(false)")) == "a\na\nb\n"
    assert run_text(in_main('print("x")\nreturn')) == "x\n"


def test_unreachable_code_after_return():
    error = only(with_main("fn f() -> Int {\n    return 1\n    print(2)\n    print(3)\n}", "print(f())"))
    assert error.code == "E2015"
    assert error.span.line == 3


# Return paths through 'if'

@pytest.mark.parametrize("body", [
    "if n > 0 {\n        return 1\n    }",                                               # the 'if' can be skipped
    "if n > 0 {\n        return 1\n    } else {\n        print(n)\n    }",                # 'else' does not return
    "if n > 0 {\n        print(n)\n    } else {\n        return 1\n    }",                # 'then' does not return
    "if n > 0 {\n        return 1\n    } else if n < 0 {\n        return 2\n    }",       # no final 'else'
    "{\n        if n > 0 {\n            return 1\n        }\n    }",
])
def test_paths_that_can_end_without_a_return(body):
    assert check_codes(with_main(f"fn f(n: Int) -> Int {{\n    {body}\n}}", "print(f(1))")) == ["E2014"]


@pytest.mark.parametrize("body", [
    "if n > 0 {\n        return 1\n    }\n    return 0",
    "if n > 0 {\n        return 1\n    } else {\n        return 0\n    }",
    "if n > 0 {\n        return 1\n    } else if n < 0 {\n        return 2\n    } else {\n        return 0\n    }",
    "{\n        return 1\n    }",
])
def test_paths_that_always_return(body):
    assert check_codes(with_main(f"fn f(n: Int) -> Int {{\n    {body}\n}}", "print(f(1))")) == []


# if / else at run time

SIGN = (
    'fn sign(n: Int) -> Text {\n    if n < 0 {\n        return "negative"\n    } else if n == 0 {\n'
    '        return "zero"\n    } else {\n        return "positive"\n    }\n}'
)


def test_if_else_chain():
    assert run_text(with_main(SIGN, "print(sign(-5))\nprint(sign(0))\nprint(sign(9))")) == "negative\nzero\npositive\n"


def test_if_without_else_and_scopes():
    body = 'let n = 3\nif n > 2 {\n    let inside = n * 2\n    print(inside)\n}\nif n > 5 {\n    print("never")\n}\nprint("end")'
    assert run_text(in_main(body)) == "6\nend\n"
    assert check_codes(in_main("if true {\n    let inside = 1\n}\nprint(inside)")) == ["E2005"]


def test_both_branches_may_declare_the_same_name():
    assert check_codes(in_main("if true {\n    let x = 1\n    print(x)\n} else {\n    let x = 2\n    print(x)\n}")) == []


# Recursion

def test_recursion():
    functions = "fn factorial(n: Int) -> Int {\n    if n <= 1 {\n        return 1\n    }\n    return n * factorial(n - 1)\n}"
    assert run_text(with_main(functions, "print(factorial(5))\nprint(factorial(20))")) == "120\n2432902008176640000\n"


def test_fibonacci():
    functions = "fn fib(n: Int) -> Int {\n    if n < 2 {\n        return n\n    }\n    return fib(n - 1) + fib(n - 2)\n}"
    assert run_text(with_main(functions, "print(fib(15))")) == "610\n"


def test_mutual_recursion():
    functions = (
        "fn is_even(n: Int) -> Bool {\n    if n == 0 {\n        return true\n    }\n    return is_odd(n - 1)\n}\n"
        "fn is_odd(n: Int) -> Bool {\n    if n == 0 {\n        return false\n    }\n    return is_even(n - 1)\n}"
    )
    assert run_text(with_main(functions, "print(is_even(10))\nprint(is_even(7))")) == "true\nfalse\n"


COUNT = "fn count(n: Int) -> Int {\n    if n == 0 {\n        return 0\n    }\n    return 1 + count(n - 1)\n}"


def test_deep_recursion_below_the_limit_works():
    depth = MAX_CALL_DEPTH - 2
    assert run_text(with_main(COUNT, f"print(count({depth}))")) == f"{depth}\n"


def test_unbounded_recursion_is_a_clean_runtime_error():
    functions = "fn forever(n: Int) -> Int {\n    return forever(n + 1)\n}"
    output, error = run_failure(with_main(functions, 'print("start")\nprint(forever(0))'))
    assert output == "start\n"
    assert (error.code, error.category) == ("E3004", "runtime")
    assert error.span.line == 2
    assert any("more call" in note for note in error.notes)


def test_recursion_past_the_limit_is_reported_not_crashed():
    _, error = run_failure(with_main(COUNT, f"print(count({MAX_CALL_DEPTH + 50}))"))
    assert error.code == "E3004"


def test_overflow_inside_a_function_reports_the_call_chain():
    functions = "fn factorial(n: Int) -> Int {\n    if n <= 1 {\n        return 1\n    }\n    return n * factorial(n - 1)\n}"
    _, error = run_failure(with_main(functions, "print(factorial(25))"))
    assert error.code == "E3002"
    assert error.notes[0] == "In 'factorial', called at line 5, column 16."
    assert error.notes[-1] == "In 'factorial', called at line 9, column 11."


def test_main_can_be_called_like_any_function():
    assert check_codes("fn helper() -> Void {\n    main()\n}\nfn main() -> Void {}") == []


def test_a_void_call_cannot_be_returned_as_a_value():
    functions = 'fn log() -> Void {\n    print("x")\n}\nfn f() -> Int {\n    return log()\n}'
    error = only(with_main(functions, "print(f())"))
    assert error.code == "E2011"
    assert error.label == "This call does not produce a value to return"

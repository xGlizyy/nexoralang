"""The `?` operator: the value of a `Some` or an `Ok`, or an early return of the `None` or the `Err`.

Decision 0028.
"""

from helpers import check_codes, diagnostics_of, run_failure, run_text, parse_text

from nexora import ast_nodes as ast

PARSE = """
fn parse(text: Text) gives Result[Int, Text] {
    if Int.can_parse(text) {
        return Ok(Int.parse(text))
    }
    return Err("bad " + text)
}
"""

FIRST = """
fn first(names: List[Text]) gives Option[Text] {
    if List.length(names) == 0 {
        return None
    }
    return Some(List.get(names, 0))
}
"""


def test_a_result_gives_its_value_and_continues():
    assert run_text(PARSE + """
fn double(text: Text) gives Result[Int, Text] {
    let n = parse(text)?
    return Ok(n * 2)
}

fn main() {
    print(double("21"))
}
""") == "Ok(42)\n"


def test_an_err_ends_the_function_unchanged():
    assert run_text(PARSE + """
fn double(text: Text) gives Result[Int, Text] {
    print("before")
    let n = parse(text)?
    print("after")
    return Ok(n * 2)
}

fn main() {
    print(double("x"))
}
""") == "before\nErr(bad x)\n"


def test_an_option_gives_its_value_or_returns_none():
    assert run_text(FIRST + """
fn shout(names: List[Text]) gives Option[Text] {
    let name = first(names)?
    return Some(name + "!")
}

fn main() {
    print(shout(["ada"]))
    print(shout([]))
}
""") == "Some(ada!)\nNone\n"


def test_it_works_inside_a_larger_expression_and_in_arguments():
    assert run_text(PARSE + """
fn sum(a: Text, b: Text) gives Result[Int, Text] {
    return Ok(parse(a)? + parse(b)? * 10)
}

fn main() {
    print(sum("1", "2"))
    print(sum("1", "z"))
    print(sum("q", "z"))
}
""") == "Ok(21)\nErr(bad z)\nErr(bad q)\n"


def test_it_returns_from_inside_loops_and_branches():
    assert run_text(PARSE + """
fn total(items: List[Text]) gives Result[Int, Text] {
    var sum = 0
    for item in items {
        if item != "skip" {
            sum = sum + parse(item)?
        }
    }
    return Ok(sum)
}

fn main() {
    print(total(["1", "skip", "2"]))
    print(total(["1", "oops", "2"]))
}
""") == "Ok(3)\nErr(bad oops)\n"


def test_questions_can_be_chained_over_nested_options():
    assert run_text("""
fn flatten(value: Option[Option[Int]]) gives Option[Int] {
    return Some(value??)
}

fn main() {
    let inner: Option[Int] = None
    let nothing: Option[Option[Int]] = None
    print(flatten(Some(Some(3))))
    print(flatten(Some(inner)))
    print(flatten(nothing))
}
""") == "Some(3)\nNone\nNone\n"


def test_the_promises_are_checked_on_the_early_return():
    output, error = run_failure(PARSE + """
fn positive(text: Text) gives Result[Int, Text]
promises Result.is_ok(result)
{
    let n = parse(text)?
    return Ok(n)
}

fn main() {
    print(positive("x"))
}
""")
    assert error.code == "E4002"
    assert output == ""


def test_a_failure_of_the_callee_still_stops_the_program():
    # `?` does not catch run-time failures, only the `None` and the `Err`.
    _, error = run_failure("""
fn divide(a: Int, b: Int) gives Result[Int, Text] {
    return Ok(a / b)
}

fn run_it(b: Int) gives Result[Int, Text] {
    let n = divide(1, b)?
    return Ok(n)
}

fn main() {
    print(run_it(0))
}
""")
    assert error.code == "E3001"


def test_precedence_is_tighter_than_unary_and_binary_operators():
    program, errors = parse_text("""
fn f(a: Int) gives Result[Int, Text] {
    return Ok(-g(a)? + 1)
}
""")
    assert errors == []
    call = program.functions[0].body.statements[0].value.arguments[0]
    assert isinstance(call, ast.Binary)
    assert isinstance(call.left, ast.Unary)
    assert isinstance(call.left.operand, ast.Try)
    assert isinstance(call.left.operand.operand, ast.Call)


def test_a_non_option_operand_is_e2036():
    assert check_codes("""
fn f() gives Option[Int] {
    let n = 5?
    return Some(n)
}
fn main() {
}
""") == ["E2036"]


def test_the_function_has_to_give_the_same_kind():
    assert check_codes(PARSE + """
fn f(text: Text) gives Option[Int] {
    let n = parse(text)?
    return Some(n)
}
fn g(text: Text) gives Int {
    return parse(text)?
}
fn main() {
}
""") == ["E2036", "E2036"]


def test_the_error_type_has_to_be_the_same():
    diagnostics = diagnostics_of(PARSE + """
fn f(text: Text) gives Result[Int, Int] {
    let n = parse(text)?
    return Ok(n)
}
fn main() {
}
""")
    assert [d.code for d in diagnostics] == ["E2036"]
    assert "Result[..., Text]" in (diagnostics[0].hint or "")


def test_the_value_can_be_a_different_type_from_the_one_returned():
    assert check_codes(PARSE + """
fn f(text: Text) gives Result[Bool, Text] {
    let n = parse(text)?
    return Ok(n > 1)
}
fn main() {
}
""") == []


def test_main_cannot_use_it():
    assert check_codes(PARSE + """
fn main() {
    let n = parse("1")?
}
""") == ["E2036"]


def test_it_is_not_valid_in_clauses_or_refined_types():
    assert check_codes(PARSE + """
fn f(text: Text) gives Int
needs parse(text)? > 0
{
    return 1
}
fn main() {
}
""") == ["E2036"]


def test_a_question_mark_alone_is_a_syntax_error():
    _, errors = parse_text("""
fn main() {
    let n = ?
}
""")
    assert [e.code for e in errors] == ["E1101"]

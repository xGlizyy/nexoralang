"""`Option` and `Result`: the two variants of each, their inspection and their failures.

Decision 0016. These are the values a program uses to say "there is nothing here" or
"this failed", without exceptions: `None` is not `Some(x)`, and `Ok(x)` is not `Err(x)`,
even when both carry the same value.
"""

from helpers import check_codes, diagnostics_of, run_failure, run_text


def test_some_carries_a_value_and_none_carries_none():
    assert run_text("""
fn main() {
    let found: Option[Int] = Some(42)
    print(Option.is_some(found))
    print(Option.is_none(found))
    print(Option.value_or(found, 0))
}
""") == "true\nfalse\n42\n"


def test_none_is_the_absence_of_a_value():
    assert run_text("""
fn main() {
    let missing: Option[Int] = None
    print(Option.is_some(missing))
    print(Option.is_none(missing))
    print(Option.value_or(missing, 7))
}
""") == "false\ntrue\n7\n"


def test_the_payload_can_be_read_when_there_is_one():
    assert run_text("""
fn main() {
    let found: Option[Text] = Some("hello")
    print(Option.value(found))
}
""") == "hello\n"


def test_the_variants_are_told_apart_even_with_equal_payloads():
    assert run_text("""
fn main() {
    let some_value: Option[Int] = Some(1)
    let none_value: Option[Int] = None
    print(some_value == some_value)
    print(some_value == none_value)
    print(none_value == some_value)
    print(none_value == none_value)
}
""") == "true\nfalse\nfalse\ntrue\n"


def test_ok_and_err_are_told_apart_even_with_equal_payloads():
    assert run_text("""
fn main() {
    let good: Result[Int, Text] = Ok(1)
    let bad: Result[Int, Text] = Err("boom")
    print(good == good)
    print(good == bad)
    print(bad == good)
    print(bad == bad)
}
""") == "true\nfalse\nfalse\ntrue\n"


def test_none_is_not_some_of_the_same_value():
    # There is no null in NEXORA, so there is no value that is both an absence and a presence.
    assert run_text("""
fn main() {
    let missing: Option[Int] = None
    let present: Option[Int] = Some(0)
    print(missing == present)
}
""") == "false\n"


def test_a_result_tells_success_from_failure():
    assert run_text("""
fn main() {
    let good: Result[Int, Text] = Ok(1)
    let bad: Result[Int, Text] = Err("boom")
    print(Result.is_ok(good))
    print(Result.is_err(good))
    print(Result.is_ok(bad))
    print(Result.is_err(bad))
    print(Result.value_or(good, 0))
    print(Result.value_or(bad, 0))
}
""") == "true\nfalse\nfalse\ntrue\n1\n0\n"


def test_the_error_is_kept_as_it_was():
    assert run_text("""
fn main() {
    let bad: Result[Int, Text] = Err("the file is missing")
    print(Result.error(bad))
}
""") == "the file is missing\n"


def test_the_payloads_can_be_nested():
    assert run_text("""
fn main() {
    let inner: Option[Int] = Some(3)
    let outer: Option[Option[Int]] = Some(inner)
    let empty: Option[Int] = None
    print(Option.is_some(outer))
    print(Option.value_or(outer, empty))
}
""") == "true\nSome(3)\n"


def test_a_value_is_printed_as_it_was_built():
    assert run_text("""
fn main() {
    let found: Option[Int] = Some(1)
    let missing: Option[Int] = None
    let good: Result[Int, Text] = Ok(1)
    let bad: Result[Int, Text] = Err("boom")
    print(found)
    print(missing)
    print(good)
    print(bad)
}
""") == "Some(1)\nNone\nOk(1)\nErr(boom)\n"


def test_to_text_writes_the_value_the_same_way():
    assert run_text("""
fn main() {
    let found: Option[Int] = Some(1)
    print(to_text(found))
}
""") == "Some(1)\n"


def test_an_optional_lookup():
    # The shape of a lookup that may not find anything.
    source = """
fn find(names: List[Text], wanted: Text) gives Option[Int] {
    var index = 0
    while index < List.length(names)
    shrinks List.length(names) - index, "Each turn looks at one more name"
    {
        if List.get(names, index) == wanted {
            return Some(index)
        }
        index = index + 1
    }
    return None
}

fn main() {
    let names = ["a", "b", "c"]
    print(Option.value_or(find(names, "b"), -1))
    print(Option.value_or(find(names, "z"), -1))
}
"""
    assert run_text(source) == "1\n-1\n"


def test_a_parsing_that_may_fail():
    source = """
fn parse(text: Text) gives Result[Int, Text] {
    if Int.can_parse(text) {
        return Ok(Int.parse(text))
    }
    return Err("not a whole number")
}

fn main() {
    print(Result.value_or(parse("42"), -1))
    print(Result.is_err(parse("x")))
    print(Result.error(parse("x")))
}
"""
    assert run_text(source) == "42\ntrue\nnot a whole number\n"


def test_the_caller_tells_an_absence_from_a_failure():
    source = """
fn lookup(text: Text) gives Option[Int] {
    if Int.can_parse(text) {
        return Some(Int.parse(text))
    }
    return None
}

fn divide(a: Int, b: Int) gives Result[Int, Text] {
    if b == 0 {
        return Err("division by zero")
    }
    return Ok(a / b)
}

fn main() {
    let absent = lookup("x")
    let failed = divide(1, 0)
    print(Option.is_none(absent))
    print(Result.is_err(failed))
}
"""
    assert run_text(source) == "true\ntrue\n"


def test_the_functions_compose():
    source = """
fn parse(text: Text) gives Result[Int, Text] {
    if Int.can_parse(text) {
        return Ok(Int.parse(text))
    }
    return Err("not a whole number")
}

fn double(text: Text) gives Result[Int, Text] {
    let number = parse(text)
    if Result.is_err(number) {
        return Err("the number is not there")
    }
    return Ok(Result.value(number) * 2)
}

fn main() {
    print(Result.value_or(double("21"), 0))
    print(Result.value_or(double("x"), 0))
}
"""
    assert run_text(source) == "42\n0\n"


def test_a_function_can_return_an_option_and_a_result():
    source = """
fn find(text: Text) gives Option[Int] {
    if Int.can_parse(text) {
        return Some(Int.parse(text))
    }
    return None
}

fn parse(text: Text) gives Result[Int, Text] {
    let number = find(text)
    if Option.is_none(number) {
        return Err("not a whole number")
    }
    return Ok(Option.value(number))
}

fn main() {
    print(Result.value_or(parse("7"), 0))
    print(Result.is_err(parse("x")))
}
"""
    assert run_text(source) == "7\ntrue\n"


def test_reading_the_payload_of_an_option_without_a_value_fails():
    output, error = run_failure("""
fn main() {
    let missing: Option[Int] = None
    print(Option.value(missing))
}
""")
    assert (error.code, error.category) == ("E3011", "runtime")
    assert error.label == "This Option has no value"


def test_reading_the_value_of_a_failed_result_fails():
    output, error = run_failure("""
fn main() {
    let bad: Result[Int, Text] = Err("boom")
    print(Result.value(bad))
}
""")
    assert (error.code, error.category) == ("E3012", "runtime")
    assert error.label == "This Result is an error: \"boom\""


def test_reading_the_error_of_a_successful_result_fails():
    output, error = run_failure("""
fn main() {
    let good: Result[Int, Text] = Ok(1)
    print(Result.error(good))
}
""")
    assert (error.code, error.category) == ("E3013", "runtime")
    assert error.label == "This Result is not an error"


def test_the_type_of_a_payload_is_checked():
    (error,) = diagnostics_of("""
fn main() {
    let wrong: Option[Int] = Some("text")
}
""")
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == "Expected Option[Int], found Option[Text]"


def test_the_error_type_of_a_result_is_checked():
    (error,) = diagnostics_of("""
fn main() {
    let wrong: Result[Int, Text] = Err(1)
}
""")
    assert (error.code, error.category) == ("E2011", "type")


def test_the_two_variants_of_a_result_do_not_mix():
    (error,) = diagnostics_of("""
fn main() {
    let wrong: Result[Int, Text] = Ok("text")
}
""")
    assert (error.code, error.category) == ("E2011", "type")


def test_a_value_that_is_not_an_option_is_refused():
    assert check_codes("""
fn main() {
    let wrong: Option[Int] = 1
}
""") == ["E2011"]


def test_none_needs_a_type_that_says_which_option_it_is():
    (error,) = diagnostics_of("""
fn main() {
    let missing = None
}
""")
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == "Cannot infer the type of None without an expected type"


def test_an_ok_needs_the_type_of_its_error():
    (error,) = diagnostics_of("""
fn main() {
    let good = Ok(1)
}
""")
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == "Cannot infer the error type of this Result"


def test_an_err_needs_the_type_of_its_value():
    (error,) = diagnostics_of("""
fn main() {
    let bad = Err("boom")
}
""")
    assert (error.code, error.category) == ("E2011", "type")
    assert error.label == "Cannot infer the item type of this Result"


def test_a_type_argument_that_is_not_there_is_refused():
    assert check_codes("""
fn main() {
    let wrong: Option = Some(1)
}
""") == ["E2012"]


def test_the_number_of_type_arguments_is_checked():
    assert check_codes("""
fn main() {
    let wrong: Result[Int] = Ok(1)
}
""") == ["E1101"]


def test_the_inspection_needs_the_right_type():
    assert check_codes("""
fn main() {
    let wrong: Int = Option.is_some(1)
}
""") == ["E2011"]


def test_a_comparison_with_none_knows_which_option_it_is():
    assert run_text("""
fn main() {
    let missing: Option[Int] = None
    let present: Option[Int] = Some(1)
    print(missing == None)
    print(present == None)
}
""") == "true\nfalse\n"

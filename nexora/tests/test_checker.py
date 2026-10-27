"""Static checks: what `nex check` reports without running the program."""

import pytest

from nexora.diagnostics import Source
from nexora.pipeline import analyze

from helpers import check_codes, in_main


def diagnostics(text: str):
    return analyze(Source("test.nex", text)).diagnostics


def test_valid_program_has_no_diagnostics():
    assert check_codes(in_main('let name = "NEXORA"\nprint(name)\nprint(1 + 2 * 3)')) == []


# The main function

def test_missing_main():
    (error,) = diagnostics("// nothing here\n")
    assert error.code == "E2001"
    assert error.span is None
    assert check_codes("") == ["E2001"]


def test_a_program_with_other_functions_still_needs_main():
    assert check_codes("fn main() {}\nfn helper() {}\n") == []
    assert check_codes("fn helper() {}\n") == ["E2001"]


def test_duplicate_main():
    (error,) = diagnostics("fn main() {}\nfn main() {}\n")
    assert error.code == "E2002"
    assert error.span.line == 2
    assert error.notes == ("It was first declared at line 1, column 4.",)


def test_main_must_return_void():
    assert check_codes("fn main() gives Int {\n    return 1\n}") == ["E2004"]
    assert check_codes("fn main() gives Nothing {}") == ["E2012"]


def test_main_takes_no_parameters():
    (error,) = diagnostics("fn main(count: Int) {}")
    assert error.code == "E2013"
    assert (error.span.column, error.span.end_column) == (9, 19)


# Variables and scopes

def test_unknown_variable():
    (error,) = diagnostics(in_main("print(missing)"))
    assert error.code == "E2005"
    assert (error.span.line, error.span.column) == (2, 11)
    assert error.hint == "Declare it first with 'let'."


def test_unknown_variable_suggests_a_similar_name():
    (error,) = diagnostics(in_main("let total = 1\nprint(totl)"))
    assert error.hint == "Did you mean 'total'?"


def test_variable_cannot_be_used_before_its_declaration():
    assert check_codes(in_main("print(later)\nlet later = 1")) == ["E2005"]


def test_variable_is_not_visible_in_its_own_initialiser():
    assert check_codes(in_main("let x = x")) == ["E2005"]


def test_duplicate_declaration_in_the_same_scope():
    (error,) = diagnostics(in_main("let x = 1\nlet x = 2"))
    assert error.code == "E2006"
    assert error.span.line == 3
    assert error.notes == ("It was first declared at line 2, column 9.",)


def test_inner_block_reads_outer_variables():
    assert check_codes(in_main("let x = 1\n{\n    print(x)\n}")) == []


def test_inner_block_cannot_redeclare_a_visible_name():
    assert check_codes(in_main("let x = 1\n{\n    let x = 2\n}")) == ["E2006"]


def test_block_variables_end_with_the_block():
    assert check_codes(in_main("{\n    let inner = 1\n}\nprint(inner)")) == ["E2005"]


def test_sibling_blocks_may_reuse_a_name():
    assert check_codes(in_main("{\n    let x = 1\n    print(x)\n}\n{\n    let x = 2\n    print(x)\n}")) == []


def test_reassignment_is_rejected():
    (error,) = diagnostics(in_main("let x = 1\nx = 2"))
    assert error.code == "E2007"
    assert (error.span.line, error.span.column) == (3, 5)


def test_assignment_to_an_unknown_name():
    assert check_codes(in_main("x = 2")) == ["E2005"]


def test_builtin_name_cannot_be_declared():
    assert check_codes(in_main("let print = 1")) == ["E2006"]


# Calls

def test_unknown_function():
    (error,) = diagnostics(in_main("prnt(1)"))
    assert error.code == "E2008"
    assert error.hint == "Did you mean 'print'?"
    assert check_codes(in_main("open(1)")) == ["E2008"]


def test_calling_a_variable():
    assert check_codes(in_main("let x = 1\nx(2)")) == ["E2008"]


@pytest.mark.parametrize("call", ["print()", "print(1, 2)"])
def test_print_takes_exactly_one_argument(call):
    assert check_codes(in_main(call)) == ["E2009"]


def test_print_has_no_value():
    assert check_codes(in_main("let x = print(1)")) == ["E2011"]
    assert check_codes(in_main("print(print(1))")) == ["E2011"]


def test_print_without_parentheses_is_not_a_value():
    assert check_codes(in_main("let x = print")) == ["E2011"]


def test_unused_expression_value():
    (error,) = diagnostics(in_main("40 + 2"))
    assert error.code == "E2010"
    assert check_codes(in_main('"text"')) == ["E2010"]


# Types

@pytest.mark.parametrize("expression", [
    "1 + 2", "1 - 2", "1 * 2", "1 / 2",
    "1.5 + 2.5", "1.5 - 2.5", "1.5 * 2.5", "1.5 / 2.5",
    '"a" + "b"', "-1", "-1.5", "-(1 + 2)", "(1 + 2) * (3 - 4)",
])
def test_valid_operations(expression):
    assert check_codes(in_main(f"let x = {expression}\nprint(x)")) == []


@pytest.mark.parametrize("expression", [
    '1 + "a"', '"a" + 1', "1 + 1.5", "1.5 * 2", "true + 1", "true + false",
    '"a" - "b"', '"a" * 2', '"a" / "b"', "1 + true", '-"a"', "-true",
])
def test_type_mismatches(expression):
    assert check_codes(in_main(f"let x = {expression}")) == ["E2011"]


def test_type_mismatch_points_at_the_operator_and_names_both_types():
    (error,) = diagnostics(in_main('let total = 10 + "5"'))
    assert error.label == "Cannot apply '+' to Int and Text"
    assert (error.span.line, error.span.column, error.span.end_column) == (2, 20, 21)


def test_types_follow_variables():
    assert check_codes(in_main('let a = 1\nlet b = "x"\nlet c = a + b')) == ["E2011"]
    assert check_codes(in_main("let a = 1.5\nlet b = a * 2.0\nlet c = b + 1")) == ["E2011"]


def test_one_mistake_is_reported_once():
    # 'missing' is unknown; the operations that use it are not reported again.
    assert check_codes(in_main("let x = missing + 1\nlet y = x * 2\nprint(y)")) == ["E2005"]


def test_all_independent_errors_are_reported():
    codes = check_codes(in_main('let a = 1 + "x"\nprint(b)\na = 2\nprint(1, 2)'))
    assert codes == ["E2011", "E2005", "E2007", "E2009"]


# Stages

def test_lexical_errors_stop_before_parsing():
    assert check_codes("fn main() {\n    let x = @\n}") == ["E1001"]


def test_syntax_errors_stop_before_the_semantic_checks():
    assert check_codes(in_main("let = 1\nprint(missing)")) == ["E1101"]

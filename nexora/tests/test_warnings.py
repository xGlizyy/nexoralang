"""Warnings: unused names (W2001), a `var` that never changes (W2002) and names outside snake_case (W2003).

A warning points at an improvement. It never stops a program, and it is only reported when the
file has no errors.
"""

import json
from pathlib import Path

import pytest

from helpers import diagnostics_of, in_main, run_text, with_main
from nexora import api, cli

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


COUNTING_LOOP = (
    "var i = 0\nwhile i < 3\n    keeps i >= 0\n    shrinks 3 - i, \"i moves towards 3\"\n{\n    i = i + 1\n}"
)


def warnings_of(text: str) -> list[tuple[str, int, str]]:
    """(code, line, message) of every diagnostic, which must all be warnings."""
    found = diagnostics_of(text)
    assert all(diagnostic.severity == "warning" for diagnostic in found), found
    return [(diagnostic.code, diagnostic.span.line, diagnostic.message) for diagnostic in found]


def codes_of(text: str) -> list[str]:
    return [code for code, _, _ in warnings_of(text)]


# W2001: unused variables

def test_an_unused_local_variable_is_reported_where_it_is_declared():
    diagnostic = diagnostics_of(in_main("let unused = 1"))[0]
    assert (diagnostic.code, diagnostic.message) == ("W2001", "Unused variable")
    assert diagnostic.label == "The variable 'unused' is never used"
    assert (diagnostic.span.line, diagnostic.span.column) == (2, 9)


def test_a_variable_that_is_read_is_not_reported():
    assert codes_of(in_main("let used = 1\nprint(used)")) == []


def test_a_variable_read_in_a_nested_scope_is_used():
    text = in_main("let limit = 3\nif true {\n    print(limit)\n}")
    assert codes_of(text) == []


def test_a_variable_read_only_in_a_condition_or_a_loop_is_used():
    text = in_main(COUNTING_LOOP)
    assert codes_of(text) == []


def test_a_variable_that_only_receives_assignments_is_unused():
    # Writing a value is not reading it.
    assert codes_of(in_main("var total = 0\ntotal = 5")) == ["W2001"]


def test_an_assignment_is_not_a_read_but_the_right_hand_side_is():
    text = in_main("let step = 2\nvar total = 0\ntotal = total + step\nprint(total)")
    assert codes_of(text) == []


def test_a_variable_with_the_same_name_in_a_sibling_scope_is_judged_on_its_own():
    # The language does not allow hiding a visible name, but two blocks may reuse one.
    text = in_main("if true {\n    let value = 1\n    print(value)\n}\nif true {\n    let value = 2\n}")
    found = warnings_of(text)
    assert [(code, line) for code, line, _ in found] == [("W2001", 7)]


def test_an_unused_parameter_is_reported_and_a_used_one_is_not():
    text = with_main("fn first(a: Int, b: Int) gives Int { return a }", "print(first(1, 2))")
    diagnostic = diagnostics_of(text)[0]
    assert diagnostic.code == "W2001" and "'b'" in diagnostic.label
    assert len(diagnostics_of(text)) == 1


def test_a_parameter_named_underscore_is_never_reported():
    text = with_main("fn first(a: Int, _: Int) gives Int { return a }", "print(first(1, 2))")
    assert codes_of(text) == []


def test_a_parameter_used_only_in_a_contract_is_used():
    text = with_main(
        "fn positive(n: Int) gives Int\n    needs n > 0, \"Positive only\"\n{\n    return 1\n}",
        "print(positive(1))",
    )
    assert codes_of(text) == []


def test_an_unused_loop_iterator_is_reported():
    text = in_main("for item in [1, 2] {\n    print(1)\n}")
    diagnostic = diagnostics_of(text)[0]
    assert diagnostic.code == "W2001" and "iterator" in diagnostic.label


def test_a_used_loop_iterator_is_not_reported():
    assert codes_of(in_main("for item in [1, 2] {\n    print(item)\n}")) == []


def test_the_underscore_name_is_not_a_variable_to_report():
    assert codes_of(in_main("let _ = 1")) == []


def test_functions_are_not_reported_as_unused_variables():
    # A function that is never called is not a variable; this warning does not look at it.
    text = with_main("fn never_called() gives Int { return 1 }", "print(1)")
    assert codes_of(text) == []


# W2002: var that never changes

def test_a_var_that_is_never_reassigned_suggests_let():
    diagnostic = diagnostics_of(in_main("var count = 1\nprint(count)"))[0]
    assert diagnostic.code == "W2002"
    assert "never reassigned" in diagnostic.message
    assert "let" in diagnostic.hint
    assert (diagnostic.span.line, diagnostic.span.column) == (2, 9)


def test_a_let_that_is_never_reassigned_is_fine():
    assert codes_of(in_main("let count = 1\nprint(count)")) == []


def test_a_var_reassigned_in_a_branch_is_not_reported():
    text = in_main("var label = \"a\"\nif true {\n    label = \"b\"\n}\nprint(label)")
    assert codes_of(text) == []


def test_a_var_reassigned_in_a_loop_is_not_reported():
    text = in_main("var total = 0\nfor n in [1, 2, 3] {\n    total = total + n\n}\nprint(total)")
    assert codes_of(text) == []


def test_a_var_reassigned_in_a_while_loop_is_not_reported():
    text = in_main(COUNTING_LOOP + "\nprint(i)")
    assert codes_of(text) == []


def test_a_var_reassigned_in_only_one_of_two_variables_reports_the_other():
    text = in_main("var a = 1\nvar b = 2\nb = b + 1\nprint(a)\nprint(b)")
    found = warnings_of(text)
    assert [(code, line) for code, line, _ in found] == [("W2002", 2)]


def test_an_unused_var_is_reported_as_unused_not_as_never_reassigned():
    # One warning per problem: suggesting `let` for a name nobody reads is noise.
    assert codes_of(in_main("var ignored = 1")) == ["W2001"]


# W2003: snake_case

@pytest.mark.parametrize("name", ["total", "total_count", "_private", "x1", "value_2", "a"])
def test_snake_case_variables_are_accepted(name):
    assert codes_of(in_main(f"let {name} = 1\nprint({name})")) == []


@pytest.mark.parametrize("name, suggestion", [
    ("camelCase", "camel_case"),
    ("PascalCase", "pascal_case"),
    ("totalCOUNT", "total_count"),
    ("HTTPServer", "http_server"),
    ("SHOUTING", "shouting"),
])
def test_names_outside_snake_case_are_reported_with_a_suggestion(name, suggestion):
    diagnostics = diagnostics_of(in_main(f"let {name} = 1\nprint({name})"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["W2003"]
    assert f"'{suggestion}'" in diagnostics[0].hint


def test_a_parameter_outside_snake_case_is_reported():
    text = with_main("fn double(someValue: Int) gives Int { return someValue * 2 }", "print(double(1))")
    diagnostics = diagnostics_of(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["W2003"]
    assert "parameter" in diagnostics[0].label


def test_a_private_function_outside_snake_case_is_reported():
    text = with_main("fn doubleIt(n: Int) gives Int { return n * 2 }", "print(doubleIt(1))")
    diagnostics = diagnostics_of(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["W2003"]
    assert "function" in diagnostics[0].label


def test_a_public_function_and_its_parameters_keep_their_spelling():
    # Another module calls them by these names: warning would invite a silent rename.
    text = with_main("pub fn doubleIt(someValue: Int) gives Int { return someValue * 2 }", "print(doubleIt(1))")
    assert codes_of(text) == []


def test_type_names_keep_pascal_case():
    text = "type Percent = Int where value >= 0 and value <= 100\ntype Point = { x: Int, y: Int }\n" + in_main(
        "let p: Percent = 5\nlet point = Point(x: 1, y: 2)\nprint(p)\nprint(point.x)"
    )
    assert codes_of(text) == []


def test_the_main_function_is_snake_case():
    assert codes_of(in_main("print(1)")) == []


# Warnings do not stop anything

def test_a_program_with_warnings_still_runs():
    text = in_main("let unused = 1\nvar changed_never = 2\nprint(changed_never)")
    assert codes_of(text) == ["W2001", "W2002"] or sorted(codes_of(text)) == ["W2001", "W2002"]
    assert run_text(text) == "2\n"


def test_analysis_with_only_warnings_is_ok_and_can_be_run():
    from nexora.diagnostics import Source
    analysis = api.analyze(Source("test.nex", in_main("let unused = 1")))
    assert analysis.ok
    assert analysis.checked is not None
    assert [diagnostic.code for diagnostic in analysis.diagnostics] == ["W2001"]


def test_warnings_are_not_reported_when_the_file_has_an_error():
    # `unused` would be a warning, but the program is already rejected for the other reason.
    text = in_main("let unused = 1\nlet wrong: Int = \"text\"\nprint(wrong)")
    found = diagnostics_of(text)
    assert found and all(diagnostic.severity == "error" for diagnostic in found)


def test_warnings_come_sorted_by_position():
    text = in_main("let badName = 1\nlet unused = 2\nvar never = 3\nprint(never)\nprint(badName)")
    found = diagnostics_of(text)
    positions = [(d.span.line, d.span.column) for d in found]
    assert positions == sorted(positions)


# The command line

def write(tmp_path, text: str) -> str:
    path = tmp_path / "program.nex"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_check_succeeds_and_prints_the_warnings(tmp_path, capsys):
    path = write(tmp_path, in_main("let unused = 1"))
    assert cli.main(["check", path]) == 0
    captured = capsys.readouterr()
    assert "W2001" in captured.err + captured.out
    assert "Check passed with 1 warning" in captured.out


def test_check_json_marks_the_severity_and_stays_ok(tmp_path, capsys):
    path = write(tmp_path, in_main("let unused = 1"))
    assert cli.main(["check", path, "--format", "json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is True
    assert [(item["code"], item["severity"]) for item in document["diagnostics"]] == [("W2001", "warning")]


def test_run_does_not_print_warnings_and_runs_the_program(tmp_path, capsys):
    path = write(tmp_path, in_main("let unused = 1\nprint(7)"))
    assert cli.main(["run", path]) == 0
    captured = capsys.readouterr()
    assert captured.out == "7\n"
    assert "W2001" not in captured.err


def test_a_file_without_warnings_says_so(tmp_path, capsys):
    path = write(tmp_path, in_main("let used = 1\nprint(used)"))
    assert cli.main(["check", path]) == 0
    assert "Check passed:" in capsys.readouterr().out


# The examples of the repository are the reference of good style

@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.nex")), ids=lambda path: path.name)
def test_the_examples_have_no_warnings(path):
    from nexora.diagnostics import Source
    from nexora.pipeline import analyze
    analysis = analyze(Source(str(path), path.read_text(encoding="utf-8")))
    assert [(d.code, d.span.line if d.span else 0) for d in analysis.diagnostics
            if d.severity == "warning"] == []


# Review of the semantics: the edges of each warning

def test_a_variable_that_only_feeds_itself_is_not_reported_by_design():
    # `x = x + 1` reads x. Proving that nobody observes the result needs data flow analysis, and a
    # false warning is worse than a missing one, so a self-assignment counts as a use.
    assert codes_of(in_main("var counter = 0\ncounter = counter + 1")) == []


def test_a_self_assignment_does_not_hide_the_variable_that_is_never_read_elsewhere():
    # The other variable is only written: it is still reported.
    text = in_main("var counter = 0\nvar last = 0\ncounter = counter + 1\nlast = counter")
    assert [(code, line) for code, line, _ in warnings_of(text)] == [("W2001", 3)]


def test_a_var_reassigned_in_the_else_branch_is_not_reported():
    text = in_main("var label = \"a\"\nif false {\n    print(1)\n} else {\n    label = \"b\"\n}\nprint(label)")
    assert codes_of(text) == []


def test_a_var_reassigned_in_a_nested_loop_is_not_reported():
    text = in_main(
        "var total = 0\nfor a in [1, 2] {\n    for b in [3, 4] {\n        total = total + a * b\n    }\n}\nprint(total)"
    )
    assert codes_of(text) == []


def test_a_var_reassigned_only_after_a_loop_is_not_reported():
    text = in_main("var total = 0\nfor a in [1, 2] {\n    print(a)\n}\ntotal = 9\nprint(total)")
    assert codes_of(text) == []


def test_a_public_type_keeps_its_pascal_case():
    text = "pub type Percent = Int where value >= 0 and value <= 100\n" + in_main("print(1)")
    assert codes_of(text) == []


def test_the_locals_of_a_public_function_are_still_checked():
    # Only the interface (name and parameters) is exempt; the body is private to the module.
    text = with_main("pub fn double(n: Int) gives Int {\n    let someLocal = n * 2\n    return someLocal\n}", "print(double(1))")
    diagnostics = diagnostics_of(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["W2003"]
    assert "'someLocal'" in diagnostics[0].label


def test_a_snake_case_name_with_digits_and_leading_underscore_is_accepted():
    assert codes_of(in_main("let _hidden1 = 1\nprint(_hidden1)")) == []


def test_there_is_no_constant_syntax_so_an_uppercase_variable_is_reported():
    # `const` is reserved but not implemented: until it exists, no spelling is exempt.
    assert codes_of(in_main("let LIMIT = 3\nprint(LIMIT)")) == ["W2003"]

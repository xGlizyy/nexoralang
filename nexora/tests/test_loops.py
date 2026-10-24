"""Variables declared with 'var', assignments and loops with their measure and invariants (decision 0010).

The numbers in brackets are the regression tests listed in the decision.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from helpers import check_codes, diagnostics_of, in_main, parse_text, run_failure, run_text, with_main
from nexora import api, ast_nodes as ast, interpreter, schemas, tooling
from nexora.interpreter import MAX_CALL_DEPTH

SCHEMAS = schemas.all_schemas()

SUM_TO = """
fn sum_to(n: Int) gives Int
    needs n >= 0, "Only natural numbers"
    promises result == n * (n + 1) / 2
{
    var total = 0
    var i = 0
    while i < n
        keeps total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        shrinks n - i, "Each turn moves i one step closer to n"
    {
        i = i + 1
        total = total + i
    }
    return total
}
"""


def loop(*lines: str, condition: str = "i < 3", setup: str = "var i = 0", after: str = "") -> str:
    """A main function with `setup`, a loop and `after`. The `keeps` and `shrinks` at the start of
    `lines` go in the header of the loop; the rest is its body."""
    lines = list(lines)
    clauses = []
    while lines and lines[0].split(" ", 1)[0] in ("keeps", "shrinks"):
        clauses.append(lines.pop(0))
    body = "\n".join(f"        {line}" for line in lines)
    if clauses:
        header = "".join(f"\n    {clause}" for clause in clauses)
        head = f"    while {condition}{header}\n    {{"
    else:
        head = f"    while {condition} {{"
    return f"fn main() {{\n    {setup}\n{head}\n{body}\n    }}\n    {after}\n}}\n"


# Syntax [1-4]

def test_var_while_invariant_and_decreases_are_keywords():
    from nexora.tokens import KEYWORDS, RESERVED_WORDS

    for word in ("var", "while", "for", "in", "keeps", "shrinks"):
        assert word in KEYWORDS and word not in RESERVED_WORDS
    assert {"break", "continue"} <= RESERVED_WORDS


def test_var_assignment_and_while_are_parsed_into_their_nodes():  # [1]
    program, errors = parse_text(with_main(SUM_TO, "print(sum_to(3))"))
    assert errors == []
    statements = program.functions[0].body.statements
    assert [type(statement).__name__ for statement in statements] == ["Var", "Var", "While", "Return"]
    loop_node = statements[2]
    assert [(clause.clause, clause.message) for clause in loop_node.clauses] == [
        ("keeps", "total is the sum of the numbers already added"),
        ("shrinks", "Each turn moves i one step closer to n"),
    ]
    assert [type(statement).__name__ for statement in loop_node.body.statements] == ["Assign", "Assign"]


def test_a_var_with_a_type_annotation():
    program, _ = parse_text(in_main("var total: Int = 0"))
    (statement,) = program.functions[0].body.statements
    assert isinstance(statement, ast.Var) and statement.declared_type.name == "Int"


@pytest.mark.parametrize("text, code", [
    (in_main("var x"), "E1101"),                              # [1] no value
    (in_main("while true"), "E1101"),                          # [1] no body
    (in_main("while {\n}"), "E1101"),                          # no condition
    (in_main("let x = 1\nx = y = 2"), "E1101"),                # [4] assignment is not an expression
    (in_main("var x = 1\nif x = 1 {\n}"), "E1101"),            # [4]
    (in_main("let keeps = 1"), "E1101"),                   # [4] a keyword now
    (in_main("let shrinks = 1"), "E1101"),
    (in_main("break"), "E1103"),                               # [2]
    (in_main("continue"), "E1103"),
])
def test_syntax_errors(text, code):
    assert check_codes(text)[0] == code


@pytest.mark.parametrize("word, hint", [
    ("break", "a loop ends when its condition is false or its list is exhausted, or with 'return'"),
    ("continue", "put the rest of the turn inside an 'if'"),
])
def test_reserved_loop_words_point_to_what_exists(word, hint):
    (error,) = diagnostics_of(in_main(word))
    assert error.code == "E1103" and hint in error.hint


@pytest.mark.parametrize("text, label", [  # [3]
    (in_main("keeps true"), "'keeps' goes between the head of the loop and its body"),
    (in_main("shrinks 1"), "'shrinks' goes between the head of the loop and its body"),
    (loop("shrinks 3 - i", "i = i + 1", "keeps true"), "'keeps' goes between the head of the loop"),
    (loop("shrinks 3 - i", "needs true"), "'needs' goes between the signature and the body"),
    (loop("shrinks 3 - i", "example true"), "'example' goes between the signature and the body"),
])
def test_misplaced_clauses(text, label):
    errors = [error for error in diagnostics_of(text) if error.code == "E1106"]
    assert errors and errors[0].label.startswith(label)


# Checking [5-10]

def test_assigning_a_var_of_the_same_or_an_outer_block():  # [5]
    text = in_main("var x = 1\nx = 2\nif true {\n    x = x + 1\n}\nprint(x)")
    assert check_codes(text) == []
    assert run_text(text) == "3\n"


def test_assigning_a_let_is_e2007_with_a_note_and_a_hint():  # [6]
    (error,) = diagnostics_of(in_main("let x = 1\nx = 2"))
    assert (error.code, error.label) == ("E2007", "'x' was declared with 'let' and cannot be given a new value")
    assert error.notes == ("'x' is declared at line 2, column 9.",)
    assert error.hint == "Declare it with 'var' if its value has to change."


def test_assigning_a_parameter_is_e2007():  # [6]
    (error,) = diagnostics_of(with_main("fn f(n: Int) gives Int {\n    n = 3\n    return n\n}", "print(f(1))"))
    assert (error.code, error.label) == ("E2007", "'n' is a parameter and cannot be given a new value")
    assert error.hint == "Copy it into a variable: 'var name = n'."


def test_assigning_an_unknown_name_is_e2005():
    assert check_codes(in_main("x = 1")) == ["E2005"]


@pytest.mark.parametrize("text, codes", [  # [7]
    (in_main('var x = 1\nx = "a"'), ["E2011"]),
    (in_main("var x: Float = 1.0\nx = 2"), ["E2011"]),
    (in_main('var x = 1\nx = print("a")'), ["E2011"]),
    (in_main("var x: Text = 1"), ["E2011"]),
    (in_main("var x: Void = 1"), ["E2012"]),
])
def test_an_assignment_keeps_the_type_of_the_variable(text, codes):
    assert check_codes(text) == codes


def test_a_float_assignment_suggests_the_conversion():
    (error,) = diagnostics_of(in_main("var x: Float = 1.0\nx = 2"))
    assert error.notes == ("'x' is declared as Float.",)
    assert "to_float" in error.hint


PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"\n'


@pytest.mark.parametrize("assignment, codes", [  # [7]
    ("p = 30", []),
    ("p = 120", ["E2017"]),
    ("p = p + 1", ["E2011"]),
    ("p = Percent(p + 1)", []),
])
def test_assignments_to_a_refined_variable_keep_its_guarantee(assignment, codes):
    assert check_codes(PERCENT + in_main(f"var p: Percent = 20\n{assignment}")) == codes


def test_a_refined_value_can_be_assigned_to_a_var_of_its_base():
    assert check_codes(PERCENT + in_main("var total = 0\nlet p: Percent = 20\ntotal = p")) == []


def test_constants_of_assignments_count_for_the_refinement_budget():  # [7]
    from nexora.checker import MAX_REFINEMENT_STEPS

    condition = " and ".join(["value >= 0"] * 50)
    assignments = "\n".join(["p = 1"] * (MAX_REFINEMENT_STEPS // 199 + 1))
    text = f"type Big = Int where {condition}\n" + in_main(f"var p: Big = 1\n{assignments}")
    assert "E2019" in check_codes(text)


def test_a_loop_without_a_measure_is_e2021():  # [8]
    (error,) = diagnostics_of(loop("i = i + 1"))
    assert (error.code, error.label) == ("E2021", "This loop does not say why it ends")
    assert (error.span.line, error.span.column, error.span.end_column) == (3, 5, 10)
    assert "shrinks n - i" in error.hint


def test_a_loop_with_two_measures_is_e2021_at_the_second():  # [8]
    (error,) = diagnostics_of(loop("shrinks 3 - i", "shrinks 4 - i", "i = i + 1"))
    assert (error.code, error.label, error.span.line) == ("E2021", "A loop has exactly one measure", 5)
    assert error.notes == ("The first 'shrinks' is at line 4, column 5.",)


@pytest.mark.parametrize("text, label", [  # [8]
    (loop("shrinks 1.5"), "The measure of 'shrinks' must be Int, found Float"),
    (loop('shrinks "x"'), "The measure of 'shrinks' must be Int, found Text"),
    (loop("keeps 1", "shrinks 3 - i"), "The condition of 'keeps' must be Bool, found Int"),
    (loop("shrinks 3 - i", condition="i"), "The condition of 'while' must be Bool, found Int"),
])
def test_clause_and_condition_types(text, label):
    assert label in [error.label for error in diagnostics_of(text)]


def test_a_refined_int_is_a_valid_measure():
    assert check_codes(PERCENT + loop("shrinks Percent(3 - i)", "i = i + 1")) == []


def test_the_clauses_do_not_see_the_body():  # [9]
    errors = diagnostics_of(loop("keeps step >= 0", "shrinks 3 - i", "let step = 1", "i = i + step"))
    assert [(error.code, error.label) for error in errors] == [("E2005", "There is no variable named 'step' here")]


def test_a_variable_of_the_body_is_not_visible_after_the_loop():
    assert check_codes(loop("shrinks 3 - i", "let step = 1", "i = i + step", after="print(step)")) == ["E2005"]


@pytest.mark.parametrize("body, codes", [  # [10]
    ("var i = 0\nwhile i < n\n    shrinks n - i\n{\n    return i\n}", ["E2014"]),
    ("var i = 0\nwhile i < n\n    shrinks n - i\n{\n    i = i + 1\n}\nreturn i", []),
    ("while true\n    shrinks n\n{\n    return n\n}\nreturn 0", []),
    ("while true\n    shrinks n\n{\n    return n\n    print(1)\n}\nreturn 0", ["E2015"]),
])
def test_return_paths(body, codes):
    lines = "\n".join(f"    {line}" for line in body.splitlines())
    assert check_codes(with_main(f"fn f(n: Int) gives Int {{\n{lines}\n}}", "print(f(1))")) == codes


def test_no_shadowing_inside_a_loop():
    assert check_codes(loop("shrinks 3 - i", "var i = 5")) == ["E2006"]


def test_a_loop_and_an_assignment_never_count_as_returning():
    (error,) = diagnostics_of(with_main("fn f(n: Int) gives Int {\n    var x = n\n    x = 1\n}", "print(f(1))"))
    assert error.code == "E2014" and "a loop may not run at all" in error.hint


# Running [11-17]

def test_a_long_loop_needs_no_stack():  # [11]
    assert run_text(with_main(SUM_TO, "print(sum_to(100000))")) == "5000050000\n"


def test_loops_inside_deep_recursion_do_not_count_as_calls():  # [16]
    text = with_main(
        "fn down(n: Int) gives Int {\n"
        "    if n == 0 {\n"
        "        return 0\n"
        "    }\n"
        "    var i = 0\n"
        "    while i < 50\n"
        "        shrinks 50 - i\n"
        "    {\n"
        "        i = i + 1\n"
        "    }\n"
        "    return down(n - 1) + 1\n"
        "}",
        f"print(down({MAX_CALL_DEPTH - 2}))",
    )
    assert run_text(text) == f"{MAX_CALL_DEPTH - 2}\n"


def test_a_variable_of_the_body_lives_for_one_turn():  # [12]
    text = loop("shrinks 3 - i", "let doubled = i * 2", "print(doubled)", "i = i + 1")
    assert run_text(text) == "0\n2\n4\n"


def test_a_loop_whose_condition_is_false_never_runs_its_body_or_measure():
    assert run_text(loop("shrinks 0 - 1", "print(i)", condition="false", after='print("done")')) == "done\n"


def test_return_inside_a_loop_ends_the_function_and_checks_ensures():  # [17]
    text = with_main(
        "fn first_square_above(n: Int) gives Int\n"
        "    promises result * result > n\n"
        "{\n"
        "    var i = 0\n"
        "    while true\n"
        "        shrinks n + 1 - i\n"
        "    {\n"
        "        if i * i > n {\n"
        "            return i\n"
        "        }\n"
        "        i = i + 1\n"
        "    }\n"
        "    return 0\n"
        "}",
        "print(first_square_above(50))",
    )
    assert run_text(text) == "8\n"


def test_nested_loops_restart_the_inner_measure_on_every_entry():  # [15]
    text = in_main(
        "var i = 0\n"
        "var count = 0\n"
        "while i < 3\n"
        "    shrinks 3 - i\n"
        "{\n"
        "    var j = 0\n"
        "    while j < 3\n"
        "        shrinks 3 - j\n"
        "    {\n"
        "        count = count + 1\n"
        "        j = j + 1\n"
        "    }\n"
        "    i = i + 1\n"
        "}\n"
        "print(count)"
    )
    assert run_text(text) == "9\n"


@pytest.mark.parametrize("step, label", [  # [13]
    ("i = i + 0", "The measure was 3 and is still 3"),
    ("i = i - 1", "The measure was 3 and is now 4"),
])
def test_a_measure_that_does_not_decrease(step, label):
    output, error = run_failure(loop("shrinks 3 - i", "print(i)", step))
    assert output == "0\n"
    assert (error.code, error.label, error.span.line) == ("E4006", label, 4)
    assert error.notes == (
        "The measure at line 4: shrinks 3 - i",
        "Before turn 2 of the loop at line 3.",
        "The values: i = 0" if step.endswith("+ 0") else "The values: i = -1",
    )


def test_a_negative_measure():  # [13]
    _, error = run_failure(loop('shrinks 1 - i, "At most one turn"', "i = i + 1", setup="var i = 5", condition="i < 10"))
    assert (error.code, error.label) == ("E4006", "The measure is -4; it must be 0 or more")
    assert error.notes == (
        "The measure at line 4: shrinks 1 - i",
        "Reason: At most one turn",
        "Before turn 1 of the loop at line 3.",
        "The values: i = 5",
    )


def test_a_loop_that_would_never_end_stops():  # [18]
    _, error = run_failure(in_main("while true\n    shrinks 1\n{\n}"))
    assert (error.code, error.label) == ("E4006", "The measure was 1 and is still 1")


@pytest.mark.parametrize("setup, step, when", [  # [14]
    ("var i = 5", "i = i + 1", "Before the first turn of the loop at line 3."),
    ("var i = 0", "i = i + 2", "After turn 2 of the loop at line 3."),
    ("var i = 0", "i = i + 4", "After turn 1 of the loop at line 3."),
])
def test_a_broken_invariant(setup, step, when):
    text = loop('keeps i <= 3, "i never passes the end"', "shrinks 3 - i", step, setup=setup)
    _, error = run_failure(text)
    assert (error.code, error.label, error.span.line) == ("E4005", "This condition is false", 4)
    assert error.notes[0] == "The condition at line 4 is false: keeps i <= 3"
    assert error.notes[1:3] == ("Reason: i never passes the end", when)


def test_the_invariant_is_also_checked_when_the_loop_ends():  # [14]
    # i reaches 4 on the last turn: the condition is then false, but the invariant is checked first.
    _, error = run_failure(loop("keeps i <= 3", "shrinks 4 - i", "i = i + 2", condition="i < 3"))
    assert error.code == "E4005" and error.notes[1] == "After turn 2 of the loop at line 3."


def test_the_values_are_every_visible_variable_and_parameter_in_order():
    text = with_main(
        'fn f(limit: Int, name: Text) gives Int {\n'
        '    let start = 1\n'
        '    var i = start\n'
        '    while i < limit\n'
        '        shrinks limit - i\n'
        '    {\n'
        '        let inside = 1\n'
        '        i = i - inside\n'
        '    }\n'
        '    return i\n'
        '}',
        'print(f(3, "x"))',
    )
    _, error = run_failure(text)
    assert 'The values: limit = 3, name = "x", start = 1, i = 0' in error.notes


def test_a_runtime_error_names_every_loop_innermost_first():  # [16]
    text = in_main(
        "var i = 0\n"
        "while i < 3\n"
        "    shrinks 3 - i\n"
        "{\n"
        "    var j = 0\n"
        "    while j < 3\n"
        "        shrinks 3 - j\n"
        "    {\n"
        "        print(10 / (2 - i - j))\n"
        "        j = j + 1\n"
        "    }\n"
        "    i = i + 1\n"
        "}"
    )
    output, error = run_failure(text)
    assert output == "5\n10\n"
    assert error.code == "E3001"
    assert error.notes == ("In turn 3 of the loop at line 7.", "In turn 1 of the loop at line 3.")


def test_errors_in_the_clauses_say_where_in_the_loop():
    _, error = run_failure(loop("keeps 10 / (2 - i) > 0", "shrinks 3 - i", "i = i + 1"))
    assert error.code == "E3001" and error.notes == ("After turn 2 of the loop at line 3.",)
    _, error = run_failure(loop("shrinks 6 / (1 - i)", "i = i + 1"))
    assert error.code == "E3001" and error.notes == ("Before turn 2 of the loop at line 3.",)


def test_a_broken_refinement_inside_a_loop_keeps_the_output_of_earlier_turns():  # [17]
    text = PERCENT + loop("shrinks 3 - i", "print(Percent(i * 60))", "i = i + 1")
    output, error = run_failure(text)
    assert output == "0\n60\n"
    assert error.code == "E4003" and error.notes[-1] == "In turn 3 of the loop at line 4."


def test_loop_notes_are_limited():
    depth = 9
    lines, indent = [], ""
    for level in range(depth):
        lines += [f"{indent}var v{level} = 0", f"{indent}while v{level} < 1", f"{indent}    shrinks 1 - v{level}",
                  f"{indent}{{"]
        indent += "    "
    lines.append(f"{indent}print(1 / 0)")
    for level in reversed(range(depth)):
        indent = indent[:-4]
        lines += [f"{indent}    v{level} = 1", f"{indent}}}"]
    _, error = run_failure(in_main("\n".join(lines)))
    assert len(error.notes) == 7 and error.notes[-1] == "... and more loops."


# E3007 and the E3004 for Python's own stack are built outside every loop, after MemoryError or
# RecursionError has left them. They still name the loops, with the notes any other diagnostic gets
# at the same point. The failure is raised on purpose exactly where a division by zero (E3001) would be.

def fail_divisions(monkeypatch, failure):
    """A division by zero raises `failure` instead of E3001."""
    original = interpreter.Interpreter._fail

    def fail(self, code, *arguments, **options):
        if code == "E3001":
            raise failure
        return original(self, code, *arguments, **options)

    monkeypatch.setattr(interpreter.Interpreter, "_fail", fail)


NESTED_IN_A_CALL = with_main(
    "fn inner(limit: Int) gives Int {\n"
    "    var j = 0\n"
    "    while j < limit\n"
    "        shrinks limit - j\n"
    "    {\n"
    "        if j == 1 {\n"
    "            print(10 / (j - 1))\n"
    "        }\n"
    "        j = j + 1\n"
    "    }\n"
    "    return j\n"
    "}",
    "var i = 0\nwhile i < 3\n    shrinks 3 - i\n{\n    print(inner(i))\n    i = i + 1\n}",
)


def deep_loops(depth: int) -> str:
    lines, indent = [], ""
    for level in range(depth):
        lines += [f"{indent}var v{level} = 0", f"{indent}while v{level} < 1", f"{indent}    shrinks 1 - v{level}",
                  f"{indent}{{"]
        indent += "    "
    lines.append(f"{indent}print(1 / 0)")
    for level in reversed(range(depth)):
        indent = indent[:-4]
        lines += [f"{indent}    v{level} = 1", f"{indent}}}"]
    return in_main("\n".join(lines))


@pytest.mark.parametrize("failure, code", [(MemoryError, "E3007"), (RecursionError, "E3004")])
@pytest.mark.parametrize("text", [
    NESTED_IN_A_CALL,                                                       # loops in two functions
    loop("keeps 10 / (2 - i) > 0", "shrinks 3 - i", "i = i + 1"),     # in an invariant
    loop("shrinks 6 / (1 - i)", "i = i + 1"),                             # in the measure
    loop("shrinks 3 - i", "i = i + 1", condition="i < 6 / (2 - i)"),      # in the condition
    deep_loops(9),                                                          # more loops than notes
    deep_loops(6),                                                          # exactly as many
], ids=["call", "keeps", "measure", "condition", "nine-loops", "six-loops"])
def test_e3007_and_stack_e3004_name_the_loops_like_any_other_error(monkeypatch, text, failure, code):
    output, expected = run_failure(text)
    assert expected.code == "E3001" and any(" of the loop at line " in note for note in expected.notes)
    fail_divisions(monkeypatch, failure)
    same_output, error = run_failure(text)
    assert error.code == code and same_output == output
    assert error.notes == expected.notes


@pytest.mark.parametrize("failure, code", [(MemoryError, "E3007"), (RecursionError, "E3004")])
def test_a_loop_that_ended_leaves_no_note(monkeypatch, failure, code):
    finished = loop("shrinks 3 - i", "i = i + 1", after="print(1 / (i - 3))")
    returned = with_main(
        "fn first(n: Int) gives Int {\n"
        "    var i = 0\n"
        "    while i < n\n"
        "        shrinks n - i\n"
        "    {\n"
        "        return i\n"
        "    }\n"
        "    return n\n"
        "}",
        "print(first(3))\nprint(1 / first(3))",
    )
    fail_divisions(monkeypatch, failure)
    for text in (finished, returned):
        _, error = run_failure(text)
        assert (error.code, error.notes) == (code, ())


def test_a_real_stack_exhaustion_names_the_loops():
    # No injection: recursion through a nested expression, inside a loop of main and of every call.
    nested = "(" * 50 + "deep(n - 1)" + ")" * 50
    text = with_main(
        "fn deep(n: Int) gives Int {\n    if n == 0 {\n        return 0\n    }\n    var total = 0\n    var i = 0\n"
        f"    while i < 1\n        shrinks 1 - i\n    {{\n        total = {nested} + 1\n        i = i + 1\n    }}\n"
        "    return total\n}",
        f"var k = 0\nwhile k < 1\n    shrinks 1 - k\n{{\n    print(deep({MAX_CALL_DEPTH - 100}))\n    k = k + 1\n}}",
    )
    _, error = run_failure(text)
    assert error.code == "E3004" and "ran out of stack space after" in error.label
    loop_notes = [note for note in error.notes if " of the loop at line " in note]
    assert loop_notes == ["In turn 1 of the loop at line 7."] * 6
    assert error.notes[-1] == "... and more loops."
    # Shallow, the same program works: nothing is left behind by the loops that ended.
    assert run_text(text.replace(f"deep({MAX_CALL_DEPTH - 100})", "deep(20)")) == "20\n"


def test_e4005_and_e4006_stop_the_program_with_exit_code_5(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "loop.nex"
    path.write_text(in_main("while true\n    shrinks 1\n{\n}"), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "nexora", "run", str(path)], capture_output=True, encoding="utf-8")
    assert result.returncode == 5
    assert "contract error[E4006]: Loop measure did not decrease" in result.stderr


def test_run_source_reports_a_contract_violation():
    result = api.run_source(in_main("while true\n    shrinks 1\n{\n}"))
    assert result["status"] == "contract_violation"
    assert [diagnostic["code"] for diagnostic in result["diagnostics"]] == ["E4006"]


def test_nex_test_never_hangs_on_a_loop():  # [18]
    text = (
        "fn forever(n: Int) gives Int\n"
        "    example forever(1) == 1\n"
        "{\n"
        "    while true\n"
        "        shrinks 1\n"
        "    {\n"
        "    }\n"
        "    return n\n"
        "}\n" + SUM_TO.replace("    promises", "    example sum_to(4) == 10\n    promises", 1)
    )
    document = api.test_source(text)
    assert [example["status"] for example in document["examples"]] == ["error", "passed"]
    assert document["examples"][0]["diagnostic"]["code"] == "E4006"
    jsonschema.validate(document, SCHEMAS["nexora-test.schema.json"])


# Tools [19]

def test_inspect_has_the_new_nodes_and_follows_its_schema():
    document = tooling.inspect_source(with_main(SUM_TO, "print(sum_to(3))"))
    jsonschema.validate(document, SCHEMAS["nexora-inspect.schema.json"])
    statements = document["program"]["functions"][0]["body"]["statements"]
    assert [statement["kind"] for statement in statements] == ["Var", "Var", "While", "Return"]
    loop_node = statements[2]
    assert list(loop_node) == ["kind", "span", "condition", "clauses", "body"]
    assert [(clause["kind"], clause["clause"]) for clause in loop_node["clauses"]] == [
        ("LoopClause", "keeps"), ("LoopClause", "shrinks"),
    ]
    assert loop_node["clauses"][1]["condition"]["type"] == "Int"


def _valid_in(schema: dict, kind: str, node: dict) -> bool:
    """Whether `node` is a valid `kind` for the definitions of an old schema."""
    try:
        jsonschema.validate(node, {"$defs": schema["$defs"], "$ref": f"#/$defs/{kind}"})
    except jsonschema.ValidationError:
        return False
    return True


def _schema_of_0_4_0() -> dict:
    path = Path(__file__).parent / "golden" / "schemas" / "nexora-inspect-0.4.0.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_program_without_loops_keeps_the_body_of_0_4_0_and_only_its_function_changed():
    # Decision 0019, 8.8: `nexora.inspect/3` changes the document and `Function` (`header`
    # replaces `contracts` and `examples`, `return_type` can be null). Everything below a
    # function is unchanged, so a body without loops is still a Block of 0.4.0.
    old = _schema_of_0_4_0()
    document = tooling.inspect_source(in_main("let x = 1\nprint(x)"))
    (main,) = document["program"]["functions"]
    assert _valid_in(old, "Block", main["body"])
    assert not _valid_in(old, "Function", main)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, old)


def test_a_consumer_of_0_4_0_notices_a_var_instead_of_reading_it_as_a_let():
    # Decision 0010, section 11: a new kind of node, not a new field that an old tool would ignore.
    # Checked on the body, which 0.12 did not change, so the Var is what the old schema rejects.
    old = _schema_of_0_4_0()
    (main,) = tooling.inspect_source(in_main("var x = 1\nprint(x)"))["program"]["functions"]
    assert not _valid_in(old, "Block", main["body"])
    assert _valid_in(old, "ExprStatement", main["body"]["statements"][1])


def test_symbols_say_which_variables_change_and_where():
    document = tooling.get_symbols(with_main(SUM_TO, "print(sum_to(3))"))
    jsonschema.validate(document, SCHEMAS["nexora-symbols.schema.json"])
    entries = {entry["name"]: entry for entry in document["symbols"]}
    assert (entries["total"]["mutable"], entries["n"]["mutable"], entries["sum_to"]["mutable"]) == (True, False, False)
    assert [span["line"] for span in entries["i"]["assignments"]] == [11]
    assert all(span in entries["i"]["references"] for span in entries["i"]["assignments"])
    assert entries["n"]["assignments"] == []


def test_context_lists_the_loops_and_their_requirements():
    document = tooling.get_context(with_main(SUM_TO, "print(sum_to(3))"))
    jsonschema.validate(document, SCHEMAS["nexora-context.schema.json"])
    assert {"mutable_variables", "loops", "loop_invariants"} <= set(document["features"])
    assert any("stops with E4006" in note for note in document["notes"])
    function = document["functions"][0]
    assert [(v["name"], v["mutable"]) for v in function["variables"]] == [("total", True), ("i", True)]
    assert function["loops"] == [{
        "line": 7,
        "kind": "while",
        "condition": "i < n",
        "invariants": [{"condition": "total == i * (i + 1) / 2",
                        "message": "total is the sum of the numbers already added", "line": 8, "name": None}],
        "measure": {"condition": "n - i", "message": "Each turn moves i one step closer to n", "line": 9,
                    "name": None},
    }]


def test_context_text_shows_the_loops():
    from nexora.tooling import render_context

    text = render_context(tooling.get_context(with_main(SUM_TO, "print(sum_to(3))")))
    assert "variables: var total: Int, var i: Int" in text
    assert "loop at line 7: while i < n" in text
    assert "keeps total == i * (i + 1) / 2" in text
    assert "shrinks n - i" in text


def test_context_of_a_loop_without_a_measure():
    document = tooling.get_context(loop("i = i + 1"))
    assert document["functions"][0]["loops"][0]["measure"] is None
    jsonschema.validate(document, SCHEMAS["nexora-context.schema.json"])

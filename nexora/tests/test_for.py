"""I5: `for x in xs { ... }` over an immutable `List[T]` (decision 0012).

The iterator is declared by the loop, is immutable and has the element type; the body opens a new
scope on every turn; the loop accepts `invariant` but not `decreases`; a `return` leaves the
function. Invariants are checked before every turn and once after the last one, exactly as in a
`while`.
"""

from __future__ import annotations

import jsonschema
import pytest

from nexora import ast_nodes as ast
from nexora import schemas, tooling

from helpers import check_codes, diagnostics_of, in_main, parse_text, run_failure, run_text, with_main

SCHEMAS = schemas.all_schemas()

COUNT = """
fn count(xs: List[Int]) -> Int {
    var total = 0
    for x in xs {
        invariant total >= 0, "The total is never negative"
        total = total + x
    }
    return total
}
"""


def test_a_for_is_parsed_with_its_iterator_iterable_clauses_and_body():
    program, diagnostics = parse_text(
        "fn main() -> Void {\n"
        "    for value in numbers {\n"
        "        invariant value >= 0\n"
        "        print(value)\n"
        "    }\n"
        "}\n"
    )
    assert diagnostics == []
    loop = program.functions[0].body.statements[0]

    assert isinstance(loop, ast.For)
    assert (loop.name, loop.name_span.line, loop.name_span.column) == ("value", 2, 9)
    assert isinstance(loop.iterable, ast.Name) and loop.iterable.name == "numbers"
    assert [(clause.clause, clause.message) for clause in loop.clauses] == [("invariant", None)]
    assert len(loop.body.statements) == 1
    assert (loop.span.line, loop.span.column) == (2, 5)


def test_a_for_walks_the_list_in_order():
    assert run_text(with_main(COUNT, "print(count([1, 2, 3, 4]))")) == "10\n"


def test_a_for_over_an_empty_list_runs_no_turn():
    text = with_main(COUNT, "print(count([]))")
    assert run_text(text) == "0\n"


def test_the_iterable_is_evaluated_once():
    text = with_main(
        "fn make() -> List[Int] {\n"
        '    print("once")\n'
        "    return [1, 2, 3]\n"
        "}\n",
        "for x in make() {\n    print(x)\n}",
    )
    assert run_text(text) == "once\n1\n2\n3\n"


@pytest.mark.parametrize("iterable", ["3", '"abc"', "true", "1.5"])
def test_the_iterable_must_be_a_list(iterable):
    (error,) = diagnostics_of(in_main(f"for x in {iterable} {{\n    print(x)\n}}"))
    assert error.code == "E2011"
    assert error.label.startswith("The value a 'for' walks over must be a List, found ")


def test_a_non_list_iterable_reports_once_and_does_not_cascade():
    assert check_codes(in_main("for x in 3 {\n    print(x)\n}")) == ["E2011"]


def test_the_iterator_has_the_element_type():
    text = with_main(
        "fn lengths(xs: List[Text]) -> Void {\n"
        "    for x in xs {\n"
        "        print(Text.length(x))\n"
        "    }\n"
        "}\n",
        'lengths(["ab", "c"])',
    )
    assert run_text(text) == "2\n1\n"


def test_the_iterator_is_not_visible_after_the_loop():
    (error,) = diagnostics_of(in_main("for x in [1] {\n    print(x)\n}\nprint(x)"))
    assert error.code == "E2005"


def test_a_name_declared_in_the_body_is_not_visible_in_the_next_turn():
    (error,) = diagnostics_of(in_main("for x in [1, 2] {\n    let previous = x\n}\nprint(previous)"))
    assert error.code == "E2005"


def test_the_iterator_cannot_shadow_a_visible_name():
    (error,) = diagnostics_of(in_main("let x = 1\nfor x in [2] {\n    print(x)\n}"))
    assert error.code == "E2006"


def test_the_iterator_is_immutable_with_its_own_message():
    (error,) = diagnostics_of(in_main("for x in [1] {\n    x = 2\n}"))
    assert (error.code, error.label) == (
        "E2007",
        "'x' is the iterator of a 'for' loop and cannot be given a new value",
    )
    assert "declare a 'var'" in error.hint


def test_a_return_inside_the_body_leaves_the_function():
    text = with_main(
        "fn first(xs: List[Int]) -> Int {\n"
        "    for x in xs {\n"
        "        return x\n"
        "    }\n"
        "    return 0\n"
        "}\n",
        "print(first([7, 8]))\nprint(first([]))",
    )
    assert run_text(text) == "7\n0\n"


def test_a_for_can_be_nested():
    text = in_main(
        "for x in [1, 2] {\n"
        "    for y in [3, 4] {\n"
        "        print(x * 10 + y)\n"
        "    }\n"
        "}"
    )
    assert run_text(text) == "13\n14\n23\n24\n"


def test_the_body_updates_a_variable_of_the_outer_scope():
    text = in_main(
        "var total = 0\n"
        "for x in [1, 2, 3] {\n"
        "    total = total + x\n"
        "}\n"
        "print(total)"
    )
    assert run_text(text) == "6\n"


def test_an_invariant_is_checked_before_the_first_turn_even_for_an_empty_list():
    text = with_main(
        "fn f(xs: List[Int]) -> Void {\n"
        "    var i = 1\n"
        "    for x in xs {\n"
        '        invariant i == 0, "i starts at zero"\n'
        "    }\n"
        "}\n",
        "f([])",
    )
    _, error = run_failure(text)
    assert (error.code, error.label) == ("E4005", "This condition is false")
    assert error.notes[1] == "Reason: i starts at zero"
    assert error.notes[2] == "Before the first turn of the loop at line 3."


def test_an_invariant_is_checked_once_after_the_last_turn():
    text = in_main(
        "var i = 0\n"
        "for x in [1, 2] {\n"
        "    invariant i < 2\n"
        "    i = i + 1\n"
        "}"
    )
    _, error = run_failure(text)
    assert error.code == "E4005"
    assert error.notes[1] == "After turn 2 of the loop at line 3."


def test_invariants_do_not_see_the_iterator():
    codes = check_codes(in_main("for x in [1] {\n    invariant x > 0\n}"))
    assert codes == ["E2005"]


def test_an_invariant_must_be_bool():
    (error,) = diagnostics_of(in_main("var n = 1\nfor x in [1] {\n    invariant n\n}"))
    assert (error.code, error.label) == (
        "E2011",
        "The condition of 'invariant' must be Bool, found Int",
    )


def test_decreases_is_rejected_with_e2022():
    (error,) = diagnostics_of(in_main("for x in [1] {\n    decreases 1\n}"))
    assert (error.code, error.label) == ("E2022", "'decreases' has no meaning in a 'for' loop")
    assert "remove the 'decreases' clause" in error.hint


@pytest.mark.parametrize("word", ["break", "continue"])
def test_break_and_continue_are_still_reserved(word):
    (error,) = diagnostics_of(in_main(f"for x in [1] {{\n    {word}\n}}"))
    assert error.code == "E1103"


@pytest.mark.parametrize("text, column", [
    ("for {\n}", 9),
    ("for x {\n}", 11),
    ("for x in {\n}", 14),
])
def test_a_malformed_for_is_e1101(text, column):
    (error,) = diagnostics_of(in_main(text))
    assert (error.code, error.span.line, error.span.column) == ("E1101", 2, column)


@pytest.mark.parametrize("word", ["for", "in"])
def test_for_and_in_are_keywords_not_reserved_words(word):
    (error,) = diagnostics_of(in_main(f"let {word} = 1"))
    assert (error.code, error.label) == ("E1101", f"Expected a variable name after 'let', but '{word}' is a keyword")


def test_the_context_lists_a_for_loop():
    document = tooling.get_context(with_main(COUNT, "print(count([1, 2, 3]))"))
    jsonschema.validate(document, SCHEMAS["nexora-context.schema.json"])
    assert {"loops", "loop_invariants"} <= set(document["features"])
    assert document["functions"][0]["loops"] == [{
        "line": 3,
        "kind": "for",
        "condition": "x in xs",
        "invariants": [{"condition": "total >= 0",
                        "message": "The total is never negative", "line": 4}],
        "measure": None,
    }]


def test_the_context_text_shows_a_for_loop():
    text = tooling.render_context(tooling.get_context(with_main(COUNT, "print(count([1, 2, 3]))")))
    assert "loop at line 3: for x in xs" in text
    assert "invariant total >= 0" in text


def test_the_symbols_document_marks_the_iterator_immutable():
    document = tooling.get_symbols(in_main("let xs = [1]\nfor x in xs {\n    print(x)\n}"))
    jsonschema.validate(document, SCHEMAS["nexora-symbols.schema.json"])
    entries = {entry["name"]: entry for entry in document["symbols"]}

    assert (entries["x"]["category"], entries["x"]["type"], entries["x"]["mutable"]) == ("variable", "Int", False)
    assert entries["x"]["scope"] is not None
    assert entries["x"]["assignments"] == []
    assert entries["xs"]["references"]


def test_inspect_writes_the_for_node():
    document = tooling.inspect_source(in_main("for x in [1] {\n    print(x)\n}"))
    jsonschema.validate(document, SCHEMAS["nexora-inspect.schema.json"])
    loop = document["program"]["functions"][0]["body"]["statements"][0]

    assert loop["kind"] == "For"
    assert loop["name"] == "x"
    assert loop["name_span"]["line"] == 2
    assert loop["iterable"]["kind"] == "ListLiteral"
    assert loop["clauses"] == []
    assert loop["body"]["kind"] == "Block"

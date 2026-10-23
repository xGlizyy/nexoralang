"""The `example` clause, as the static analysis sees it (decision 0008, sections 1 and 2).

Nothing here evaluates an example: these tests are about syntax, types, names, the own-call rule
and the call graph. Evaluation is in test_nex_test.py.
"""

import pytest

from helpers import diagnostics_of, parse_text
from nexora.checker import own_calls
from nexora.diagnostics import Source
from nexora.pipeline import analyze


def double(*clauses: str, body: str = "return n * 2") -> str:
    """A function `double(n: Int) -> Int` with the given clauses, and nothing else (no main)."""
    lines = "\n".join(f"    {line}" for line in (*clauses, body))
    return f"fn double(n: Int) -> Int {{\n{lines}\n}}\n"


def test_codes(text: str) -> list[str]:
    """Diagnostics of the analysis `nex test` runs, which does not require main."""
    return [diagnostic.code for diagnostic in analyze(Source("test.nex", text), require_main=False).diagnostics]


test_codes.__test__ = False   # a helper, not a test


# Syntax

def test_example_is_a_keyword_and_no_longer_reserved():
    from nexora.tokens import KEYWORDS, RESERVED_WORDS

    assert "example" in KEYWORDS and "example" not in RESERVED_WORDS


def test_examples_are_parsed_into_their_own_nodes_in_any_order_with_the_contracts():
    program, errors = parse_text(double(
        "requires n >= 0", 'example double(2) == 4, "Two doubled"', "ensures result >= n", "example double(0) == 0",
    ))
    assert errors == []
    function = program.functions[0]
    assert [contract.clause for contract in function.contracts] == ["requires", "ensures"]
    assert [(example.message, example.span.line) for example in function.examples] == [("Two doubled", 3), (None, 5)]
    assert type(function.examples[0].condition).__name__ == "Binary"


def test_a_function_without_examples_has_an_empty_tuple():
    program, _ = parse_text(double())
    assert program.functions[0].examples == ()


def test_an_example_after_a_statement_is_misplaced():
    (error,) = diagnostics_of(double("let x = 1", "example double(1) == 2", body="return x"))
    assert (error.code, error.label) == (
        "E1106", "'example' must come at the start of a function body, before any other statement",
    )


@pytest.mark.parametrize("clause, label", [
    ('example double(2) == 4, ""', "The explanation of 'example' is empty"),
    ('example double(2) == 4, "   "', "The explanation of 'example' is empty"),
    ('example double(2) == 4, "a\\nb"', "An explanation is a single line: it cannot contain '\\n'"),
    ("example double(2) == 4, 4", "Expected a text after ',' explaining the rule of 'example', found the number 4"),
    ("example", "Expected a condition after 'example', found the end of line"),
])
def test_malformed_examples_are_syntax_errors(clause, label):
    (error,) = diagnostics_of(double(clause))
    assert (error.code, error.label) == ("E1101", label)


# Types and names

def test_a_valid_example_passes_the_analysis_without_main():
    assert test_codes(double("example double(2) == 4", 'example double(3) == 6, "Three doubled"')) == []


def test_without_main_check_still_reports_e2001():
    # Decision 0008, closed decision 1: `nex check` keeps requiring main.
    assert [d.code for d in diagnostics_of(double("example double(2) == 4"))] == ["E2001"]


def test_the_expression_must_be_bool():
    errors = analyze(Source("t.nex", double("example double(2)")), require_main=False).diagnostics
    assert [(error.code, error.label) for error in errors] == [
        ("E2011", "The condition of 'example' must be Bool, found Int"),
    ]


def test_a_void_function_cannot_have_a_valid_example():
    text = 'fn say(n: Int) -> Void {\n    example say(1)\n    print(n)\n}\n'
    assert test_codes(text) == ["E2011"]


@pytest.mark.parametrize("clause", ["example double(n) == 4", "example double(2) == n"])
def test_an_example_does_not_see_the_parameters(clause):
    (error,) = analyze(Source("t.nex", double(clause)), require_main=False).diagnostics
    assert (error.code, error.label) == ("E2005", "There is no variable named 'n' here")
    assert error.hint == "An example has no parameters: write its inputs as values, for example: double(2)"


def test_an_example_does_not_see_result():
    errors = analyze(Source("t.nex", double("example double(2) == result")), require_main=False).diagnostics
    assert [(error.code, error.label) for error in errors] == [("E2005", "There is no variable named 'result' here")]
    assert errors[0].hint.startswith("An example has no parameters")


def test_an_example_can_use_other_functions_builtins_and_refined_checks():
    text = (
        'type Small = Int where value < 100\n\n'
        "fn half(n: Int) -> Int {\n    return n / 2\n}\n\n"
        + double("example half(double(5)) == 5", "example to_float(double(1)) > 1.5",
                 "example double(Small(3)) == 6")
    )
    assert test_codes(text) == []


def test_constants_in_examples_are_checked_against_refined_types():
    text = 'type Percent = Int where value >= 0 and value <= 100\n\n' \
           "fn twice(p: Percent) -> Int {\n    example twice(150) == 300\n    return p * 2\n}\n"
    assert test_codes(text) == ["E2017"]


# The own call (decision 0008, 1.4)

@pytest.mark.parametrize("clause, count", [
    ("example double(2) == 4", 1),
    ("example double(double(2)) == 8", 2),
    ("example double(1) + double(2) == 6", 2),
    ("example to_float(double(2)) > 3.5", 1),
    ("example half(double(2)) == 2", 1),
    ("example (double(2)) == 4", 1),
    ("example not (double(2) != 4)", 1),
])
def test_calls_anywhere_in_the_expression_count(clause, count):
    text = "fn half(n: Int) -> Int {\n    return n / 2\n}\n\n" + double(clause)
    assert test_codes(text) == []
    program, _ = parse_text(text)
    assert len(own_calls(program.functions[1].examples[0], "double")) == count


def test_own_calls_are_listed_in_the_order_they_start_in_the_text():
    program, _ = parse_text(double("example double(double(1)) + double(3) == 10"))
    calls = own_calls(program.functions[0].examples[0], "double")
    assert [(call.span.column, call.span.end_column) for call in calls] == [(13, 30), (20, 29), (33, 42)]


def test_no_own_call_is_e2020_on_the_whole_expression():
    errors = analyze(Source("t.nex", double("example 2 + 2 == 4")), require_main=False).diagnostics
    assert [(e.code, e.category, e.label) for e in errors] == [
        ("E2020", "semantic", "This example of 'double' never calls 'double'"),
    ]
    assert errors[0].hint == "Write the call with its inputs, for example: example double(2) == 4"
    span = errors[0].span
    assert (span.line, span.column, span.end_column) == (2, 13, 23)


def test_a_call_made_only_inside_another_function_does_not_count():
    text = "fn quad(n: Int) -> Int {\n    return double(double(n))\n}\n\n" + double("example quad(1) == 4")
    assert test_codes(text) == ["E2020"]


def test_not_bool_and_no_own_call_are_two_errors():
    assert test_codes(double("example 2 + 2")) == ["E2011", "E2020"]


@pytest.mark.parametrize("clause, code", [
    ("example double(1, 2) == 4", "E2009"),
    ("example double() == 0", "E2009"),
    ('example double("two") == 4', "E2011"),
])
def test_an_own_call_with_wrong_arguments_is_its_own_error_not_e2020(clause, code):
    assert test_codes(double(clause)) == [code]


# Analysing is not running (decision 0008, section 2)

def test_the_analysis_never_evaluates_an_example():
    # Evaluating any of these would fail or print; the analysis accepts them silently.
    text = (
        "fn boom(n: Int) -> Int {\n    print(\"evaluated!\")\n    return n / 0\n}\n\n"
        + double("example double(boom(1)) == 0", "example double(2) == 5")
    )
    assert test_codes(text) == []


def test_calls_in_examples_are_not_edges_of_the_call_graph():
    text = "fn g(n: Int) -> Int {\n    return n + 1\n}\n\n" + double("example double(g(1)) == 4 and double(2) == 4")
    analysis = analyze(Source("t.nex", text), require_main=False)
    assert analysis.ok
    assert ("double", "double") not in analysis.facts.calls
    assert ("double", "g") not in analysis.facts.calls


def test_calls_in_examples_are_references():
    text = "fn g(n: Int) -> Int {\n    return n + 1\n}\n\n" + double("example double(g(1)) == 4")
    symbols = {symbol.name: symbol for symbol in analyze(Source("t.nex", text), require_main=False).facts.symbols}
    assert [(span.line, span.column) for span in symbols["g"].references] == [(6, 20)]
    assert [(span.line, span.column) for span in symbols["double"].references] == [(6, 13)]


def test_main_is_still_checked_when_present():
    text = double("example double(2) == 4") + "\nfn main() -> Int {\n    return 1\n}\n"
    assert test_codes(text) == ["E2004"]


# The analysis tools (decision 0008, section 8)

TWO_EXAMPLES = (
    "fn g(n: Int) -> Int {\n    return n + 1\n}\n\n"
    + double('example double(2) == 4, "Two doubled"', "example double(g(1)) == 4")
    + "\nfn main() -> Void {\n    print(double(1))\n}\n"
)


def test_inspect_adds_example_nodes_at_the_end_of_function():
    from nexora import tooling

    document = tooling.inspect_source(TWO_EXAMPLES)
    assert document["schema"] == "nexora.inspect/2" and document["ok"]
    function = document["program"]["functions"][1]
    assert list(function)[-2:] == ["examples", "public"]
    first, second = function["examples"]
    assert list(first) == ["kind", "span", "condition", "message"]
    assert (first["kind"], first["message"], second["message"]) == ("Example", "Two doubled", None)
    assert first["condition"]["type"] == "Bool"
    assert first["condition"]["left"]["callee"] == "double" and first["condition"]["left"]["type"] == "Int"


def test_inspect_still_validates_against_the_schema_of_0_3_1():
    # Case 38: a consumer written for 0.3.1 reads the new documents, because the schema only gains
    # a field at the end of Function and a node kind, and schemas never forbid extra fields.
    import json
    from pathlib import Path

    import jsonschema

    from nexora import tooling

    old = json.loads((Path(__file__).parent / "golden" / "schemas" / "nexora-inspect-0.3.1.schema.json")
                     .read_text(encoding="utf-8"))
    document = tooling.inspect_source(TWO_EXAMPLES)
    jsonschema.validate(document, old)
    old_order = old["$defs"]["Function"]["required"]
    function = document["program"]["functions"][1]
    assert [name for name in function if name in old_order] == old_order


def test_context_lists_examples_last_and_keeps_the_call_graph():
    from nexora import tooling

    document = tooling.get_context(TWO_EXAMPLES)
    function = next(f for f in document["functions"] if f["name"] == "double")
    # Each field was added at the end: the examples in 0.4.0, the loops in 0.5.0 (decision 0010),
    # the file in 0.11.0 (decision 0018).
    assert list(function)[-3:] == ["examples", "loops", "file"]
    assert function["examples"] == [
        {"condition": "double(2) == 4", "message": "Two doubled", "line": 6},
        {"condition": "double(g(1)) == 4", "message": None, "line": 7},
    ]
    # Case 32: the examples call double and g, but double does neither when it runs.
    assert (function["calls"], function["recursive"]) == ([], False)
    g = next(f for f in document["functions"] if f["name"] == "g")
    assert g["called_by"] == []
    assert "examples" in document["features"]


def test_context_text_shows_the_examples():
    from nexora import tooling

    text = tooling.render_context(tooling.get_context(TWO_EXAMPLES))
    assert "      example double(2) == 4\n          reason: Two doubled\n      example double(g(1)) == 4" in text


def test_a_program_without_examples_has_an_empty_list_and_no_feature():
    from nexora import tooling

    document = tooling.get_context(double() + "\nfn main() -> Void {\n    print(double(1))\n}\n")
    assert all(function["examples"] == [] for function in document["functions"])
    assert "examples" not in document["features"]


def test_symbols_count_calls_in_examples_as_references():
    from nexora import tooling

    entries = {entry["name"]: entry for entry in tooling.get_symbols(TWO_EXAMPLES)["symbols"]}
    lines = {(reference["line"], reference["column"]) for reference in entries["g"]["references"]}
    assert lines == {(7, 20)}


def test_no_analysis_tool_evaluates_examples():
    # Case 33: evaluating this example would print and divide by zero.
    from nexora import tooling

    text = "fn boom(n: Int) -> Int {\n    print(\"evaluated!\")\n    return n / 0\n}\n\n" \
           + double("example double(boom(1)) == 0") + "\nfn main() -> Void {\n    print(1)\n}\n"
    for document in (tooling.check_source(text), tooling.inspect_source(text), tooling.get_context(text),
                     tooling.get_symbols(text)):
        assert document["ok"], document["schema"]

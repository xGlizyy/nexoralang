"""The edits of `nex migrate` (decision 0019, 8.5) and the refusals of 8.6.

Each case M1-M12 of the decision is written here with its original and its migrated text, as
the decision gives them. The edits never re-render the program: every character outside them
must be kept (G2).
"""

import pytest

from nexora import migrate
from nexora.legacy011.diagnostics import Source
from nexora.legacy011.pipeline import analyze


def plan(text: str) -> migrate.FilePlan:
    analysis = analyze(Source("program.nex", text), require_main=False)
    assert analysis.ok, [d.code for d in analysis.diagnostics]   # G1: only valid 0.11 programs
    return migrate.plan(text, analysis.tokens, analysis.program)


def migrated(text: str) -> tuple[str, list[str]]:
    result = plan(text)
    assert result.refusals == (), result.refusals
    output = migrate.apply(text, result.edits)
    assert migrate.kept_outside(text, result.edits, output)
    return output, [edit.kind for edit in result.edits]


def in_function(loop: str) -> str:
    return "fn w(n: Int) -> Int {\n    var i = 0\n" + loop + "    return i\n}\n"


# The cases of 8.5.5, with the edits each one names.
CASES = {
    "M1": (
        "fn f(x: Int) -> Int { // entry\n    requires x > 0\n    return x\n}\n",
        "fn f(x: Int) gives Int // entry\n    needs x > 0\n{\n    return x\n}\n",
        ["E1", "E5a", "E3", "E6"],
    ),
    "M2": (
        "fn g(x: Int) -> Int {\n    // input\n    requires x > 0\n\n    ensures result > 0 // positive\n"
        "    // body\n    return x\n}\n",
        "fn g(x: Int) gives Int\n    // input\n    needs x > 0\n\n    promises result > 0 // positive\n{\n"
        "    // body\n    return x\n}\n",
        ["E1", "E5a", "E3", "E3", "E6"],
    ),
    "M3": (
        "fn h(x: Int) -> Int\r\n{\r\n    requires x > 0\r\n    return x\r\n}\r\n",
        "fn h(x: Int) gives Int\r\n    needs x > 0\r\n{\r\n    return x\r\n}\r\n",
        ["E1", "E5b", "E3", "E6"],
    ),
    "M4": (
        "fn k(x: Int) -> Int\n    {   // checks\n    requires x > 0\n    return x\n}\n",
        "fn k(x: Int) gives Int\n    // checks\n    needs x > 0\n{\n    return x\n}\n",
        ["E1", "E5c", "E3", "E6"],
    ),
    "M5": (
        "fn log(x: Int) -> Void {\n    requires x > 0\n    print(x)\n}\n",
        "fn log(x: Int)\n    needs x > 0\n{\n    print(x)\n}\n",
        ["E2", "E5a", "E3", "E6"],
    ),
    "M6": (
        "fn one() -> Int // unit\n{\n    return 1\n}\n",
        "fn one() gives Int { // unit\n    return 1\n}\n",
        ["E1", "E7", "E7"],
    ),
    "M7": (
        "fn one() -> Int\n// doc\n{\n    return 1\n}\n",
        "fn one() gives Int {\n// doc\n    return 1\n}\n",
        ["E1", "E7", "E7"],
    ),
    "M8": (
        in_function("    while i < n {\n        decreases n - i\n        i = i + 1\n    }\n"),
        "fn w(n: Int) gives Int {\n    var i = 0\n    while i < n\n        shrinks n - i\n    {\n        i = i + 1\n    }\n"
        "    return i\n}\n",
        ["E1", "E5a", "E3", "E6"],
    ),
    "M9": (
        "fn h(x: Int) -> Int {\r    requires x > 0\r    return x\r}\r",
        "fn h(x: Int) gives Int\r    needs x > 0\r{\r    return x\r}\r",
        ["E1", "E5a", "E3", "E6"],
    ),
    "M11": (
        "fn h(x: Int) -> Int {\n    requires x > 0\n    return x\n}",
        "fn h(x: Int) gives Int\n    needs x > 0\n{\n    return x\n}",
        ["E1", "E5a", "E3", "E6"],
    ),
    "M12": (
        "fn h(x: Int) -> Int {\n\trequires x > 0\n\treturn x\n}\n",
        "fn h(x: Int) gives Int\n\tneeds x > 0\n{\n\treturn x\n}\n",
        ["E1", "E5a", "E3", "E6"],
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_each_case_of_the_decision_gives_its_migrated_text(name):
    original, expected, kinds = CASES[name]
    output, found = migrated(original)
    assert output == expected
    assert found == kinds


def test_the_inserted_brace_copies_the_indentation_of_the_line_of_the_signature():
    # M12, with the function indented by a tab, and a loop indented by tabs inside it.
    original = "\tfn h(x: Int) -> Int {\n\t\trequires x > 0\n\t\treturn x\n\t}\n"
    output, _ = migrated(original)
    assert output == "\tfn h(x: Int) gives Int\n\t\tneeds x > 0\n\t{\n\t\treturn x\n\t}\n"


def test_a_public_function_takes_the_indentation_of_the_line_of_pub():
    output, _ = migrated("pub fn h(x: Int) -> Int {\n    requires x > 0\n    return x\n}\n")
    assert output == "pub fn h(x: Int) gives Int\n    needs x > 0\n{\n    return x\n}\n"


def test_examples_stay_where_they_are_among_the_clauses():
    # The interleaving is kept by the text (8.4.1): no line of the header moves.
    original = "fn d(x: Int) -> Int {\n    requires x > 0\n    example d(1) == 2\n    ensures result > x\n    return x * 2\n}\n"
    output, _ = migrated(original)
    assert output == ("fn d(x: Int) gives Int\n    needs x > 0\n    example d(1) == 2\n    promises result > x\n{\n"
                      "    return x * 2\n}\n")


def test_a_condition_across_lines_keeps_its_lines():
    original = "fn g(x: Int) -> Int {\n    requires (x > 0 and\n        x < 10)\n    return x\n}\n"
    output, _ = migrated(original)
    assert output == "fn g(x: Int) gives Int\n    needs (x > 0 and\n        x < 10)\n{\n    return x\n}\n"


def test_unwrap_and_unwrap_or_become_value_and_value_or():
    original = ("fn f(x: Option[Int], y: Result[Int, Text]) -> Int {\n"
                "    return Option.unwrap_or(x, 0) + Option.unwrap(x) + Result.unwrap_or(y, 0) + Result.unwrap(y)\n}\n")
    output, kinds = migrated(original)
    assert output == ("fn f(x: Option[Int], y: Result[Int, Text]) gives Int {\n"
                      "    return Option.value_or(x, 0) + Option.value(x) + Result.value_or(y, 0) + Result.value(y)\n}\n")
    assert kinds == ["E1", "E4", "E4", "E4", "E4"]


def test_the_other_functions_of_option_and_result_are_not_renamed():
    original = ("fn f(x: Option[Int], y: Result[Int, Text]) -> Bool {\n"
                "    return Option.is_some(x) and Result.is_ok(y) and Result.error(y) == \"\"\n}\n")
    output, kinds = migrated(original)
    assert output == original.replace("-> Bool", "gives Bool")
    assert kinds == ["E1"]


def test_a_function_without_clauses_only_changes_its_arrow():
    output, kinds = migrated("fn main() -> Void {\n    print(1)\n}\n")
    assert output == "fn main() {\n    print(1)\n}\n"
    assert kinds == ["E2"]


# 8.6: the refusals. Nothing is planned for a file with a refusal.

REFUSALS = {
    "a clause on the line of the brace": (
        "fn f(x: Int) -> Int { requires x > 0\n    return x\n}\n", (1, 23), "Put 'requires' on its own line"),
    "a clause and the closing brace on the line of the opening one": (
        "fn g(x: Int) -> Void { requires x > 0 }\n", (1, 24), "Put 'requires' on its own line"),
    "the last clause followed by the closing brace": (
        "fn g(x: Int) -> Void {\n    requires x > 0 }\n", (2, 5), "Put 'requires' on its own line"),
    "a comment after a brace alone, without clauses": (
        "fn one() -> Int\n{ // note\n    return 1\n}\n", (2, 1), "Move this comment"),
    "a statement after a brace alone, without clauses": (
        "fn one() -> Int\n{ return 1\n}\n", (2, 1), "Put the first statement on its own line"),
    "a name that becomes a keyword": (
        "fn f() -> Int {\n    let needs = 3\n    return needs\n}\n", (2, 9), "'needs' is a keyword from 0.12"),
    "a field that becomes a keyword": (
        "type R = { trust: Int }\n", (1, 12), "'trust' is a keyword from 0.12"),
}


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_a_case_that_needs_a_choice_is_refused(name):
    text, position, message = REFUSALS[name]
    result = plan(text)
    assert result.edits == ()
    assert (result.refusals[0].line, result.refusals[0].column) == position
    assert result.refusals[0].message.startswith(message)


def test_a_loop_without_clauses_is_left_as_it_is():
    original = "fn s(xs: List[Int]) -> Int {\n    var t = 0\n    for x in xs {\n        t = t + x\n    }\n    return t\n}\n"
    output, kinds = migrated(original)
    assert output == original.replace("-> Int", "gives Int")
    assert kinds == ["E1"]


def _plan_with_modules(tmp_path, files: dict[str, str]) -> migrate.FilePlan:
    """A program and the modules it imports, read from disk as `nex` reads them."""
    from nexora import cli
    from nexora.legacy011.diagnostics import Diagnostic

    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    entry = tmp_path / "main.nex"
    source = Source(str(entry), files["main.nex"])
    analysis = analyze(source, require_main=False, read=cli._module_reader(source, Source, Diagnostic))
    assert analysis.ok, [d.code for d in analysis.diagnostics]   # all of them pass the 0.11 check
    return migrate.plan(files["main.nex"], analysis.tokens, analysis.program)


def test_a_module_named_like_a_new_keyword_is_refused_even_if_it_is_never_used(tmp_path):
    result = _plan_with_modules(tmp_path, {
        "main.nex": 'import "m/needs.nex"\nfn main() -> Void {\n    print(1)\n}\n',
        "m/needs.nex": "type T = Int where value > 0\n",
    })
    assert result.edits == ()
    assert [(r.line, r.column, r.message) for r in result.refusals] == [
        (1, 8, "'needs' is a keyword from 0.12: rename the file 'needs.nex'")]


def test_a_module_named_like_option_is_refused_because_e4_could_not_tell_the_calls_apart(tmp_path):
    result = _plan_with_modules(tmp_path, {
        "main.nex": 'import "m/Option.nex"\nfn main() -> Void {\n    print(Option.unwrap_or(Some(1), 0))\n}\n',
        "m/Option.nex": "type T = Int where value > 0\n",
    })
    assert result.edits == ()
    assert result.refusals[0].message.startswith("A module named 'Option' hides the built-in type")


def test_every_use_of_a_new_keyword_is_listed():
    result = plan("fn f() -> Int {\n    let needs = 3\n    return needs\n}\n")
    assert [(r.line, r.column) for r in result.refusals] == [(2, 9), (3, 12)]


def test_edits_that_would_overlap_are_a_defect():
    with pytest.raises(AssertionError):
        migrate._ordered([migrate.Edit(0, 5, "", "E2"), migrate.Edit(3, 4, "x", "E1")])


def test_kept_outside_notices_a_changed_character():
    text = "fn main() -> Void {\n    print(1)\n}\n"
    result = plan(text)
    output = migrate.apply(text, result.edits).replace("print(1)", "print(2)")
    assert not migrate.kept_outside(text, result.edits, output)

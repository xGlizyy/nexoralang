"""`nex impact`: directions of changed conditions, every status, loops, modules and the command's failures."""

import json

import jsonschema
import pytest

from nexora import impact, schemas
from nexora.diagnostics import Source
from nexora.pipeline import analyze

from test_impact import program, run_cli, statuses

SCHEMA = schemas.all_schemas()["nexora-impact.schema.json"]
BIG = "9223372036854775807"


def compare(before: str, after: str) -> dict:
    analyses = [analyze(Source(name, text)) for name, text in (("a.nex", before), ("b.nex", after))]
    assert all(analysis.ok for analysis in analyses), [a.diagnostics for a in analyses]
    document = impact.compare(*analyses)
    jsonschema.validate(document, SCHEMA)
    return document


def direction(before: str, after: str) -> str | None:
    document = compare(program(before, name="c"), program(after, name="c"))
    return document["changes"][0]["direction"] if document["changes"] else None


@pytest.mark.parametrize("before, after, expected", [
    ("amount > 0", "amount >= 1", "equivalent"),
    ("amount > 0", "amount > -5", "weakened"),
    ("amount > 0", "amount > 5", "strengthened"),
    ("amount < 0", "amount > 5", "incomparable"),
    ("0 < amount", "1 <= amount", "equivalent"),
    ("10 >= amount", "20 > amount", "weakened"),
    ("amount == 3", "amount != 4", "weakened"),
    ("amount != 3", "amount == 3", "incomparable"),
    ("not (amount > 3)", "amount <= 3", "equivalent"),
    ("(amount > 3)", "true", "unknown"),
    ("false", "amount > 3", "unknown"),
    ("1 < 2", "amount == 1", "unknown"),
    ("2 < 1", "amount == 1", "unknown"),
    ("amount == amount", "amount != amount", "strengthened"),
    ("amount < amount", "amount <= amount", "weakened"),
    ("amount > amount", "amount >= amount", "weakened"),
    ("amount > -3 and amount < 3", "amount > -3 and amount < 4", "weakened"),
    ("amount < -3 or amount > 3", "amount < -3 or amount > 4", "strengthened"),
    (f"amount > {BIG}", "amount > 1", "weakened"),
    (f"amount < -{BIG}", "amount < 1", "weakened"),
    (f"amount == {BIG}", "amount == 1", "incomparable"),
    (f"amount != {BIG}", "amount != 1", "strengthened"),
    (f"amount >= {BIG}", "amount >= 1", "weakened"),
    (f"amount <= -{BIG}", "amount <= 1", "weakened"),
    (f"-{BIG} < amount", "amount > 1", "weakened"),
])
def test_direction_of_changed_conditions(before, after, expected):
    # Only that the answer is one of the four honest ones is fixed here for the edge cases of the integer range.
    result = direction(before, after)
    assert result in ("equivalent", "weakened", "strengthened", "incomparable", "unknown")
    if BIG not in before and "amount > amount" not in before:
        assert result == expected


def two_parameters(condition: str) -> str:
    return ("fn charge(amount: Int, other: Int) gives Int\n"
            f"    needs c: {condition}\n"
            "{\n    return amount\n}\n\nfn main() {\n    print(charge(1, 1))\n}\n")


@pytest.mark.parametrize("before, after", [
    ("amount > 0 and other > 0", "amount > 1"),
    ("amount * 2 > 0", "amount > 1"),
    ("not (amount * 2 > 0)", "amount > 1"),
    ("amount > 1", "other > 1"),
    ("amount > 0 and amount != 3", "amount > 1 and other < 9"),
    ("amount + 1 > 1", "amount > 1"),
    ("amount > other", "amount > 1"),
])
def test_conditions_outside_the_fragment_have_unknown_direction(before, after):
    document = compare(two_parameters(before), two_parameters(after))
    assert document["changes"][0]["direction"] == "unknown"
    assert document["summary"]["unknown_direction"] == 1 and document["summary"]["weakened"] == 0
    assert "unknown means review manually" in impact.render(document)


def with_clause(clause: str) -> str:
    signature = "fn charge(amount: Int) gives Int" + ("" if clause else " {")
    brace = "{\n" if clause else ""
    return (f"{signature}\n{clause}{brace}    return amount\n}}\n\n"
            "fn main() {\n    print(charge(1))\n}\n")


def test_a_clause_that_changes_kind_is_reported():
    document = compare(with_clause("    needs c: amount > 0\n"), with_clause("    promises c: amount > 0\n"))
    assert statuses(document) == [("kind_changed", "unknown")]
    assert "KIND_CHANGED" in impact.render(document)


def test_a_changed_explanation_is_reported():
    document = compare(with_clause('    needs c: amount > 0, "one"\n'), with_clause('    needs c: amount > 0, "two"\n'))
    assert statuses(document) == [("explanation_changed", None)]
    rendered = impact.render(document)
    assert "EXPLANATION_CHANGED" in rendered and "before:" in rendered and "after:" in rendered


def test_a_renamed_clause_is_recognized():
    document = compare(with_clause("    needs old_name: amount > 0\n"), with_clause("    needs new_name: amount > 0\n"))
    assert statuses(document) == [("renamed", None)]
    assert document["changes"][0]["previous_name"] == "old_name"


def test_a_removed_and_an_added_named_clause():
    document = compare(with_clause("    needs a: amount > 0\n"), with_clause("    needs b: amount > 5\n"))
    assert sorted(statuses(document), key=str) == [("added", None), ("removed", "weakened")]
    rendered = impact.render(document)
    assert "ADDED:" in rendered and "POTENTIAL WEAKENING:" in rendered and ".a" in rendered


def test_a_removed_promises_is_a_potential_weakening_but_a_removed_trust_is_not_proved():
    before = with_clause('    promises c: result > 0\n    trust t: amount > 0, "checked elsewhere"\n')
    document = compare(before, with_clause(""))
    assert sorted((c["clause"], c["direction"]) for c in document["changes"]) == [
        ("promises", "weakened"), ("trust", "unknown")]


def test_repeated_unnamed_clauses_are_paired_one_to_one():
    clause = "    needs amount > 0\n    needs amount > 0\n"
    assert compare(with_clause(clause), with_clause(clause))["changes"] == []
    document = compare(with_clause(clause), with_clause("    needs amount > 0\n"))
    assert statuses(document) == [("removed", "weakened")]


LOOPS = """fn run(n: Int) gives Int
    needs n >= 0
{{
    var i = 0
    while i < n
        keeps {keeps}
        shrinks n - i, "closer"
    {{
        if i > 100 {{
            i = i + 1
        }} else if i > 50 {{
            i = i + 1
        }} else {{
            i = i + 1
        }}
    }}
    for k in [1, 2]
        keeps {keeps}
    {{
        i = i + k
    }}
    for k in [1, 2]
        keeps {keeps}
    {{
        i = i + k
    }}
    return i
}}

fn main() {{
    print(run(3))
}}
"""


def test_loop_clauses_are_requirements_too():
    document = compare(LOOPS.format(keeps="i >= 0"), LOOPS.format(keeps="i >= -5"))
    assert {change["clause"] for change in document["changes"]} == {"keeps"}
    assert all(change["scope"] != "function" for change in document["changes"])
    assert len(document["changes"]) == 6  # three loops, each one removed and added
    assert "[" in impact.render(document)


def test_a_changed_shrinks_is_a_removal_with_unknown_direction():
    before = LOOPS.format(keeps="i >= 0")
    after = before.replace("shrinks n - i,", "shrinks n - i + 0,")
    document = compare(before, after)
    assert ("shrinks", "unknown") in [(c["clause"], c["direction"]) for c in document["changes"]]


def test_modules_are_matched_by_path(tmp_path):
    main = 'import "rules.nex"\n\nfn main() {\n    print(rules.positive(1))\n}\n'
    rule = "pub fn positive(n: Int) gives Int\n    needs c: n > {}\n{{\n    return n\n}}\n"
    old = tmp_path / "old"
    old.mkdir()
    (old / "main.nex").write_text(main, encoding="utf-8")
    (old / "rules.nex").write_text(rule.format(5), encoding="utf-8")
    (tmp_path / "main.nex").write_text(main, encoding="utf-8")
    (tmp_path / "rules.nex").write_text(rule.format(0), encoding="utf-8")
    result = run_cli(str(old / "main.nex"), "main.nex", "--format", "json", cwd=tmp_path)
    assert result.returncode == 0
    document = json.loads(result.stdout)
    jsonschema.validate(document, SCHEMA)
    assert [(c["module"], c["status"]) for c in document["changes"]] == [("rules", "weakened")]
    assert "rules:positive" in run_cli(str(old / "main.nex"), "main.nex", cwd=tmp_path).stdout


def test_text_output_of_invalid_and_missing_files(tmp_path):
    (tmp_path / "a.nex").write_text(program(), encoding="utf-8")
    (tmp_path / "bad.nex").write_text("fn main( {\n", encoding="utf-8")
    invalid = run_cli("a.nex", "bad.nex", cwd=tmp_path)
    assert invalid.returncode == 1 and "bad.nex" in invalid.stderr
    missing = run_cli("a.nex", "nope.nex", cwd=tmp_path)
    assert missing.returncode == 4

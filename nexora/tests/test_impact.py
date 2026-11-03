"""`nex impact`: requirement changes between two versions of a program (nexora.impact/1)."""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema

from nexora import impact, schemas
from nexora.diagnostics import Source
from nexora.pipeline import analyze

SCHEMA = schemas.all_schemas()["nexora-impact.schema.json"]


def program(needs: str = "amount >= 0 and amount <= 100", name: str = "") -> str:
    lines = ["fn charge(amount: Int) gives Int" + ("" if needs else " {")]
    if needs:
        lines += [f"    needs {name + ': ' if name else ''}{needs}", "{"]
    lines += ["    return amount", "}", "", "fn main() {", "    print(charge(1))", "}", ""]
    return "\n".join(lines)


def compare(before: str, after: str) -> dict:
    analyses = [analyze(Source(name, text)) for name, text in (("a.nex", before), ("b.nex", after))]
    assert all(analysis.ok for analysis in analyses)
    document = impact.compare(*analyses)
    jsonschema.validate(document, SCHEMA)
    return document


def statuses(document: dict) -> list[tuple[str, str | None]]:
    return [(change["status"], change["direction"]) for change in document["changes"]]


def test_identical_programs_have_no_changes():
    document = compare(program(), program())
    assert document["changes"] == []
    assert impact.render(document) == "No requirement changes."


def test_a_wider_range_is_a_proven_weakening():
    document = compare(program(name="range"), program("amount >= 0 and amount <= 200", name="range"))
    assert statuses(document) == [("weakened", "weakened")]
    assert document["summary"]["weakened"] == 1


def test_a_narrower_range_is_not_a_weakening():
    document = compare(program(name="range"), program("amount >= 10 and amount <= 50", name="range"))
    assert statuses(document) == [("condition_changed", "strengthened")]
    assert document["summary"]["weakened"] == 0


def test_an_unnamed_condition_that_changes_is_a_removal_and_an_addition():
    # Unnamed clauses are matched by kind and condition, so a new condition is never taken for the old one.
    document = compare(program(), program("amount >= 0 and amount <= 200"))
    assert sorted(statuses(document)) == [("added", None), ("removed", "weakened")]


def test_a_removed_needs_is_a_potential_weakening():
    document = compare(program(), program(""))
    assert statuses(document) == [("removed", "weakened")]
    assert document["summary"]["removed"] == 1
    assert "POTENTIAL WEAKENING" in impact.render(document)


def test_an_added_needs_is_reported_without_direction():
    document = compare(program(""), program())
    assert statuses(document) == [("added", None)]


def test_a_condition_outside_the_fragment_is_unknown_never_safe():
    document = compare(program("amount > 0 and amount != 5", name="shape"),
                       program("amount > 1 or amount == 0", name="shape"))
    assert document["changes"][0]["direction"] in ("unknown", "incomparable")
    assert document["summary"]["weakened"] == 0


def test_a_named_needs_is_matched_by_name():
    before = program("amount > 0", name="positive")
    after = program("amount >= 0", name="positive")
    document = compare(before, after)
    assert [change["name"] for change in document["changes"]] == ["positive"]
    assert document["changes"][0]["direction"] == "weakened"


def test_neither_program_is_run(capsys):
    # main prints, so running either program would write to the standard output.
    compare(program(), program(""))
    assert capsys.readouterr().out == ""


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "nexora", "impact", *arguments],
                          capture_output=True, encoding="utf-8", cwd=cwd)


def test_the_command_writes_text_and_json(tmp_path):
    (tmp_path / "a.nex").write_text(program(), encoding="utf-8")
    (tmp_path / "b.nex").write_text(program(""), encoding="utf-8")
    text = run_cli("a.nex", "b.nex", cwd=tmp_path)
    assert text.returncode == 0
    assert "POTENTIAL WEAKENING" in text.stdout
    document = json.loads(run_cli("a.nex", "b.nex", "--format", "json", cwd=tmp_path).stdout)
    jsonschema.validate(document, SCHEMA)
    assert document["ok"] is True and document["summary"]["removed"] == 1


def test_invalid_and_missing_files_have_the_usual_exit_codes(tmp_path):
    (tmp_path / "a.nex").write_text(program(), encoding="utf-8")
    (tmp_path / "bad.nex").write_text("fn main( {\n", encoding="utf-8")
    invalid = run_cli("a.nex", "bad.nex", "--format", "json", cwd=tmp_path)
    assert invalid.returncode == 1
    document = json.loads(invalid.stdout)
    jsonschema.validate(document, SCHEMA)
    assert document["ok"] is False and document["diagnostics"]
    missing = run_cli("a.nex", "nope.nex", "--format", "json", cwd=tmp_path)
    assert missing.returncode == 4
    jsonschema.validate(json.loads(missing.stdout), SCHEMA)

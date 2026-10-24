"""`nex check --evidence` and `nexora.evidence/1` (decision 0019, section 5), as phase 1 defines
them: only the enforcement dimension is computed, and nothing is run."""

import json

import jsonschema
import pytest

from nexora import cli, schemas, tooling

from test_syntax_012 import PERCENTAGE, SUM_TO

SCHEMA = schemas.all_schemas()["nexora-evidence.schema.json"]

MAIN = "\nfn main() {\n    print(to_text(percentage(3, 12)))\n}\n"

TRUSTING = """\
fn halve(n: Int) gives Int
    trust even: n / 2 * 2 == n, "Every caller passes an even number"
    needs n >= 0
{
    return n / 2
}

fn main() {
    print(to_text(halve(4)))
}
"""


def nex(arguments: list[str], files: dict[str, str], tmp_path, monkeypatch, capsys) -> tuple[int, str, str]:
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    code = cli.main(arguments)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def evidence(source: str) -> dict:
    document = tooling.get_evidence(source, "program.nex")
    jsonschema.validate(document, SCHEMA)
    return document


def test_the_report_of_percentage_is_the_one_of_the_decision(tmp_path, monkeypatch, capsys):
    code, out, err = nex(["check", "--evidence", "percentage.nex"], {"percentage.nex": PERCENTAGE + MAIN},
                         tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")
    # 5.8, byte for byte.
    assert out == (
        "percentage.nex: 4 promises in 1 function (computed: enforcement)\n"
        "  percentage\n"
        "    needs whole_positive    checked\n"
        "    needs part_inside       checked\n"
        "    needs fits              checked\n"
        "    promises in_range       checked\n"
    )


def test_an_entry_has_the_fields_of_the_decision():
    document = evidence(PERCENTAGE + MAIN)
    assert document["schema"] == "nexora.evidence/1"
    assert document["computed"] == {"static": False, "observed": False}
    # 5.7, with the observed dimension of an analysis instead of the one of nex test.
    assert document["clauses"][0] == {
        "id": {"module": "", "function": "percentage", "name": "whole_positive", "kind": "needs",
               "stable": True},
        "condition": "whole > 0",
        "message": "A percentage of nothing is not defined",
        "enforcement": "checked",
        "static": {"status": "not_computed", "reason": "phase_not_implemented"},
        "observed": {"status": "not_computed", "reason": "analysis_only"},
        "summary": "checked",
    }
    promise = document["clauses"][3]
    assert promise["id"]["kind"] == "promises"
    assert promise["static"] == {"status": "not_applicable"}
    assert promise["observed"] == {"status": "not_computed", "reason": "analysis_only"}


def test_examples_have_no_entry_and_loop_clauses_follow_the_header():
    document = evidence(SUM_TO + "\nfn main() {\n    print(to_text(sum_to(4)))\n}\n")
    assert [(c["id"]["kind"], c["id"]["name"]) for c in document["clauses"]] == [
        ("needs", "natural"), ("needs", "small"), ("promises", "gauss"),
        ("keeps", "partial_sum"), ("shrinks", "steps_left")]
    loop = document["clauses"][3:]
    assert all(c["static"] == {"status": "not_applicable"} for c in loop)
    assert all(c["summary"] == "checked" for c in loop)


def test_a_trust_is_never_presented_as_checked(tmp_path, monkeypatch, capsys):
    trust, needs = evidence(TRUSTING)["clauses"]
    # 5.2 and 5.6: never evaluated, never decided, never observed.
    assert trust["enforcement"] == trust["summary"] == "trusted"
    assert trust["static"] == trust["observed"] == {"status": "not_applicable"}
    assert trust["message"] == "Every caller passes an even number"
    assert needs["id"] == {"module": "", "function": "halve", "name": None, "kind": "needs", "stable": False}
    assert needs["summary"] == "checked"

    code, out, _ = nex(["check", "--evidence", "halve.nex"], {"halve.nex": TRUSTING}, tmp_path, monkeypatch, capsys)
    assert code == 0
    # An unnamed clause is shown by its condition.
    assert out.splitlines()[1:] == ["  halve", "    trust even      trusted", "    needs n >= 0    checked"]


def test_a_program_without_clauses_has_no_entries(tmp_path, monkeypatch, capsys):
    program = 'fn main() {\n    print("hi")\n}\n'
    assert evidence(program)["clauses"] == []
    code, out, _ = nex(["check", "--evidence", "hi.nex"], {"hi.nex": program}, tmp_path, monkeypatch, capsys)
    assert (code, out) == (0, "hi.nex: 0 promises in 0 functions (computed: enforcement)\n")


def test_the_clauses_of_every_module_are_listed_by_module_path(tmp_path, monkeypatch, capsys):
    files = {
        "main.nex": 'import "lib/geo.nex"\nimport "a.nex"\n\nfn main()\n    trust t: true, "Nothing"\n{\n'
                    "    print(to_text(geo.area(2) + a.one()))\n}\n",
        "a.nex": "pub fn one() gives Int\n    promises result == 1\n{\n    return 1\n}\n",
        "lib/geo.nex": 'import "sub/base.nex"\n\npub fn area(side: Int) gives Int\n'
                       '    needs positive: side > 0, "A side is positive"\n{\n    return base.square(side)\n}\n',
        "lib/sub/base.nex": "pub fn square(x: Int) gives Int\n    needs x >= 0\n{\n    return x * x\n}\n",
    }
    code, out, err = nex(["check", "--evidence", "--format", "json", "main.nex"], files, tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")
    document = json.loads(out)
    jsonschema.validate(document, SCHEMA)
    # 7.1: relative to the directory of the entry file, with '/'; "" for the entry file, which comes first.
    assert [(c["id"]["module"], c["id"]["function"], c["id"]["kind"]) for c in document["clauses"]] == [
        ("", "main", "trust"), ("a.nex", "one", "promises"), ("lib/geo.nex", "area", "needs"),
        ("lib/sub/base.nex", "square", "needs")]

    code, out, _ = nex(["check", "--evidence", "main.nex"], files, tmp_path, monkeypatch, capsys)
    assert out.splitlines()[0] == "main.nex: 4 promises in 4 functions (computed: enforcement)"
    assert "  area (lib/geo.nex)" in out.splitlines()


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_a_program_with_errors_has_no_evidence(output_format, tmp_path, monkeypatch, capsys):
    program = "fn main() {\n    print(x)\n}\n"
    code, out, err = nex(["check", "--evidence", "--format", output_format, "bad.nex"], {"bad.nex": program},
                         tmp_path, monkeypatch, capsys)
    assert code == 1
    if output_format == "json":
        document = json.loads(out)
        jsonschema.validate(document, SCHEMA)
        assert (document["ok"], document["clauses"]) == (False, None)
        assert [d["code"] for d in document["diagnostics"]] == ["E2005"]
    else:
        # The same as nex check without --evidence.
        assert out == ""
        assert err.endswith("error: bad.nex: check failed with 1 error\n")


def test_a_file_that_cannot_be_read_is_code_4(tmp_path, monkeypatch, capsys):
    code, out, _ = nex(["check", "--evidence", "--format", "json", "missing.nex"], {}, tmp_path, monkeypatch, capsys)
    assert code == 4
    document = json.loads(out)
    jsonschema.validate(document, SCHEMA)
    assert document["clauses"] is None
    assert document["diagnostics"][0]["code"] == "E0001"


def test_the_evidence_document_starts_as_the_diagnostics_document(tmp_path, monkeypatch, capsys):
    files = {"percentage.nex": PERCENTAGE + MAIN}
    _, plain, _ = nex(["check", "--format", "json", "percentage.nex"], files, tmp_path, monkeypatch, capsys)
    _, with_evidence, _ = nex(["check", "--evidence", "--format", "json", "percentage.nex"], files,
                              tmp_path, monkeypatch, capsys)
    plain, with_evidence = json.loads(plain), json.loads(with_evidence)
    assert plain["schema"] == "nexora.diagnostics/1"
    assert {key: value for key, value in with_evidence.items() if key in plain and key != "schema"} == \
        {key: value for key, value in plain.items() if key != "schema"}


def test_nothing_is_run(tmp_path, monkeypatch, capsys):
    from nexora import interpreter

    def forbidden(*arguments, **options):
        raise AssertionError("nex check --evidence started the interpreter")
    monkeypatch.setattr(interpreter.Interpreter, "run", forbidden)
    monkeypatch.setattr(interpreter, "run", forbidden)
    code, _, _ = nex(["check", "--evidence", "halve.nex"], {"halve.nex": TRUSTING}, tmp_path, monkeypatch, capsys)
    assert code == 0


@pytest.mark.parametrize("path, entry, expected", [
    ("main.nex", "main.nex", ""),
    ("lib/geo.nex", "main.nex", "lib/geo.nex"),
    ("C:/work/lib/geo.nex", "C:/work/main.nex", "lib/geo.nex"),
    ("/work/app/lib/geo.nex", "/work/app/main.nex", "lib/geo.nex"),
    ("p/../shared.nex", "p/main.nex", "../shared.nex"),
    ("lib/b.nex", "./main.nex", "lib/b.nex"),
])
def test_a_module_is_identified_by_its_path_relative_to_the_entry_file(path, entry, expected):
    assert tooling._module_id(path, entry) == expected


def test_a_program_given_by_its_absolute_path_has_the_same_module_ids(tmp_path, monkeypatch, capsys):
    files = {"main.nex": 'import "lib/one.nex"\n\nfn main() {\n    print(to_text(one.one()))\n}\n',
             "lib/one.nex": "pub fn one() gives Int\n    promises result == 1\n{\n    return 1\n}\n"}
    _, out, _ = nex(["check", "--evidence", "--format", "json", str(tmp_path / "main.nex")], files,
                    tmp_path, monkeypatch, capsys)
    assert [clause["id"]["module"] for clause in json.loads(out)["clauses"]] == ["lib/one.nex"]

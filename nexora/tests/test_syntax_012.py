"""The acceptance cases of the 0.12 syntax (decision 0019, 4.3): A1-A12 must be accepted and
R1-R18 must be rejected.

Each case is run with the commands, in their JSON form, as 4.3 says when a case passes. A
fragment of the decision is completed into the smallest program in which the construct of the
case is the only thing being checked.
"""

import json

import pytest

from nexora import cli

PERCENTAGE = """\
pub fn percentage(part: Int, whole: Int) gives Int
    needs whole_positive: whole > 0, "A percentage of nothing is not defined"
    needs part_inside: part >= 0 and part <= whole, "The part has to be inside the whole"
    needs fits: part <= 92233720368547758, "part * 100 has to fit in an Int"
    promises in_range: result >= 0 and result <= 100
    example percentage(3, 12) == 25
    example percentage(12, 12) == 100
{
    return part * 100 / whole
}
"""

SUM_TO = """\
fn sum_to(n: Int) gives Int
    needs natural: n >= 0, "Only natural numbers"
    needs small: n <= 3037000499, "n * (n + 1) has to fit in an Int"
    promises gauss: result == n * (n + 1) / 2
    example sum_to(4) == 10
{
    var total = 0
    var i = 0
    while i < n
        keeps partial_sum: total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        shrinks steps_left: n - i, "Each turn moves i one step closer to n"
    {
        i = i + 1
        total = total + i
    }
    return total
}
"""

FIND = """\
fn find(names: List[Text], wanted: Text) gives Option[Int] {
    var index = 0
    while index < List.length(names)
        shrinks remaining: List.length(names) - index, "Each turn looks at one more name"
    {
        if List.get(names, index) == wanted {
            return Some(index)
        }
        index = index + 1
    }
    return None
}

fn show_all(names: List[Text]) {
    for name in names {
        print(name)
    }
}

fn main() {
    print(Option.value_or(find(["ada", "grace"], "grace"), -1))
    show_all(["ada", "grace"])
}
"""

PARSE_AGE = """\
fn parse_age(text: Text) gives Int
    needs digits: Int.can_parse(text), "Only whole numbers"
    trust plausible: Int.parse(text) < 150, "Ages come from a form that already limits them"
{
    return Int.parse(text)
}
"""

ACCEPTED = {
    "A1": PERCENTAGE,
    "A2": SUM_TO,
    "A3": FIND,
    "A4": PARSE_AGE,
    "A5": "fn f(x: Int) gives Int {\n    return x\n}\n",
    "A6": "fn log(x: Int) {\n    print(x)\n}\n",
    "A7": "fn g(x: Int) gives Int\n    needs x > 0\n{\n    return x\n}\n",
    "A8": "fn g(x: Int) gives Int\n    // why\n    needs x > 0\n\n    promises result > 0\n{\n    return x\n}\n",
    "A9": "fn g(x: Int) gives Int\n    needs ok: (x > 0 and\n        x < 10)\n{\n    return x\n}\n",
    "A10": ("fn c(xs: List[Int]) gives Int {\n    var count = 0\n    for x in xs\n        keeps seen: count >= 0\n"
            "    {\n        count = count + 1\n    }\n    return count\n}\n"),
    "A11": "fn h(x: Int) gives Int\n    example h(1) == 2\n{\n    return x * 2\n}\n",
    "A12": "pub fn p(x: Int) gives Int\n    needs positive: x > 0\n    promises result > 0\n{\n    return x\n}\n",
}

WITH_EXAMPLES = {"A1": 2, "A2": 1, "A11": 1}

# (program, code, line of the construct the case names)
REJECTED = {
    "R1": ("fn f(x: Int) gives Int\n{\n    return x\n}\n", "E1101", 2),
    "R2": ("fn f(x: Int) -> Int {\n    return x\n}\n", "E1108", 1),
    "R3": ("fn f(x: Int) gives Int {\n    requires x > 0\n    return x\n}\n", "E1107", 2),
    "R4": ("fn f(x: Int) gives Int {\n    needs x > 0\n    return x\n}\n", "E1106", 2),
    "R5": ("fn f(x: Int) gives Int\n    needs x > 0 {\n    return x\n}\n", "E1101", 2),
    "R6": ("fn w(n: Int) gives Int {\n    var i = 0\n    while i < n {\n        shrinks n - i\n        i = i + 1\n"
           "    }\n    return i\n}\n", "E1106", 4),
    "R7": ("fn w(n: Int) gives Int {\n    var i = 0\n    while i < n {\n        i = i + 1\n    }\n    return i\n}\n",
           "E2021", 3),
    "R8": ("fn c(xs: List[Int]) {\n    for x in xs\n        shrinks 1\n    {\n        print(x)\n    }\n}\n", "E2022", 3),
    "R9": ("fn f(x: Int) gives Int\n    needs a: x > 0\n    promises a: result > 0\n{\n    return x\n}\n", "E2031", 3),
    "R10": ("fn f(x: Int) gives Int\n    needs x: x > 0\n{\n    return x\n}\n", "E2031", 2),
    "R11": ("fn f(x: Int) gives Int\n    needs result > 0\n{\n    return x\n}\n", "E2005", 2),
    "R12": ("fn log(x: Int)\n    promises result > 0\n{\n    print(x)\n}\n", "E2005", 2),
    "R13": ("fn main() gives Int {\n    return 1\n}\n", "E2004", 1),
    "R14": ("fn f() gives Void {\n    print(1)\n}\n", "E2012", 1),
    "R15": ("fn f(x: Int) gives Int\n    trust t: x > 0\n{\n    return x\n}\n", "E1101", 2),
    "R16": ("fn f(x: Int) gives Int\n    example e: f(1) == 1\n{\n    return x\n}\n", "E1101", 2),
    "R17": ("fn f() gives Int {\n    let needs = 3\n    return 3\n}\n", "E1101", 2),
    "R18": ("fn f(x: Int) gives Int\n    needs x + 1\n{\n    return x\n}\n", "E2011", 2),
}


def nex(command: list[str], source: str, tmp_path, monkeypatch, capsys) -> tuple[int, str, str]:
    (tmp_path / "program.nex").write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    code = cli.main([command[0], "program.nex", *command[1:]])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("case", sorted(ACCEPTED, key=lambda name: int(name[1:])))
def test_each_accepted_case_passes_the_analysis_without_main(case, tmp_path, monkeypatch, capsys):
    code, out, _ = nex(["test", "--format", "json"], ACCEPTED[case], tmp_path, monkeypatch, capsys)
    document = json.loads(out)
    assert document["ok"] is True and document["diagnostics"] == [], document["diagnostics"]
    if case in WITH_EXAMPLES:
        assert code == 0
        assert document["status"] == "passed"
        assert len(document["examples"]) == WITH_EXAMPLES[case]
        assert all(example["status"] == "passed" for example in document["examples"])


def test_the_accepted_program_with_main_also_passes_nex_check(tmp_path, monkeypatch, capsys):
    code, out, err = nex(["check"], ACCEPTED["A3"], tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")


def test_a_trusted_condition_is_never_evaluated(tmp_path, monkeypatch, capsys):
    # 5.6: a false `trust` cannot stop the program.
    program = ("fn age(x: Int) gives Int\n    trust plausible: x < 150, \"From a form\"\n{\n    return x\n}\n\n"
               "fn main() {\n    print(age(200))\n}\n")
    code, out, err = nex(["run"], program, tmp_path, monkeypatch, capsys)
    assert (code, out, err) == (0, "200\n", "")


@pytest.mark.parametrize("case", sorted(REJECTED, key=lambda name: int(name[1:])))
def test_each_rejected_case_has_its_code_on_the_line_of_the_construct(case, tmp_path, monkeypatch, capsys):
    program, expected, line = REJECTED[case]
    command = ["check", "--format", "json"] if "fn main" in program else ["test", "--format", "json"]
    code, out, _ = nex(command, program, tmp_path, monkeypatch, capsys)
    document = json.loads(out)
    assert document["ok"] is False and code != 0
    found = [(item["code"], item["line"]) for item in document["diagnostics"]]
    assert (expected, line) in found, found


# Beyond the 30 cases: the rest of what decision 0019 fixes for phase 1.

from helpers import run_text  # noqa: E402

from nexora.diagnostics import Source  # noqa: E402
from nexora.pipeline import analyze  # noqa: E402


def diagnostics_of(text: str):
    """The diagnostics of the analysis without `main`, as `nex test` runs it."""
    return analyze(Source("program.nex", text), require_main=False).diagnostics


def check_codes(text: str) -> list[str]:
    return [diagnostic.code for diagnostic in diagnostics_of(text)]


@pytest.mark.parametrize("word, new, place", [
    ("requires", "needs", "function"), ("ensures", "promises", "function"),
    ("invariant", "keeps", "loop"), ("decreases", "shrinks", "loop"),
])
def test_each_clause_word_of_0_11_is_e1107_with_its_replacement(word, new, place):
    (error,) = diagnostics_of(f"fn main() {{\n    {word} true\n}}\n")
    assert (error.code, error.span.line) == ("E1107", 2)
    assert error.label == f"'{word}' is the syntax before 0.12: write '{new}' in the header of the {place}"
    assert "nex migrate" in error.hint


def test_an_old_clause_word_is_not_a_name_either():
    assert check_codes("fn main() {\n    let requires = 1\n}\n") == ["E1107"]


def test_the_old_arrow_to_void_says_to_remove_it():
    (error,) = diagnostics_of("fn main() -> Void {\n}\n")
    assert (error.code, error.label) == ("E1108", "Remove '-> Void': a function that gives nothing has no 'gives'")


def test_ai_and_tool_are_ordinary_names_from_0_12():
    assert run_text("fn main() {\n    let ai = 1\n    let tool = 2\n    print(ai + tool)\n}\n") == "3\n"


def test_value_and_value_or_replace_unwrap_and_unwrap_or():
    program = ("fn main() {\n    let none: Option[Int] = None\n    let failed: Result[Int, Text] = Err(\"no\")\n"
               "    let fine: Result[Int, Text] = Ok(3)\n"
               "    print(Option.value(Some(1)) + Option.value_or(none, 2))\n"
               "    print(Result.value(fine) + Result.value_or(failed, 4))\n}\n")
    assert run_text(program) == "3\n7\n"
    assert check_codes("fn main() {\n    print(Option.unwrap(Some(1)))\n}\n") == ["E2008"]


def test_a_clause_name_is_unique_across_the_function_and_its_loops():
    program = ("fn w(n: Int) gives Int\n    needs steps: n >= 0\n{\n    var i = 0\n    while i < n\n"
               "        shrinks steps: n - i\n    {\n        i = i + 1\n    }\n    return i\n}\n")
    (error,) = diagnostics_of(program)
    assert (error.code, error.span.line) == ("E2031", 6)
    assert error.notes == ("It is first used at line 2, column 5.",)


def test_result_cannot_name_a_clause():
    (error,) = diagnostics_of("fn f(x: Int) gives Int\n    promises result: result > 0\n{\n    return x\n}\n")
    assert (error.code, error.label) == ("E2031", "'result' cannot be the name of a clause")


def test_a_clause_name_is_lowercase_and_is_not_a_variable():
    assert check_codes("fn f(x: Int) gives Int\n    needs Big: x > 0\n{\n    return x\n}\n") == ["E1101"]
    assert check_codes("fn f(x: Int) gives Int\n    needs big: x > 0\n{\n    return big\n}\n") == ["E2005"]


def test_a_trust_is_type_checked_but_never_evaluated():
    assert check_codes('fn f(x: Int) gives Int\n    trust t: x + 1, "Why"\n{\n    return x\n}\n') == ["E2011"]
    program = ('fn f(x: Int) gives Int\n    trust t: 1 / x > 0, "Never evaluated"\n{\n    return x\n}\n\n'
               "fn main() {\n    print(f(0))\n}\n")
    assert run_text(program) == "0\n"


def test_a_broken_named_clause_is_named_in_the_diagnostic(tmp_path, monkeypatch, capsys):
    program = ('fn f(x: Int) gives Int\n    needs positive: x > 0, "Only positive"\n{\n    return x\n}\n\n'
               "fn main() {\n    print(f(0))\n}\n")
    code, _, err = nex(["run"], program, tmp_path, monkeypatch, capsys)
    assert code == 5
    assert "This call breaks needs 'positive' of 'f'" in err
    assert "The condition at line 2 is false: needs positive: x > 0" in err


# The clause words of 0.11 are reserved during the transition (decision 0019, section 9)

@pytest.mark.parametrize("program, line", [
    ("fn f(x: Int) gives Int\n    requires x > 0\n{\n    return x\n}\n", 2),            # in a header
    ("fn f(x: Int) gives Int\n    ensures result > 0\n{\n    return x\n}\n", 2),
    ("fn w(n: Int) {\n    var i = 0\n    while i < n\n        decreases n - i\n    {\n        i = i + 1\n    }\n}\n", 4),
    ("fn w(xs: List[Int]) {\n    for x in xs\n        invariant x > 0\n    {\n        print(x)\n    }\n}\n", 3),
    ("fn requires() {\n}\n", 1),                                                     # as a name
    ("fn f(ensures: Int) {\n}\n", 1),
    ("type R = { invariant: Int }\n", 1),
])
def test_an_old_clause_word_is_reserved_and_is_never_a_clause_of_0_12(program, line):
    diagnostics = diagnostics_of(program)
    assert ("E1107", line) in [(d.code, d.span.line) for d in diagnostics]
    assert all(d.code in ("E1107", "E1101", "E2021") for d in diagnostics), [d.code for d in diagnostics]


def test_the_tools_list_the_old_clause_words_as_reserved_and_not_as_keywords():
    from nexora import api, tooling

    old = {"requires", "ensures", "invariant", "decreases"}
    for language in (api.language_info(), tooling.get_capabilities()["language"]):
        assert old <= set(language["reserved_words"])
        assert not old & set(language["keywords"])


# `nexora.capabilities/1` keeps the clause names it was published with (decision of 2026-10-24)

def test_capabilities_1_keeps_requires_and_ensures_and_symbols_2_uses_the_new_words():
    import jsonschema

    from nexora import schemas, tooling

    capabilities = tooling.get_capabilities()
    assert capabilities["schema"] == "nexora.capabilities/1"
    jsonschema.validate(capabilities, schemas.all_schemas()["nexora-capabilities.schema.json"])
    clauses = {c["clause"] for b in capabilities["language"]["builtins"] for c in b["contracts"]}
    assert clauses == {"requires", "ensures"}
    symbols = tooling.get_symbols("fn main() {\n}\n")
    assert {c["clause"] for b in symbols["builtins"] for c in b["contracts"]} == {"needs", "promises"}

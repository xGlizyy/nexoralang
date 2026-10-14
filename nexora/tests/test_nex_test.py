"""Evaluating examples: the engine, `nexora.api.test_source` and `nex test` (decision 0008).

The numbers in brackets are the cases of the test matrix of the decision.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexora import interpreter
from nexora.checker import own_calls
from nexora.diagnostics import Source
from nexora.interpreter import run_example
from nexora.pipeline import analyze

ROOT = Path(__file__).resolve().parents[1]


def double(*clauses: str, body: str = "return n * 2", contracts: tuple[str, ...] = ()) -> str:
    lines = "\n".join(f"    {line}" for line in (*contracts, *clauses, body))
    return f"fn double(n: Int) -> Int {{\n{lines}\n}}\n"


def runs(text: str, function: str = "double"):
    """Every example of `function`, evaluated by the engine, each in its own interpreter."""
    analysis = analyze(Source("t.nex", text), require_main=False)
    assert analysis.ok, [(d.code, d.label) for d in analysis.diagnostics]
    declared = analysis.checked.functions[function]
    return [run_example(analysis.checked, example, own_calls(example, function)) for example in declared.examples]


def calls(run) -> list[tuple[str, str, object]]:
    return [(record.node.callee, record.status, record.value) for record in run.invoked]


# The engine

def test_a_true_example_has_a_value_and_its_call():                                     # [1]
    (run,) = runs(double("example double(2) == 4"))
    assert (run.value, run.error, calls(run)) == (True, None, [("double", "returned", 4)])


def test_a_false_example_finishes_without_error():                                      # [2]
    (run,) = runs(double("example double(2) == 5"))
    assert (run.value, run.error, calls(run)) == (False, None, [("double", "returned", 4)])


def test_own_calls_are_recorded_in_the_order_they_are_invoked():                        # [5]
    nested, added = runs(double("example double(double(1)) == 4", "example double(1) + double(2) == 6"))
    assert [(r.node.span.column, r.value) for r in nested.invoked] == [(20, 2), (13, 4)]
    assert [(r.node.span.column, r.value) for r in added.invoked] == [(13, 2), (25, 4)]


def test_a_broken_requires_stops_the_call_that_was_invoked():                           # [12]
    (run,) = runs(double("example double(-1) == -2", contracts=('requires n >= 0, "Only natural numbers"',)))
    assert run.value is None and run.error.code == "E4001"
    assert calls(run) == [("double", "stopped", None)]


def test_a_broken_ensures():                                                            # [13]
    (run,) = runs(double("example double(0) == 0", contracts=("ensures result > n",)))
    assert run.error.code == "E4002" and calls(run) == [("double", "stopped", None)]


def test_a_broken_requires_deeper_in_the_calls():                                       # [14]
    text = ("fn h(n: Int) -> Int {\n    requires n > 0\n    return n\n}\n\n"
            "fn g(n: Int) -> Int {\n    return h(n - 1)\n}\n\n"
            "fn f(n: Int) -> Int {\n    example f(1) == 0\n    return g(n)\n}\n")
    (run,) = runs(text, "f")
    assert run.error.code == "E4001"
    assert (run.error.span.line, run.error.span.column) == (7, 12)        # the call to h, inside g
    assert run.error.notes[-2:] == ("In 'g', called at line 12, column 12.", "In 'f', called at line 11, column 13.")


def test_a_runtime_error_in_another_function():                                         # [15]
    text = "fn broken(n: Int) -> Int {\n    return n / 0\n}\n\n" + double("example double(broken(1)) == 0")
    (run,) = runs(text)
    assert run.error.code == "E3001" and run.invoked == []


def test_a_broken_refined_type():                                                       # [16]
    text = ("type Percent = Int where value >= 0 and value <= 100\n\n"
            "fn f(p: Percent) -> Int {\n    example f(Percent(150 - 1)) == 1\n    return p\n}\n")
    (run,) = runs(text, "f")
    assert run.error.code == "E4003"


def test_each_example_starts_with_a_clean_interpreter():                                # [19]
    text = "fn loop(n: Int) -> Int {\n    example loop(1) == 1\n    example loop(0) == 0\n" \
           "    print(\"in loop\")\n    if n == 0 {\n        return 0\n    }\n    return loop(n)\n}\n"
    endless, finite = runs(text, "loop")
    assert endless.error.code == "E3004" and endless.output.count("in loop\n") == 1000
    assert (finite.value, finite.error, finite.output) == (True, None, "in loop\n")


def test_short_circuit_and_calls_never_invoked():                                       # [20]
    text = double("example double(1) == 3 and double(2) == 4")
    analysis = analyze(Source("t.nex", text), require_main=False)
    (example,) = analysis.checked.functions["double"].examples
    first, second = own_calls(example, "double")
    run = run_example(analysis.checked, example, [first, second])
    assert run.value is False and calls(run) == [("double", "returned", 2)]
    assert run.short_circuited == {id(second)}


def test_or_skips_its_right_side_when_the_left_is_true():
    (run,) = runs(double("example double(2) == 4 or double(3) == 0"))
    assert run.value is True and calls(run) == [("double", "returned", 4)] and len(run.short_circuited) == 1


def test_a_call_after_an_error_is_never_invoked():                                      # [35]
    (run,) = runs(double("example double(double(-1)) == 4", contracts=("requires n >= 0",)))
    assert run.error.code == "E4001"
    assert [(r.node.span.column, r.status) for r in run.invoked] == [(20, "stopped")]
    assert run.short_circuited == set()


def test_the_outer_call_stops_after_the_inner_one_returned():                           # [12] [35]
    (run,) = runs(double("example double(double(1)) == 4", contracts=("requires n >= 4",),
                         body="return n * 4"))
    # double(1) breaks the requires: the inner call is the one stopped, the outer never starts.
    assert [(r.node.span.column, r.status) for r in run.invoked] == [(20, "stopped")]
    (run,) = runs(double("example double(double(4)) == 64", contracts=("requires n < 10",), body="return n * 4"))
    # double(4) returns 16, and then the outer call breaks the requires: returned first, stopped last.
    assert [(r.node.span.column, r.status, r.value) for r in run.invoked] == [(20, "returned", 16), (13, "stopped", None)]
    assert run.error.code == "E4001" and (run.error.span.line, run.error.span.column) == (3, 13)


def test_short_circuit_marks_every_own_call_in_the_skipped_operand():                   # [20]
    document = api.test_source(double("example double(1) == 3 and (double(double(2)) == 8 or not (double(3) == 6))"))
    (example,) = document["examples"]
    assert [v["call"] for v in example["values"]] == ["double(1)"]
    # In the order of the text, nested calls included.
    assert [(n["call"], n["reason"]) for n in example["not_evaluated"]] == [
        ("double(double(2))", "short_circuit"), ("double(2)", "short_circuit"), ("double(3)", "short_circuit")]


def test_a_skipped_call_stays_short_circuit_when_a_later_call_fails():                  # [20] [35]
    document = api.test_source(double("example (double(1) == 2 or double(2) == 0) and double(-1) == 0",
                                      contracts=("requires n >= 0",)))
    (example,) = document["examples"]
    assert example["status"] == "error" and example["diagnostic"]["code"] == "E4001"
    assert [(v["call"], v["status"]) for v in example["values"]] == [("double(1)", "returned"), ("double(-1)", "stopped")]
    assert [(n["call"], n["reason"]) for n in example["not_evaluated"]] == [("double(2)", "short_circuit")]


def test_a_failure_after_an_own_call_returned_keeps_its_value():                        # [15]
    document = api.test_source(double("example double(2) / double(0) == 1"))
    (example,) = document["examples"]
    assert (example["status"], example["diagnostic"]["code"]) == ("error", "E3001")
    assert [(v["call"], v["status"], v["value"]) for v in example["values"]] == [
        ("double(2)", "returned", "4"), ("double(0)", "returned", "0")]
    assert example["not_evaluated"] == []


def test_an_expression_over_several_lines_is_reported_as_written():
    document = validate(api.test_source(double("example (double(1) ==\n        3)")))
    (example,) = document["examples"]
    assert example["expression"] == "(double(1) ==\n        3)"
    assert (example["span"]["line"], example["span"]["end_line"]) == (2, 3)
    assert example["values"][0]["call"] == "double(1)" and example["diagnostic"]["code"] == "E4004"


def test_the_same_program_gives_the_same_document():
    text = double("example double(2) == 5", "example double(-1) == 0", "example double(1) == 3 and double(2) == 4",
                  contracts=("requires n >= 0",), body='print("n")\n    return n * 2')
    assert api.test_source(text) == api.test_source(text)


def test_output_is_collected_per_example():                                             # [21]
    text = 'fn shout(n: Int) -> Int {\n    example shout(1) == 1\n    example shout(2) == 2\n' \
           '    print("n is " + to_text(n))\n    return n\n}\n'
    first, second = runs(text, "shout")
    assert (first.output, second.output) == ("n is 1\n", "n is 2\n")


def test_a_recursion_error_becomes_e3004_and_the_next_example_runs(monkeypatch):        # [36]
    # Raised on purpose, so the test does not depend on Python's recursion limit or the stack.
    original = interpreter.Interpreter._invoke
    calls_made = []

    def invoke(self, function, arguments, site):
        calls_made.append(arguments)
        if len(calls_made) == 1:
            raise RecursionError
        return original(self, function, arguments, site)

    monkeypatch.setattr(interpreter.Interpreter, "_invoke", invoke)
    first, second = runs(double("example double(1) == 2", "example double(2) == 4"))
    assert first.error.code == "E3004" and first.error.span is None
    assert (second.value, second.error) == (True, None)


def test_a_defect_of_nexora_is_not_turned_into_a_result(monkeypatch):                  # [31]
    def broken(self, function, arguments, site):
        raise KeyError("a bug")

    monkeypatch.setattr(interpreter.Interpreter, "_invoke", broken)
    with pytest.raises(KeyError):
        runs(double("example double(1) == 2"))


def test_memory_error_is_not_caught_by_the_engine(monkeypatch):
    # Decision 0008, 3.4: MemoryError keeps the behaviour of `nex run` (it reaches the internal error).
    def exhausted(self, function, arguments, site):
        raise MemoryError

    monkeypatch.setattr(interpreter.Interpreter, "_invoke", exhausted)
    with pytest.raises(MemoryError):
        runs(double("example double(1) == 2"))


def test_running_main_is_unchanged():
    text = double() + "\nfn main() -> Void {\n    print(double(21))\n}\n"
    analysis = analyze(Source("t.nex", text))
    output = []
    interpreter.run(analysis.checked, output.append)
    assert output == ["42\n"]


# The API: nexora.api.test_source

from nexora import api, cli, schemas, tooling  # noqa: E402

TEST_SCHEMA = schemas.all_schemas()["nexora-test.schema.json"]
DECISION = ROOT / "docs" / "decisions" / "0008-ejemplos-y-nex-test.md"


def validate(document: dict) -> dict:
    import jsonschema

    jsonschema.validate(document, TEST_SCHEMA)
    return document


def test_api_and_schema_for_a_passing_file():                                           # [1] [30]
    document = validate(api.test_source(double("example double(2) == 4"), "double.nex"))
    assert (document["schema"], document["ok"], document["status"]) == ("nexora.test/1", True, "passed")
    assert document["summary"] == {"total": 1, "passed": 1, "failed": 0, "error": 0}
    (example,) = document["examples"]
    assert example["values"] == [{"call": "double(2)", "span": {"line": 2, "column": 13, "end_line": 2, "end_column": 22},
                                  "type": "Int", "status": "returned", "value": "4"}]


def test_api_failed_example_has_e4004_with_values_and_reason():                         # [2] [9]
    document = validate(api.test_source(double('example double(2) == 5, "Two doubled"')))
    (example,) = document["examples"]
    assert (document["status"], example["status"], example["message"]) == ("failed", "failed", "Two doubled")
    diagnostic = example["diagnostic"]
    assert (diagnostic["code"], diagnostic["category"], diagnostic["label"]) == (
        "E4004", "test", "This example of 'double' is false")
    assert diagnostic["notes"] == ["double(2) returned 4", "Reason: Two doubled"]


def test_api_error_keeps_the_original_code_and_adds_the_note_last():                    # [12]
    document = validate(api.test_source(double("example double(-1) == -2", contracts=("requires n >= 0",))))
    (example,) = document["examples"]
    assert (example["status"], example["diagnostic"]["code"], example["diagnostic"]["category"]) == (
        "error", "E4001", "contract")
    assert example["diagnostic"]["notes"][-1] == "While evaluating example 1 of 'double', at line 3."
    assert example["values"][0]["status"] == "stopped" and example["values"][0]["value"] is None


def test_api_mixed_results_are_all_evaluated_in_order():                                # [18]
    text = double("example double(2) == 5", "example double(2) == 4", "example double(-1) == -2",
                  contracts=("requires n >= 0",))
    document = validate(api.test_source(text))
    assert [e["status"] for e in document["examples"]] == ["failed", "passed", "error"]
    assert [e["index"] for e in document["examples"]] == [1, 2, 3]
    assert document["summary"] == {"total": 3, "passed": 1, "failed": 1, "error": 1}
    assert document["status"] == "failed"


def test_api_not_evaluated_calls():                                                     # [20] [35]
    short = validate(api.test_source(double("example double(1) == 3 and double(2) == 4")))["examples"][0]
    assert [v["call"] for v in short["values"]] == ["double(1)"]
    assert [(n["call"], n["reason"]) for n in short["not_evaluated"]] == [("double(2)", "short_circuit")]
    stopped = validate(api.test_source(double("example double(double(-1)) == 4",
                                              contracts=("requires n >= 0",))))["examples"][0]
    assert [(v["call"], v["status"]) for v in stopped["values"]] == [("double(-1)", "stopped")]
    assert [(n["call"], n["reason"]) for n in stopped["not_evaluated"]] == [("double(double(-1))", "stopped_before")]


def test_api_output_is_kept_per_example():                                              # [21]
    text = 'fn shout(n: Int) -> Int {\n    example shout(1) == 1\n    print("hi")\n    return n\n}\n'
    assert validate(api.test_source(text))["examples"][0]["output"] == "hi\n"


def test_api_filter():                                                                  # [22]
    text = (double("example double(2) == 4", contracts=("requires n >= 0",))
            + "\nfn triple(n: Int) -> Int {\n    example triple(-1) == -2\n    return double(n) + n\n}\n")
    document = validate(api.test_source(text, function="triple"))
    assert document["filter"] == {"function": "triple"}
    (example,) = document["examples"]
    # Only the examples of triple, but the requires of double, which triple calls, is still checked.
    assert (example["function"], example["status"], example["diagnostic"]["code"]) == ("triple", "error", "E4001")


def test_api_unknown_function_raises_tooling_error():                                   # [23]
    with pytest.raises(tooling.ToolingError) as raised:
        api.test_source(double("example double(2) == 4"), "d.nex", function="dobule")
    assert raised.value.code == "unknown_function"
    assert str(raised.value) == "d.nex has no function named 'dobule'. Did you mean 'double'?"


def test_api_no_examples_and_not_run():                                                 # [24] [25] [26]
    empty = validate(api.test_source(double()))
    assert (empty["status"], empty["summary"]["total"], empty["examples"]) == ("no_examples", 0, [])
    helper = validate(api.test_source(double("example double(2) == 4") + "\nfn helper(n: Int) -> Int {\n    return n\n}\n",
                                      function="helper"))
    assert (helper["status"], helper["examples"]) == ("no_examples", [])
    broken = validate(api.test_source(double("example 2 + 2 == 4"), function="nope"))
    assert (broken["ok"], broken["status"], broken["summary"], broken["examples"]) == (False, "not_run", None, None)
    assert [d["code"] for d in broken["diagnostics"]] == ["E2020"]


def test_api_does_not_require_main_and_never_runs_it():                                 # [28] [29]
    with_main = double("example double(2) == 4") + '\nfn main() -> Void {\n    print("main ran")\n}\n'
    document = validate(api.test_source(with_main))
    assert document["status"] == "passed" and document["examples"][0]["output"] == ""


def test_the_documents_of_the_decision_are_the_real_output():                           # [30]
    import re

    text = DECISION.read_text(encoding="utf-8")
    section = text[text.index("#### 6.4"):text.index("### 7. API de Python")]
    blocks = re.findall(r"```(text|json)\n(.*?)```", section, re.S)
    programs = [body for kind, body in blocks if kind == "text"]
    documents = [json.loads(body) for kind, body in blocks if kind == "json"]
    assert len(programs) == 5 and len(documents) == 7

    def source_of(listing: str) -> str:
        return "\n".join(re.sub(r"^\d+ {1,2}", "", line) for line in listing.rstrip("\n").split("\n")) + "\n"

    for program, expected in zip(programs, documents[:5], strict=True):
        actual = validate(api.test_source(source_of(program), "double.nex"))
        assert {**actual, "nexora_version": None} == {**expected, "nexora_version": None}

    # The two fragments: one example result each, inside double.nex with the requires of line 2.
    for fragment in documents[5:]:
        listing = ('fn double(n: Int) -> Int {\n    requires n >= 0, "Only natural numbers"\n'
                   f"    example {fragment['expression']}\n    return n * 2\n}}\n")
        (actual,) = api.test_source(listing, "double.nex")["examples"]
        assert actual == fragment


# The command line: nex test

def nex(*arguments: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "nexora", *arguments], capture_output=True, encoding="utf-8", cwd=cwd)


@pytest.fixture
def files(tmp_path):
    def write(name: str, text: str) -> str:
        (tmp_path / name).write_text(text, encoding="utf-8")
        return name
    write.dir = tmp_path
    return write


def test_cli_passing(files):                                                            # [1]
    name = files("ok.nex", double("example double(2) == 4", "example double(0) == 0"))
    result = nex("test", name, cwd=files.dir)
    assert result.returncode == 0 and result.stderr == ""
    assert result.stdout == "ok.nex: 2 examples in 1 function\n  double   2 passed\n✓ 2 examples passed: ok.nex\n"


def test_cli_failing_text_report(files):                                                # [2] [12] [18] [21]
    text = double('example double(2) == 5, "Two doubled"', "example double(2) == 4", "example double(-1) == -2",
                  contracts=("requires n >= 0",), body='print("n is " + to_text(n))\n    return n * 2')
    result = nex("test", files("bad.nex", text), cwd=files.dir)
    assert result.returncode == 6
    assert result.stdout == "bad.nex: 3 examples in 1 function\n  double   1 passed, 1 failed, 1 error\n"
    assert "test error[E4004]: Example failed" in result.stderr
    assert "= note: double(2) returned 4\n  = note: Reason: Two doubled" in result.stderr
    assert "contract error[E4001]: Precondition violated" in result.stderr
    assert "= note: While evaluating example 3 of 'double', at line 5." in result.stderr
    assert "output of example 1 of 'double':\n    n is 2\n" in result.stderr
    assert "output of example 2" not in result.stderr          # it passed: its output is not shown
    assert result.stderr.endswith("error: bad.nex: 2 of 3 examples did not pass (1 failed, 1 error)\n")


def test_cli_json_is_one_valid_document(files):                                         # [30]
    result = nex("test", files("bad.nex", double("example double(2) == 5")), "--format", "json", cwd=files.dir)
    assert result.returncode == 6 and result.stderr == ""
    document = validate(json.loads(result.stdout))
    assert document["status"] == "failed"


def test_cli_static_errors(files):                                                      # [3] [26]
    name = files("broken.nex", double("example 2 + 2 == 4"))
    result = nex("test", name, cwd=files.dir)
    assert result.returncode == 1 and result.stdout == ""
    assert "semantic error[E2020]: Example without its function" in result.stderr
    assert result.stderr.endswith("error: broken.nex: not tested because of 1 error\n")
    as_json = nex("test", name, "--format", "json", "--function", "nope", cwd=files.dir)
    assert as_json.returncode == 1
    assert validate(json.loads(as_json.stdout))["status"] == "not_run"
    check = nex("check", name, cwd=files.dir)
    assert check.returncode == 1 and "E2020" in check.stderr


def test_cli_unreadable_file(files):                                                    # [27]
    text = nex("test", "missing.nex", cwd=files.dir)
    assert text.returncode == 4 and "E0001" in text.stderr and text.stdout == ""
    as_json = nex("test", "missing.nex", "--format", "json", cwd=files.dir)
    document = validate(json.loads(as_json.stdout))
    assert as_json.returncode == 4
    assert (document["status"], document["ok"], document["diagnostics"][0]["code"]) == ("not_run", False, "E0001")


def test_cli_unknown_function_is_a_usage_error_without_document(files):                 # [23]
    name = files("ok.nex", double("example double(2) == 4"))
    for extra in ((), ("--format", "json")):
        result = nex("test", name, "--function", "dobule", *extra, cwd=files.dir)
        assert result.returncode == 2 and result.stdout == ""
        assert result.stderr == "error: ok.nex has no function named 'dobule'. Did you mean 'double'?\n"


def test_cli_filter_and_no_examples(files):                                             # [22] [24] [25]
    text = double("example double(2) == 4") + "\nfn helper(n: Int) -> Int {\n    return n\n}\n"
    name = files("lib.nex", text)
    only = nex("test", name, "--function", "double", cwd=files.dir)
    assert only.returncode == 0 and only.stdout.startswith("lib.nex: 1 example of 'double'\n")
    helper = nex("test", name, "--function", "helper", cwd=files.dir)
    assert (helper.returncode, helper.stdout, helper.stderr) == (
        6, "lib.nex: no examples to run\n", "error: lib.nex: nothing was tested\n")
    none = nex("test", files("none.nex", double()), cwd=files.dir)
    assert (none.returncode, none.stdout) == (6, "none.nex: no examples to run\n")


def test_cli_without_main_and_with_main(files):                                         # [28] [29]
    library = files("lib.nex", double("example double(2) == 4"))
    assert nex("test", library, cwd=files.dir).returncode == 0
    assert "E2001" in nex("check", library, cwd=files.dir).stderr
    program = files("prog.nex", double("example double(2) == 4") + '\nfn main() -> Void {\n    print("main ran")\n}\n')
    result = nex("test", program, cwd=files.dir)
    assert result.returncode == 0 and "main ran" not in result.stdout + result.stderr


def test_cli_analysis_commands_do_not_evaluate_examples(files):                        # [33]
    text = ("fn boom(n: Int) -> Int {\n    print(\"evaluated!\")\n    return n / 0\n}\n\n"
            + double("example double(boom(1)) == 0") + '\nfn main() -> Void {\n    print("main")\n}\n')
    name = files("quiet.nex", text)
    for command in (("check",), ("inspect",), ("context",), ("symbols",)):
        result = nex(*command, name, cwd=files.dir)
        assert result.returncode == 0 and result.stderr == "", command
        # Had boom run, print would have written this line. (inspect shows the literal, quoted, in JSON.)
        assert "evaluated!" not in (result.stdout + result.stderr).splitlines(), command


def in_process(monkeypatch, capsys, failure, *arguments):
    """Runs `nex test` in this process with the engine replaced by one that raises `failure`."""
    def broken(*_):
        raise failure

    monkeypatch.setattr(api, "run_example", broken)
    code = cli.main(["test", *arguments])
    return code, capsys.readouterr()


def test_cli_internal_error_writes_no_report(monkeypatch, capsys, files):              # [31]
    name = str(files.dir / files("ok.nex", double("example double(2) == 4")))
    for extra in ((), ("--format", "json")):
        code, captured = in_process(monkeypatch, capsys, KeyError("a bug"), name, *extra)
        assert code == 70 and captured.out == ""
        assert "internal error: NEXORA hit an unexpected problem" in captured.err


def test_cli_internal_error_in_a_later_example_writes_no_partial_report(monkeypatch, capsys, files):  # [31]
    # The first example is evaluated for real and passes; the defect appears during the second one.
    original = api.run_example
    evaluated = []

    def second_breaks(*arguments):
        evaluated.append(arguments)
        if len(evaluated) == 2:
            raise KeyError("a bug")
        return original(*arguments)

    monkeypatch.setattr(api, "run_example", second_breaks)
    name = str(files.dir / files("ok.nex", double("example double(2) == 4", "example double(3) == 6")))
    for extra in ((), ("--format", "json")):
        evaluated.clear()
        code = cli.main(["test", name, *extra])
        captured = capsys.readouterr()
        assert (code, captured.out, len(evaluated)) == (70, "", 2), extra
        assert "internal error: NEXORA hit an unexpected problem" in captured.err
        assert "passed" not in captured.err


def test_cli_memory_error_keeps_the_inherited_code_70(monkeypatch, capsys, files):
    name = str(files.dir / files("ok.nex", double("example double(2) == 4")))
    code, captured = in_process(monkeypatch, capsys, MemoryError(), name, "--format", "json")
    assert code == 70 and captured.out == ""


def test_cli_ctrl_c_writes_no_report(monkeypatch, capsys, files):                       # [37]
    name = str(files.dir / files("ok.nex", double("example double(2) == 4")))
    code, captured = in_process(monkeypatch, capsys, KeyboardInterrupt(), name)
    assert code == 130 and captured.out == ""


def test_cli_recursion_error_is_e3004_not_70(monkeypatch, capsys, files):              # [36]
    original = interpreter.Interpreter._invoke
    seen = []

    def invoke(self, function, arguments, site):
        seen.append(arguments)
        if len(seen) == 1:
            raise RecursionError
        return original(self, function, arguments, site)

    monkeypatch.setattr(interpreter.Interpreter, "_invoke", invoke)
    name = str(files.dir / files("ok.nex", double("example double(1) == 2", "example double(2) == 4")))
    code = cli.main(["test", name, "--format", "json"])
    document = validate(json.loads(capsys.readouterr().out))
    assert code == 6
    assert [(e["status"], e["diagnostic"] and e["diagnostic"]["code"]) for e in document["examples"]] == [
        ("error", "E3004"), ("passed", None)]

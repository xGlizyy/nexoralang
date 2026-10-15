"""A program that runs out of memory while it runs: diagnostic E3007 (decision 0009).

The numbers in brackets are the regression tests of the decision. MemoryError is raised on purpose
by replacing an internal function, so no test exhausts real memory or depends on the machine.
"""

import copy
import gc
import json
import sys
import weakref

import pytest

from nexora import api, cli, interpreter, schemas
from nexora.checker import own_calls
from nexora.diagnostics import NexoraRuntimeError, Source
from nexora.interpreter import run_example
from nexora.pipeline import analyze

# grow(n) calls itself n times, printing on the way. The examples of grow(3) run out of memory
# three calls deep, so the error has a chain of calls; grow(1) does not.
GROW = ('fn grow(n: Int) -> Int {\n'
        '    example grow(3) == 3\n'
        '    example grow(1) == 1\n'
        '    print("grow " + to_text(n))\n'
        '    if n == 0 {\n        return 0\n    }\n'
        '    return grow(n - 1) + 1\n'
        '}\n')
# The same function, run by main: grow(3) runs out of memory after printing two lines.
PROGRAM = GROW + 'fn main() -> Void {\n    print("before")\n    print(grow(3))\n}\n'
LABEL = "The program needed more memory than is available."
HINT = "Reduce the size of values created by the program, especially values that grow with each function call."
MESSAGE = "The program needed more memory than this environment allows and was stopped."


def checked_grow():
    analysis = analyze(Source("grow.nex", GROW), require_main=False)
    assert analysis.ok, [(d.code, d.label) for d in analysis.diagnostics]
    return analysis.checked


def run_all(checked):
    """Every example of grow, each evaluated by the engine in its own interpreter."""
    return [run_example(checked, example, own_calls(example, "grow"))
            for example in checked.functions["grow"].examples]


def exhaust_three_calls_deep(monkeypatch, interpreters=None, failure=MemoryError):
    """`failure` (MemoryError) when the interpreter enters a third nested call. `interpreters`, if
    given, collects a weak reference to each interpreter that raised it."""
    original = interpreter.Interpreter._invoke

    def invoke(self, function, arguments, site):
        if len(self._stack) == 2:
            if interpreters is not None:
                interpreters.append(weakref.ref(self))
            raise failure
        return original(self, function, arguments, site)

    monkeypatch.setattr(interpreter.Interpreter, "_invoke", invoke)


# State and continuation (decision 0009, section 3): written first

def test_e3007_keeps_neither_the_memory_error_nor_its_traceback(monkeypatch):          # [6]
    exhaust_three_calls_deep(monkeypatch)
    analysis = analyze(Source("grow.nex", PROGRAM))
    try:
        interpreter.run(analysis.checked, lambda text: None)
    except NexoraRuntimeError as error:
        assert error.diagnostic.code == "E3007"
        assert error.__context__ is None and error.__cause__ is None
    else:
        raise AssertionError("no NexoraRuntimeError")


def test_the_interpreter_that_ran_out_of_memory_is_released(monkeypatch):              # [7]
    interpreters = []
    exhaust_three_calls_deep(monkeypatch, interpreters)
    checked = checked_grow()
    (example, _) = checked.functions["grow"].examples
    run = run_example(checked, example, own_calls(example, "grow"))
    assert run.error.code == "E3007"
    gc.collect()
    assert len(interpreters) == 1 and interpreters[0]() is None


def test_the_recursion_limit_of_python_is_the_same_after_the_example(monkeypatch):     # [8]
    exhaust_three_calls_deep(monkeypatch)
    before = sys.getrecursionlimit()
    (failed, _) = run_all(checked_grow())
    assert failed.error.code == "E3007"
    assert sys.getrecursionlimit() == before


def test_the_next_example_is_evaluated_on_its_own(monkeypatch):                        # [9]
    exhaust_three_calls_deep(monkeypatch)
    checked = checked_grow()
    unchanged = copy.deepcopy(checked)
    failed, passed = run_all(checked)
    assert failed.error.code == "E3007" and failed.error.notes        # it has a chain of calls
    assert failed.output == "grow 3\ngrow 2\n"
    # The second example: its own output, its own calls, no chain of calls and no error left behind.
    assert (passed.value, passed.error) == (True, None)
    assert passed.output == "grow 1\ngrow 0\n"
    assert [(r.node.callee, r.status, r.value) for r in passed.invoked] == [("grow", "returned", 1)]
    assert checked == unchanged


# Scope (decision 0009, section 1)

def run_program(write=lambda text: None):
    interpreter.run(analyze(Source("grow.nex", PROGRAM)).checked, write)


def test_memory_error_in_a_call_of_the_program_is_e3007(monkeypatch):                   # [1]
    exhaust_three_calls_deep(monkeypatch)
    with pytest.raises(NexoraRuntimeError) as raised:
        run_program()
    diagnostic = raised.value.diagnostic
    assert (diagnostic.code, diagnostic.message, diagnostic.category) == ("E3007", "Out of memory", "runtime")
    assert (diagnostic.label, diagnostic.hint, diagnostic.span) == (LABEL, HINT, None)
    assert diagnostic.notes == ("In 'grow', called at line 12, column 11.",)


def test_memory_error_in_the_write_of_print_is_e3007():                                 # [2]
    def write(text):
        raise MemoryError

    with pytest.raises(NexoraRuntimeError) as raised:
        run_program(write)
    assert raised.value.diagnostic.code == "E3007"


def in_process(capsys, *arguments):
    code = cli.main(list(arguments))
    return code, capsys.readouterr()


def test_memory_error_while_analysing_is_not_e3007(monkeypatch, capsys, tmp_path):       # [3]
    def exhausted(*_, **__):
        raise MemoryError

    monkeypatch.setattr(cli, "analyze", exhausted)
    monkeypatch.setattr(api, "analyze", exhausted)
    path = str(tmp_path / "grow.nex")
    (tmp_path / "grow.nex").write_text(PROGRAM, encoding="utf-8")
    for command in ("run", "test"):
        code, captured = in_process(capsys, command, path)
        assert code == 70 and "E3007" not in captured.out + captured.err, command
    with pytest.raises(MemoryError):
        api.test_source(PROGRAM)


def test_memory_error_while_building_the_report_is_not_e3007(monkeypatch, capsys, tmp_path):  # [4]
    def exhausted(report):
        raise MemoryError

    monkeypatch.setattr(api, "test_document", exhausted)
    (tmp_path / "grow.nex").write_text(GROW, encoding="utf-8")
    code, captured = in_process(capsys, "test", str(tmp_path / "grow.nex"), "--format", "json")
    assert (code, captured.out) == (70, "")


@pytest.mark.parametrize("module, name", [(cli, "render"), (api, "summary_of")])
@pytest.mark.parametrize("failure", [MemoryError(), KeyError("a bug")], ids=["MemoryError", "KeyError"])
def test_a_failure_while_building_the_text_report_writes_no_partial_report(monkeypatch, capsys, tmp_path,
                                                                           module, name, failure):  # [4]
    # Like the JSON document, the text report is built whole before it is written. A failure while
    # rendering a diagnostic, or while counting the summary, is an internal error (70), and stdout
    # stays empty: no summary that could be taken for the complete report.
    def broken(*_):
        raise failure

    exhaust_three_calls_deep(monkeypatch)
    monkeypatch.setattr(module, name, broken)
    (tmp_path / "grow.nex").write_text(GROW, encoding="utf-8")
    code, captured = in_process(capsys, "test", str(tmp_path / "grow.nex"))
    assert (code, captured.out) == (70, "")
    assert captured.err.startswith(f"internal error: NEXORA hit an unexpected problem ({type(failure).__name__}")
    # No verdict, no diagnostic of an example, and the failure is not taken for the program's E3007.
    assert "passed" not in captured.err and "did not pass" not in captured.err
    assert "error[" not in captured.err and "E3007" not in captured.err


def test_the_text_report_is_unchanged_when_nothing_fails(monkeypatch, capsys, tmp_path):
    # The same report as before it was built whole: summary on stdout, diagnostics and verdict on stderr.
    exhaust_three_calls_deep(monkeypatch)
    path = tmp_path / "grow.nex"
    path.write_text(GROW, encoding="utf-8")
    code, captured = in_process(capsys, "test", str(path))
    assert code == 6
    assert captured.out == f"{path}: 2 examples in 1 function\n  grow   1 passed, 1 error\n"
    assert captured.err.startswith("\nruntime error[E3007]: Out of memory\n")
    assert "\noutput of example 1 of 'grow':\n    grow 3\n    grow 2\n" in captured.err
    assert captured.err.endswith(f"\nerror: {path}: 1 of 2 examples did not pass (0 failed, 1 error)\n")


def test_memory_error_while_converting_is_not_converted(monkeypatch, capsys, tmp_path):  # [5]
    exhaust_three_calls_deep(monkeypatch)
    original = interpreter.Interpreter._fail

    def fail(self, code, *arguments, **options):
        if code == "E3007":
            raise MemoryError
        return original(self, code, *arguments, **options)

    monkeypatch.setattr(interpreter.Interpreter, "_fail", fail)
    result = api.run_source(PROGRAM)
    assert (result["status"], result["diagnostics"], result["message"]) == ("memory_limit", [], MESSAGE)
    (tmp_path / "grow.nex").write_text(PROGRAM, encoding="utf-8")
    code, _ = in_process(capsys, "run", str(tmp_path / "grow.nex"))
    assert code == 70
    with pytest.raises(MemoryError):
        api.test_source(GROW)


# The contract of each interface (decision 0009, section 4)

def validate(document: dict, schema: str) -> dict:
    import jsonschema

    jsonschema.validate(document, schemas.all_schemas()[schema])
    return document


@pytest.fixture
def grow_file(tmp_path, monkeypatch):
    exhaust_three_calls_deep(monkeypatch)

    def write(text):
        path = tmp_path / "grow.nex"
        path.write_text(text, encoding="utf-8")
        return str(path)

    return write


def test_cli_run_gives_3_with_e3007(capsys, grow_file):                                  # [10]
    code, captured = in_process(capsys, "run", grow_file(PROGRAM))
    assert code == 3 and captured.out == "before\ngrow 3\n"
    assert "runtime error[E3007]: Out of memory" in captured.err
    assert "the program stopped because of a runtime error" in captured.err
    assert "internal error" not in captured.err


def test_cli_run_json_writes_the_diagnostics_document(capsys, grow_file):                # [11]
    code, captured = in_process(capsys, "run", grow_file(PROGRAM), "--format", "json")
    document = validate(json.loads(captured.err), "nexora-diagnostics.schema.json")
    assert code == 3 and document["schema"] == "nexora.diagnostics/1"
    assert [diagnostic["code"] for diagnostic in document["diagnostics"]] == ["E3007"]


def test_cli_test_gives_6_with_the_complete_report(capsys, grow_file):                   # [12]
    path = grow_file(GROW)
    code, captured = in_process(capsys, "test", path)
    assert code == 6 and "E3007" in captured.out + captured.err and "internal error" not in captured.err
    code, captured = in_process(capsys, "test", path, "--format", "json")
    document = validate(json.loads(captured.out), "nexora-test.schema.json")
    assert (code, document["status"]) == (6, "failed")
    assert document["summary"] == {"total": 2, "passed": 1, "failed": 0, "error": 1}
    failed, passed = document["examples"]
    assert (failed["status"], failed["diagnostic"]["code"], passed["status"]) == ("error", "E3007", "passed")
    assert failed["diagnostic"]["notes"][-1] == "While evaluating example 1 of 'grow', at line 2."
    assert [(value["call"], value["status"]) for value in failed["values"]] == [("grow(3)", "stopped")]
    assert failed["output"] == "grow 3\ngrow 2\n"


def test_run_source_keeps_memory_limit_and_adds_the_diagnostic(monkeypatch):            # [13]
    exhaust_three_calls_deep(monkeypatch)
    result = validate(api.run_source(PROGRAM), "nexora-result.schema.json")
    assert (result["status"], result["message"], result["output"]) == ("memory_limit", MESSAGE, "before\ngrow 3\n")
    assert [diagnostic["code"] for diagnostic in result["diagnostics"]] == ["E3007"]


def test_test_source_returns_the_document(monkeypatch):                                 # [14]
    exhaust_three_calls_deep(monkeypatch)
    document = validate(api.test_source(GROW), "nexora-test.schema.json")
    assert document["status"] == "failed"
    assert [example["status"] for example in document["examples"]] == ["error", "passed"]


# A MemoryError of the program against a real internal error (decision 0009)

def test_a_key_error_at_the_same_point_is_still_an_internal_error(monkeypatch, capsys, tmp_path):  # [16]
    exhaust_three_calls_deep(monkeypatch, failure=KeyError("a bug"))
    (tmp_path / "grow.nex").write_text(PROGRAM, encoding="utf-8")
    for command in ("run", "test"):
        code, captured = in_process(capsys, command, str(tmp_path / "grow.nex"))
        assert code == 70 and "This is a bug in NEXORA" in captured.err, command
        assert "E3007" not in captured.out + captured.err, command
    code, captured = in_process(capsys, "test", str(tmp_path / "grow.nex"), "--format", "json")
    assert (code, captured.out) == (70, "")
    with pytest.raises(KeyError):
        api.run_source(PROGRAM)
    with pytest.raises(KeyError):
        api.test_source(GROW)

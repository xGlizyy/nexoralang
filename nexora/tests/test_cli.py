import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nexora import __version__, cli

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

HELLO = 'fn main() {\n    let message = "Hello from NEXORA"\n    print(message)\n}\n'


@pytest.fixture
def program(tmp_path):
    """Writes a program to a temporary .nex file and returns its path."""
    def write(text: str, name: str = "program.nex") -> str:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return str(path)
    return write


def nex(*arguments: str) -> subprocess.CompletedProcess:
    """Runs the real command in a separate process, as a user would."""
    return subprocess.run(
        [sys.executable, "-m", "nexora", *arguments],
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
    )


# Version and help

def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out == f"NEXORA {__version__}\n"


def test_version_matches_the_installed_package():
    from importlib.metadata import version
    assert version("nexora-lang") == __version__


def test_help(capsys):
    assert cli.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "run" in output and "check" in output and "exit codes" in output


@pytest.mark.parametrize("command", ["run", "check"])
def test_command_help(command, capsys):
    assert cli.main([command, "--help"]) == 0
    assert "file" in capsys.readouterr().out


def test_no_command_is_a_usage_error(capsys):
    assert cli.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "usage: nex" in captured.err


@pytest.mark.parametrize("arguments", [["bogus"], ["run"], ["check"], ["run", "a.nex", "--nope"], ["--nope"]])
def test_wrong_usage(arguments, capsys):
    assert cli.main(arguments) == 2
    assert "usage: nex" in capsys.readouterr().err


# run

def test_run_prints_the_program_output(program, capsys):
    assert cli.main(["run", program(HELLO)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Hello from NEXORA\n"
    assert captured.err == ""


def test_run_output_budget_stops_with_a_clear_diagnostic(program, capsys):
    path = program('fn main() {\n    print("1234567890")\n    print("never")\n}\n')
    assert cli.main(["run", path, "--max-output", "5"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "12345"
    assert "output limit exceeded (5)" in captured.err
    assert "never" not in captured.out


def test_run_output_budget_does_not_split_a_utf8_character(program, capsys):
    path = program('fn main() { print("éé") }\n')
    assert cli.main(["run", path, "--max-output", "3"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "é"
    assert "output limit exceeded (3)" in captured.err


def test_run_json_reports_a_resource_limit_as_a_diagnostic(program, capsys):
    path = program('fn main() { print("abcdef") }\n')
    assert cli.main(["run", path, "--max-output", "2", "--format", "json"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "ab"
    document = json.loads(captured.err)
    assert document["schema"] == "nexora.diagnostics/1"
    (diagnostic,) = document["diagnostics"]
    assert (diagnostic["category"], diagnostic["code"], diagnostic["label"]) == (
        "runtime", "E3015", "output limit exceeded (2)",
    )


def test_run_source_budget_refuses_large_input(program, capsys):
    assert cli.main(["run", program(HELLO), "--max-source", "1"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "runtime error[E3015]: Resource limit exceeded" in captured.err
    assert "--max-source limit exceeded (1)" in captured.err


def test_run_text_budget_stops_with_runtime_diagnostic(program, capsys):
    source = 'fn main() {\n    let a = "123456"\n    print(a + a)\n}\n'
    assert cli.main(["run", program(source), "--max-text", "8"]) == 3
    assert "E3006" in capsys.readouterr().err


@pytest.mark.parametrize(
    "option", ["--timeout", "--max-output", "--max-text", "--max-source", "--max-input", "--max-memory"],
)
def test_run_limits_must_be_positive(program, capsys, option):
    assert cli.main(["run", program(HELLO), option, "0"]) == 2
    assert f"{option} must be greater than zero" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["nan", "inf"])
def test_run_timeout_must_be_finite(program, capsys, value):
    assert cli.main(["run", program(HELLO), "--timeout", value]) == 2
    assert "--timeout must be greater than zero" in capsys.readouterr().err


def test_run_memory_budget_is_refused_where_rlimit_as_is_not_enforced(program, capsys):
    if sys.platform not in ("darwin", "win32"):
        pytest.skip("this platform enforces RLIMIT_AS")
    assert cli.main(["run", program(HELLO), "--max-memory", "536870912"]) == 2
    message = capsys.readouterr().err
    assert "--max-memory is enforced only on Linux" in message


@pytest.mark.skipif(os.name != "nt", reason="POSIX platforms support the CLI interval timer")
def test_run_timeout_is_refused_on_windows(program, capsys):
    assert cli.main(["run", program(HELLO), "--timeout", "1"]) == 2
    assert "--timeout requires a POSIX platform" in capsys.readouterr().err


def test_run_source_limit_accepts_a_file_at_the_limit(program, capsys):
    path = program(HELLO)
    assert cli.main(["run", path, "--max-source", str(os.path.getsize(path))]) == 0
    assert capsys.readouterr().out == "Hello from NEXORA\n"


def test_run_source_limit_applies_to_imported_modules(program, tmp_path, capsys):
    path = program('import "large.nex"\nfn main() { print(large.value()) }\n')
    module = tmp_path / "large.nex"
    module.write_text("// " + ("x" * 100) + "\npub fn value() gives Int { return 1 }\n", encoding="utf-8")
    assert cli.main(["run", path, "--max-source", "80"]) == 3
    message = capsys.readouterr().err
    assert "runtime error[E3015]: Resource limit exceeded" in message
    assert "--max-source limit exceeded (80)" in message
    assert "large.nex" in message


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS is enforced on Linux")
def test_run_memory_limit_becomes_a_runtime_diagnostic(program):
    source = '''fn main() {
    var text = "x"
    var count = 1
    while count < 30
        shrinks 30 - count, "The text doubles each turn"
    {
        text = text + text
        count = count + 1
    }
    print("done")
}
'''
    result = nex("run", program(source), "--max-memory", "268435456", "--format", "json")
    assert result.returncode == 3
    document = json.loads(result.stderr)
    (diagnostic,) = document["diagnostics"]
    assert diagnostic["code"] == "E3007"
    assert "memory" in diagnostic["label"].lower()


@pytest.mark.parametrize(
    "source, arguments, input_text",
    [
        ('fn main() { print("abc") }\n', [], ""),
        ('fn main() { print(input()) }\n', [], "x" * 100_000),
        ('fn main() { print(List.get(args(), 0)) }\n', ["abc"], ""),
    ],
    ids=["literal", "bounded-input", "argument"],
)
def test_run_text_limit_applies_to_literals_input_and_arguments(
    program, monkeypatch, capsys, source, arguments, input_text,
):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(input_text.encode()), encoding="utf-8"))
    assert cli.main(["run", program(source), "--max-text", "2", "--", *arguments]) == 3
    assert "E3006" in capsys.readouterr().err


def test_run_text_limit_bounds_file_reads(program, tmp_path, capsys):
    data_path = tmp_path / "data.txt"
    data_path.write_text("x" * 100_000, encoding="utf-8")
    declared_path = str(data_path).replace("\\", "\\\\")
    path = program(f'uses read "{declared_path}"\nfn main() {{ print(read_file("{declared_path}")) }}\n')
    assert cli.main(["run", path, "--max-text", "8", "--allow-read", str(data_path)]) == 3
    assert "E3006" in capsys.readouterr().err


def test_run_input_budget_stops_before_reading_past_its_byte_limit(program, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"abc\n"), encoding="utf-8"))
    source = 'fn main() {\n    print(input())\n}\n'
    assert cli.main(["run", program(source), "--max-input", "2"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "input limit exceeded (2)" in captured.err


def test_run_input_budget_counts_all_lines_and_accepts_the_exact_limit(program, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"a\nb\n"), encoding="utf-8"))
    source = 'fn main() {\n    print(input())\n    print(input())\n}\n'
    assert cli.main(["run", program(source), "--max-input", "4"]) == 0
    assert capsys.readouterr().out == "a\nb\n"


def test_run_stops_with_e3009_when_the_standard_input_has_ended(program, monkeypatch, capsys):
    # Without any limit the command used to give the program an empty line instead of stopping (section 8.3).
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"a\n"), encoding="utf-8"))
    source = 'fn main() {\n    print(input())\n    print(input())\n}\n'
    assert cli.main(["run", program(source)]) == 3
    captured = capsys.readouterr()
    assert captured.out == "a\n"
    assert "E3009" in captured.err


@pytest.mark.skipif(os.name == "nt", reason="CLI wall-clock cancellation uses POSIX interval timers")
def test_run_timeout_stops_execution_with_a_clear_diagnostic(program, capsys):
    source = '''fn fib(n: Int) gives Int {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}
fn main() {
    print(fib(45))
}
'''
    assert cli.main(["run", program(source), "--timeout", "0.05"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "time limit exceeded (0.05)" in captured.err


@pytest.mark.skipif(os.name == "nt", reason="CLI wall-clock cancellation uses POSIX interval timers")
def test_run_timeout_cleans_up_an_active_process(program, tmp_path, capsys):
    executable = sys.executable.replace("\\", "\\\\")
    marker = (tmp_path / "child-finished").as_posix()
    child_code = f"import time; time.sleep(1); open({marker!r}, 'w').close()"
    parent_code = f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child_code!r}]).wait()"
    source = f'''uses process "{executable}"

fn main() {{
    print(Process.run("{executable}", ["-c", {json.dumps(parent_code)}]))
}}
'''
    path = program(source)
    assert cli.main(["run", path, "--allow-process", sys.executable, "--timeout", "0.1"]) == 3
    assert "time limit exceeded" in capsys.readouterr().err
    time.sleep(1.1)
    assert not (tmp_path / "child-finished").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups are used for child cleanup")
def test_process_run_cleans_up_descendants_after_command_returns(program, tmp_path, capsys):
    executable = sys.executable.replace("\\", "\\\\")
    marker = (tmp_path / "child-finished").as_posix()
    child_code = f"import time; time.sleep(1); open({marker!r}, 'w').close()"
    parent_code = f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child_code!r}])"
    source = f'''uses process "{executable}"

fn main() {{
    print(Process.run("{executable}", ["-c", {json.dumps(parent_code)}]))
}}
'''
    assert cli.main(["run", program(source), "--allow-process", sys.executable]) == 0
    assert capsys.readouterr().out == "\n"
    time.sleep(1.1)
    assert not (tmp_path / "child-finished").exists()


def test_run_missing_file(capsys):
    assert cli.main(["run", "does-not-exist.nex"]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error[E0001]: Cannot read file" in captured.err
    assert "does-not-exist.nex" in captured.err


def test_run_directory_instead_of_file(tmp_path, capsys):
    assert cli.main(["run", str(tmp_path)]) == 4
    assert "E0001" in capsys.readouterr().err


def test_run_file_that_is_not_utf8(tmp_path, capsys):
    path = tmp_path / "latin1.nex"
    path.write_bytes('fn main() {\n    print("año")\n}\n'.encode("latin-1"))
    assert cli.main(["run", str(path)]) == 4
    assert "E0002" in capsys.readouterr().err


def test_run_accepts_a_utf8_byte_order_mark_and_windows_line_endings(tmp_path, capsys):
    path = tmp_path / "bom.nex"
    path.write_bytes(b"\xef\xbb\xbf" + HELLO.replace("\n", "\r\n").encode("utf-8"))
    assert cli.main(["run", str(path)]) == 0
    assert capsys.readouterr().out == "Hello from NEXORA\n"


def test_run_invalid_program_does_not_execute_anything(program, capsys):
    path = program('fn main() {\n    print("must not appear")\n    let = 1\n}\n')
    assert cli.main(["run", path]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error[E1101]: Unexpected token" in captured.err
    assert f"{path}:3:9" in captured.err
    assert "not run because of 1 error" in captured.err


def test_run_semantic_error_does_not_execute_anything(program, capsys):
    path = program('fn main() {\n    print("must not appear")\n    print(missing)\n}\n')
    assert cli.main(["run", path]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error[E2005]: Unknown variable" in captured.err


def test_run_runtime_error(program, capsys):
    path = program('fn main() {\n    print("before")\n    print(1 / 0)\n    print("after")\n}\n')
    assert cli.main(["run", path]) == 3
    captured = capsys.readouterr()
    assert captured.out == "before\n"
    assert "error[E3001]: Division by zero" in captured.err
    assert f"{path}:3:15" in captured.err
    assert "Traceback" not in captured.err


# check

def test_check_valid_program(program, capsys):
    path = program(HELLO)
    assert cli.main(["check", path]) == 0
    captured = capsys.readouterr()
    assert captured.out == f"✓ Check passed: {path}\n"
    assert captured.err == ""


def test_check_does_not_run_the_program(program, capsys):
    # A valid program whose only observable behaviour is printing, plus a failure at run time.
    path = program('fn main() {\n    print("SIDE EFFECT")\n    print(1 / 0)\n}\n')
    assert cli.main(["check", path]) == 0
    captured = capsys.readouterr()
    assert "SIDE EFFECT" not in captured.out + captured.err
    assert "E3001" not in captured.err
    # The same file does print and fail when it is run.
    assert cli.main(["run", path]) == 3
    assert capsys.readouterr().out == "SIDE EFFECT\n"


def test_check_never_calls_the_interpreter(program, monkeypatch):
    def forbidden(*arguments):
        raise AssertionError("check must not execute the program")
    monkeypatch.setattr(cli, "run", forbidden)
    assert cli.main(["check", program(HELLO)]) == 0


def test_check_invalid_program(program, capsys):
    path = program('fn main() {\n    let x = 1 + "a"\n    print(y)\n}\n')
    assert cli.main(["check", path]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error[E2011]: Type mismatch" in captured.err
    assert "error[E2005]: Unknown variable" in captured.err
    assert "check failed with 2 errors" in captured.err


def test_check_missing_file(capsys):
    assert cli.main(["check", "does-not-exist.nex"]) == 4
    assert "E0001" in capsys.readouterr().err


def test_check_json_for_a_valid_program(program, capsys):
    path = program(HELLO)
    assert cli.main(["check", path, "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "schema": "nexora.diagnostics/1", "nexora_version": __version__, "file": path, "ok": True,
        "diagnostics": [],
    }
    assert captured.err == ""


def test_check_json_for_an_invalid_program(program, capsys):
    path = program("fn main() {\n    print(missing)\n}\n")
    assert cli.main(["check", path, "--format", "json"]) == 1
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["ok"] is False
    assert document["schema"] == "nexora.diagnostics/1"
    assert document["diagnostics"] == [{
        "severity": "error",
        "category": "semantic",
        "code": "E2005",
        "message": "Unknown variable",
        "label": "There is no variable named 'missing' here",
        "hint": "Declare it first with 'let'.",
        "notes": [],
        "file": path,
        "line": 2,
        "column": 11,
        "end_line": 2,
        "end_column": 18,
    }]
    assert captured.err == ""


def test_check_json_for_a_missing_file(capsys):
    assert cli.main(["check", "does-not-exist.nex", "--format", "json"]) == 4
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is False and document["diagnostics"][0]["code"] == "E0001"


# run: contracts and JSON errors

DIVIDE = (
    "fn divide(a: Float, b: Float) gives Float\n"
    "    needs b != 0.0\n"
    "{\n"
    "    return a / b\n"
    "}\n"
    "\n"
    "fn main() {\n"
    "    print(\"before\")\n"
    "    print(divide(1.0, 0.0))\n"
    "    print(\"after\")\n"
    "}\n"
)


def test_run_contract_violation_has_its_own_exit_code(program, capsys):
    path = program(DIVIDE)
    assert cli.main(["run", path]) == 5
    captured = capsys.readouterr()
    assert captured.out == "before\n"
    assert "contract error[E4001]: Precondition violated" in captured.err
    assert "the program stopped because a contract was broken" in captured.err


def test_check_accepts_a_program_whose_contract_fails_at_run_time(program, capsys):
    assert cli.main(["check", program(DIVIDE)]) == 0
    assert "before" not in capsys.readouterr().out


def test_run_json_reports_a_runtime_failure_on_standard_error(program, capsys):
    path = program(DIVIDE)
    assert cli.main(["run", path, "--format", "json"]) == 5
    captured = capsys.readouterr()
    assert captured.out == "before\n"
    document = json.loads(captured.err)
    assert document["schema"] == "nexora.diagnostics/1"
    assert document["ok"] is False
    (diagnostic,) = document["diagnostics"]
    assert (diagnostic["category"], diagnostic["code"], diagnostic["line"]) == ("contract", "E4001", 9)


def test_run_json_reports_static_errors_without_running(program, capsys):
    path = program('fn main() {\n    print("must not appear")\n    let x: Int = "a"\n}\n')
    assert cli.main(["run", path, "--format", "json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["diagnostics"][0]["category"] == "type"


def test_run_json_prints_nothing_extra_on_success(program, capsys):
    assert cli.main(["run", program(HELLO), "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("Hello from NEXORA\n", "")


# inspect

def test_inspect_prints_the_program_as_json(program, capsys):
    path = program(HELLO)
    assert cli.main(["inspect", path]) == 0
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert list(document) == ["schema", "nexora_version", "file", "ok", "diagnostics", "complete", "program"]
    assert (document["schema"], document["file"], document["ok"]) == ("nexora.inspect/3", path, True)
    assert document["complete"] is True
    assert document["program"]["kind"] == "Program"
    assert document["program"]["functions"][0]["name"] == "main"


def test_inspect_format_json_is_accepted_and_is_the_default(program, capsys):
    path = program(HELLO)
    cli.main(["inspect", path])
    default = capsys.readouterr().out
    cli.main(["inspect", path, "--format", "json"])
    assert capsys.readouterr().out == default


def test_inspect_does_not_run_the_program(program, capsys, monkeypatch):
    def forbidden(*arguments):
        raise AssertionError("inspect must not execute the program")
    monkeypatch.setattr(cli, "run", forbidden)
    path = program('fn main() {\n    print("SIDE EFFECT")\n    print(1 / 0)\n}\n')
    assert cli.main(["inspect", path]) == 0
    captured = capsys.readouterr()
    # The text only appears as data: the literal inside the tree. Nothing was printed by the program.
    assert json.loads(captured.out)["ok"] is True
    assert captured.out.count("SIDE EFFECT") == 1
    assert captured.err == ""


def test_inspect_with_type_errors_still_shows_the_tree(program, capsys):
    path = program('fn main() {\n    let x: Int = "a"\n}\n')
    assert cli.main(["inspect", path]) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is False
    assert [d["code"] for d in document["diagnostics"]] == ["E2011"]
    assert document["program"]["functions"][0]["body"]["statements"][0]["kind"] == "Let"


def test_inspect_with_syntax_errors_has_a_partial_tree(program, capsys):
    assert cli.main(["inspect", program("fn main() {\n    let = 1\n    print(2)\n}\n")]) == 1
    document = json.loads(capsys.readouterr().out)
    assert (document["ok"], document["complete"]) == (False, False)
    assert [d["category"] for d in document["diagnostics"]] == ["syntax"]
    # The statement with the error is left out; the one that parsed is there.
    statements = document["program"]["functions"][0]["body"]["statements"]
    assert [statement["kind"] for statement in statements] == ["ExprStatement"]


def test_inspect_with_lexical_errors_has_no_tree(program, capsys):
    assert cli.main(["inspect", program('fn main() {\n    print("open)\n}\n')]) == 1
    document = json.loads(capsys.readouterr().out)
    assert (document["complete"], document["program"]) == (False, None)
    assert document["diagnostics"][0]["category"] == "lexical"


def test_a_program_with_syntax_errors_is_never_run(program, capsys):
    # The partial tree is for tools only: what parsed must not be executed.
    assert cli.main(["run", program('fn main() {\n    print("before")\n    let = 1\n}\n')]) == 1
    assert capsys.readouterr().out == ""


def test_inspect_missing_file(capsys):
    assert cli.main(["inspect", "does-not-exist.nex"]) == 4
    document = json.loads(capsys.readouterr().out)
    assert document["program"] is None and document["diagnostics"][0]["code"] == "E0001"
    assert document["complete"] is False


def test_process_inspect_is_valid_json_for_every_example():
    for path in sorted(EXAMPLES.rglob("*.nex")):
        name = path.relative_to(EXAMPLES).as_posix()
        result = nex("inspect", f"examples/{name}")
        document = json.loads(result.stdout)
        assert document["schema"] == "nexora.inspect/3", name
        assert result.stderr == "", name
        # Inspecting never runs the program, so even the examples that fail at run time are 'ok'.
        assert result.returncode == (0 if document["ok"] else 1), name


# Defects in NEXORA itself are not presented as errors in the user's program.

def test_internal_error_is_reported_as_a_bug(program, monkeypatch, capsys):
    def broken(*arguments, **options):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "analyze", broken)
    monkeypatch.delenv("NEXORA_DEBUG", raising=False)
    assert cli.main(["run", program(HELLO)]) == 70
    error = capsys.readouterr().err
    assert "internal error" in error and "bug in NEXORA" in error and "Traceback" not in error


def test_internal_error_can_be_investigated(program, monkeypatch):
    def broken(*arguments, **options):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "analyze", broken)
    monkeypatch.setenv("NEXORA_DEBUG", "1")
    with pytest.raises(RuntimeError, match="boom"):
        cli.main(["run", program(HELLO)])


def test_interrupting_a_run_is_reported_without_a_traceback(program, monkeypatch, capsys):
    def interrupted(*arguments, **keywords):
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "run", interrupted)
    assert cli.main(["run", program(HELLO)]) == 130
    error = capsys.readouterr().err
    assert "interrupted" in error and "Traceback" not in error and "internal error" not in error


@pytest.mark.parametrize("failure", [BrokenPipeError(), OSError(22, "Invalid argument")])
def test_a_reader_that_goes_away_is_not_an_internal_error(failure, program, monkeypatch, capsys):
    def closed(*arguments, **keywords):
        raise failure
    monkeypatch.setattr(cli, "run", closed)
    assert cli.main(["run", program(HELLO)]) == 0
    assert "internal error" not in capsys.readouterr().err


def test_other_operating_system_errors_are_still_reported(program, monkeypatch, capsys):
    def failing(*arguments):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(cli, "run", failing)
    monkeypatch.delenv("NEXORA_DEBUG", raising=False)
    assert cli.main(["run", program(HELLO)]) == 70
    assert "internal error" in capsys.readouterr().err


# Files that cannot be read

def test_permission_denied_is_a_file_error(program, monkeypatch, capsys):
    path = program(HELLO)

    def denied(self):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(Path, "read_bytes", denied)
    assert cli.main(["run", path]) == 4
    error = capsys.readouterr().err
    assert "file error[E0001]: Cannot read file" in error and "Permission denied" in error


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not enforced on Windows")
def test_a_file_without_read_permission(tmp_path):
    path = tmp_path / "secret.nex"
    path.write_text(HELLO, encoding="utf-8")
    path.chmod(0)
    if os.access(path, os.R_OK):
        pytest.skip("running as a user that can read any file")
    result = nex("run", str(path))
    assert result.returncode == 4 and "E0001" in result.stderr


def test_empty_file(program, capsys):
    assert cli.main(["run", program("")]) == 1
    assert "semantic error[E2001]: Missing main function" in capsys.readouterr().err


# Arguments are paths, never code

@pytest.mark.parametrize("argument", ['print("injected")', "fn main() {}", "__import__('os')", "; echo injected"])
def test_an_argument_is_never_treated_as_source_code(argument, capsys):
    assert cli.main(["run", argument]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "E0001" in captured.err


def test_there_is_no_option_to_pass_code_on_the_command_line(capsys):
    for option in ("-c", "-e", "--eval", "--code", "--exec"):
        assert cli.main(["run", option, "print(1)"]) == 2
    assert "print(1)" not in capsys.readouterr().out


def test_a_file_whose_name_starts_with_a_dash_needs_the_separator(tmp_path, monkeypatch, capsys):
    (tmp_path / "-odd.nex").write_text(HELLO, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["run", "-odd.nex"]) == 2
    capsys.readouterr()
    assert cli.main(["run", "--", "-odd.nex"]) == 0
    assert capsys.readouterr().out == "Hello from NEXORA\n"


# The JSON documents, checked field by field against what docs/language-spec.md promises

DIAGNOSTIC_FIELDS = {
    "severity": str, "category": str, "code": str, "message": str, "label": str, "hint": (str, type(None)),
    "notes": list, "file": str, "line": (int, type(None)), "column": (int, type(None)),
    "end_line": (int, type(None)), "end_column": (int, type(None)),
}
CATEGORY_NAMES = {"file", "lexical", "syntax", "semantic", "type", "runtime", "contract"}


def assert_diagnostics_document(document: dict, path: str) -> None:
    assert isinstance(document["schema"], str) and isinstance(document["ok"], bool)
    assert document["file"] == path
    assert document["ok"] is (document["diagnostics"] == [])
    for diagnostic in document["diagnostics"]:
        assert list(diagnostic) == list(DIAGNOSTIC_FIELDS)
        for field, kind in DIAGNOSTIC_FIELDS.items():
            assert isinstance(diagnostic[field], kind), field
            assert not isinstance(diagnostic[field], bool), field
        assert diagnostic["severity"] == "error"
        assert diagnostic["category"] in CATEGORY_NAMES
        assert diagnostic["file"] == path
        assert all(isinstance(note, str) for note in diagnostic["notes"])
        positions = [diagnostic[name] for name in ("line", "column", "end_line", "end_column")]
        assert all(value is None for value in positions) or all(value >= 1 for value in positions)


@pytest.mark.parametrize("text", [
    HELLO,
    "",                                                       # no main: a diagnostic without a position
    "fn main() {\n    let x = @\n}\n",                # lexical
    "fn main() {\n    let = 1\n}\n",                  # syntax
    'fn main() {\n    let x: Int = "a"\n    print(y)\n}\n',   # type and semantic
    "\x00\x01\x02 not a program at all {{{{ )))) \"",
])
def test_check_json_always_follows_the_schema(text, program, capsys):
    path = program(text)
    code = cli.main(["check", path, "--format", "json"])
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert list(document) == ["schema", "nexora_version", "file", "ok", "diagnostics"]
    assert document["schema"] == "nexora.diagnostics/1"
    assert_diagnostics_document(document, path)
    assert code == (0 if document["ok"] else 1)


def test_diagnostic_codes_and_positions_are_stable_across_runs(program, capsys):
    path = program('fn main() {\n    let x: Int = "a"\n    print(y)\n    let = 2\n}\n')
    outputs = []
    for _ in range(3):
        cli.main(["check", path, "--format", "json"])
        outputs.append(capsys.readouterr().out)
    assert outputs[0] == outputs[1] == outputs[2]


def test_json_positions_agree_with_the_text_report(program, capsys):
    path = program('fn main() {\n    let age: Int = "twenty"\n    print(missing)\n}\n')
    cli.main(["check", path, "--format", "json"])
    document = json.loads(capsys.readouterr().out)
    cli.main(["check", path])
    text = capsys.readouterr().err
    for diagnostic in document["diagnostics"]:
        assert f"{diagnostic['category']} error[{diagnostic['code']}]: {diagnostic['message']}" in text
        assert f"--> {path}:{diagnostic['line']}:{diagnostic['column']}" in text
        assert diagnostic["label"] in text


def test_inspect_document_for_invalid_input_is_controlled(program, capsys):
    path = program("\x00\x01 {{{{ not a program")
    assert cli.main(["inspect", path]) == 1
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert document["program"] is None
    assert_diagnostics_document({key: document[key] for key in ("schema", "file", "ok", "diagnostics")}, path)


# The real command, in a separate process: what a user actually runs.

def test_process_run_hello():
    result = nex("run", "examples/hello.nex")
    assert (result.returncode, result.stdout, result.stderr) == (0, "Hello from NEXORA\n", "")


def test_process_check_hello():
    result = nex("check", "examples/hello.nex")
    assert (result.returncode, result.stdout, result.stderr) == (0, "✓ Check passed: examples/hello.nex\n", "")


def test_process_version_and_help():
    result = nex("--version")
    assert (result.returncode, result.stdout) == (0, f"NEXORA {__version__}\n")
    result = nex("--help")
    assert result.returncode == 0
    for command in ("run", "check", "inspect"):
        assert command in result.stdout


def test_process_usage_error():
    result = nex("frobnicate")
    assert result.returncode == 2 and result.stdout == "" and "usage: nex" in result.stderr


def test_the_installed_nex_command_works():
    # The console script that `pip install` creates next to the Python of this environment.
    script = Path(sys.executable).parent / ("nex.exe" if os.name == "nt" else "nex")
    if not script.exists():
        pytest.skip("the 'nex' command is not installed in this environment")
    version = subprocess.run([str(script), "--version"], capture_output=True, encoding="utf-8")
    assert (version.returncode, version.stdout) == (0, f"NEXORA {__version__}\n")
    run = subprocess.run([str(script), "run", "examples/hello.nex"], capture_output=True, encoding="utf-8", cwd=ROOT)
    assert (run.returncode, run.stdout, run.stderr) == (0, "Hello from NEXORA\n", "")
    failing = subprocess.run(
        [str(script), "run", "examples/failing/contract_violation.nex"], capture_output=True, encoding="utf-8", cwd=ROOT,
    )
    assert failing.returncode == 5


def test_process_from_another_working_directory(tmp_path):
    # A relative path is resolved against the directory the command is run from,
    # and reported exactly as it was given.
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "here.nex").write_text('fn main() {\n    print("from sub")\n    print(nope)\n}\n', encoding="utf-8")
    command = [sys.executable, "-m", "nexora"]

    relative = subprocess.run([*command, "check", "sub/here.nex"], capture_output=True, encoding="utf-8", cwd=tmp_path)
    assert relative.returncode == 1 and "--> sub/here.nex:3:11" in relative.stderr

    inside = subprocess.run([*command, "check", "here.nex"], capture_output=True, encoding="utf-8", cwd=tmp_path / "sub")
    assert inside.returncode == 1 and "--> here.nex:3:11" in inside.stderr

    absolute = subprocess.run(
        [*command, "run", str(ROOT / "examples" / "hello.nex")], capture_output=True, encoding="utf-8", cwd=tmp_path,
    )
    assert (absolute.returncode, absolute.stdout) == (0, "Hello from NEXORA\n")

    missing = subprocess.run([*command, "run", "examples/hello.nex"], capture_output=True, encoding="utf-8", cwd=tmp_path)
    assert missing.returncode == 4


def test_process_output_is_utf8_whatever_the_console_encoding(tmp_path):
    path = tmp_path / "unicode.nex"
    path.write_text('fn main() {\n    print("año ✓ 日本")\n}\n', encoding="utf-8")
    environment = {**os.environ, "PYTHONIOENCODING": "ascii"}
    result = subprocess.run([sys.executable, "-m", "nexora", "run", str(path)], capture_output=True, env=environment)
    assert result.returncode == 0
    assert result.stdout.decode("utf-8").splitlines() == ["año ✓ 日本"]


def test_process_reader_that_stops_early(tmp_path):
    # `nex run big.nex | head -1`: the reader closes the pipe while the program is still printing.
    path = tmp_path / "big.nex"
    body = "\n".join(f'    print("line {index}")' for index in range(20000))
    path.write_text(f"fn main() {{\n{body}\n}}\n", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "nexora", "run", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.stdout.readline().strip() == b"line 0"
    process.stdout.close()
    error = process.stderr.read().decode("utf-8", "replace")
    process.stderr.close()
    assert process.wait(timeout=60) == 0, error
    assert "internal error" not in error and "Traceback" not in error


def test_process_internal_error_is_distinct_from_a_user_error(tmp_path):
    # A defect in NEXORA (simulated by breaking a module) is reported as such, with exit code 70,
    # and only shows a Python traceback when NEXORA_DEBUG is set.
    script = (
        "import sys, nexora.cli as cli\n"
        "def broken(*a, **options):\n    raise RuntimeError('simulated defect')\n"
        "cli.analyze = broken\n"
        "sys.exit(cli.main(['run', sys.argv[1]]))\n"
    )
    hello = str(ROOT / "examples" / "hello.nex")
    environment = {key: value for key, value in os.environ.items() if key != "NEXORA_DEBUG"}
    quiet = subprocess.run([sys.executable, "-c", script, hello], capture_output=True, encoding="utf-8", env=environment)
    assert quiet.returncode == 70
    assert "internal error" in quiet.stderr and "Traceback" not in quiet.stderr

    debug = subprocess.run(
        [sys.executable, "-c", script, hello], capture_output=True, encoding="utf-8",
        env={**environment, "NEXORA_DEBUG": "1"},
    )
    assert debug.returncode != 0 and "Traceback" in debug.stderr and "simulated defect" in debug.stderr

"""Interactive local debugger: commands, budgets, errors, and terminal handling."""

import io
import json
import sys
from types import SimpleNamespace

import pytest

from nexora import cli
from nexora.diagnostics import Diagnostic, NexoraRuntimeError


PROGRAM = '''fn double(value: Int) gives Int {
    let result = value * 2
    return result
}

fn main() {
    let start = 21
    let answer = double(start)
    print(answer)
}
'''


@pytest.fixture
def program(tmp_path):
    path = tmp_path / "debug.nex"
    path.write_text(PROGRAM, encoding="utf-8")
    return path


def debug(path, commands="continue\n", **options):
    output_format = options.pop("output_format", "text")
    console = options.pop("console", io.StringIO(commands))
    return cli._debug(str(path), output_format, console=console, **options)


def test_debugger_commands_variables_call_stack_and_breakpoints(program, capsys):
    commands = (
        "breakpoints\nhelp\nunknown\nbreak nope\nbreak 99\nbreak 3\nbreakpoints\n"
        "delete nope\ndelete 3\nbreak 3\ncontinue\ncontinue\n"
    )

    assert debug(program, commands) == cli.EXIT_OK

    captured = capsys.readouterr()
    assert captured.out == "42\n"
    assert "Paused at" in captured.err and "Call stack:" in captured.err
    assert "value = 21" in captured.err and "result = 42" in captured.err
    assert "Breakpoint set at" in captured.err and "Breakpoint cleared at" in captured.err
    assert "No breakpoints set." in captured.err
    assert "Usage: break" in captured.err and "Usage: delete" in captured.err
    assert "Unknown command" in captured.err and "Commands: step" in captured.err
    assert "Program completed." in captured.err


@pytest.mark.parametrize(("commands", "message"), [
    ("step\nquit\n", "Program stopped by the debugger."),
    ("", "Debugger input closed; stopping the program."),
])
def test_debugger_can_stop_without_running_to_completion(program, commands, message, capsys):
    assert debug(program, commands) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_debugger_empty_command_steps_and_reports_no_breakpoints(program, capsys):
    assert debug(program, "\ncontinue\n") == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "Breakpoints" in captured.err
    assert "42\n" == captured.out


def test_debugger_runs_without_a_debug_limit_and_reports_end_of_program_input(program, monkeypatch, capsys):
    input_program = program.with_name("input.nex")
    input_program.write_text('fn main() {\n    let value = input()\n    print(value)\n}\n', encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert debug(input_program, "continue\n") == cli.EXIT_RUNTIME_ERROR
    assert "standard input ended" in capsys.readouterr().err


def test_debugger_accepts_file_qualified_breakpoints(program, capsys):
    source_path = str(program).replace("\\", "/")
    qualified = f"break {source_path}:3\nbreakpoints\ncontinue\ncontinue\n"
    assert debug(program, qualified) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "Breakpoint set at" in captured.err
    assert source_path + ":3" in captured.err


def test_debugger_initial_breakpoint_and_step_limit(program, capsys):
    assert debug(program, "continue\n", breakpoints=(3,), max_steps=1) == cli.EXIT_RUNTIME_ERROR
    captured = capsys.readouterr()
    assert "--max-steps (1)" in captured.err


@pytest.mark.parametrize(("option", "value", "message"), [
    ("max_steps", 0, "--max-steps must be greater than zero"),
    ("max_output", 0, "--max-output must be greater than zero"),
    ("max_text", -1, "--max-text must be greater than zero"),
    ("timeout", float("nan"), "--timeout must be greater than zero"),
])
def test_debugger_rejects_non_positive_or_non_finite_limits(program, capsys, option, value, message):
    assert debug(program, **{option: value}) == cli.EXIT_USAGE
    assert message in capsys.readouterr().err


def test_debugger_rejects_platform_specific_limits_on_unsupported_platform(program, monkeypatch, capsys):
    monkeypatch.delattr(cli.signal, "SIGALRM", raising=False)
    monkeypatch.delattr(cli.signal, "setitimer", raising=False)
    assert debug(program, timeout=1) == cli.EXIT_USAGE
    assert "--timeout requires a POSIX platform" in capsys.readouterr().err
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    assert debug(program, max_memory=1024) == cli.EXIT_USAGE
    assert "--max-memory is enforced only on Linux" in capsys.readouterr().err


def test_debugger_reports_source_and_analysis_errors(tmp_path, program, capsys):
    missing = tmp_path / "missing.nex"
    assert debug(missing) == cli.EXIT_UNREADABLE_FILE
    assert "the file could not be read" in capsys.readouterr().err
    assert debug(missing, output_format="json") == cli.EXIT_UNREADABLE_FILE
    assert json.loads(capsys.readouterr().err)["ok"] is False

    invalid = tmp_path / "invalid.nex"
    invalid.write_text("fn main() {\n    let broken = @\n}\n", encoding="utf-8")
    assert debug(invalid) == cli.EXIT_INVALID_PROGRAM
    assert "not run because of" in capsys.readouterr().err
    assert debug(invalid, output_format="json") == cli.EXIT_INVALID_PROGRAM
    assert json.loads(capsys.readouterr().err)["ok"] is False

    assert debug(program, max_source=1) == cli.EXIT_RUNTIME_ERROR
    assert "--max-source limit exceeded" in capsys.readouterr().err
    assert debug(program, output_format="json", max_source=1) == cli.EXIT_RUNTIME_ERROR
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_debugger_applies_source_budget_to_imported_modules(tmp_path, capsys):
    entry = tmp_path / "entry.nex"
    entry_text = 'import "dependency.nex"\nfn main() {\n    print(dependency.value())\n}\n'
    entry.write_text(entry_text, encoding="utf-8")
    (tmp_path / "dependency.nex").write_text(
        "// a larger imported module\n" * 20 + "pub fn value() gives Int {\n    return 42\n}\n",
        encoding="utf-8",
    )

    assert debug(entry, max_source=len(entry_text.encode("utf-8"))) == cli.EXIT_RUNTIME_ERROR
    assert "--max-source limit exceeded" in capsys.readouterr().err


def test_debugger_limits_breakpoint_count_and_line_numbers(program, capsys):
    assert debug(program, breakpoints=(1, 999)) == cli.EXIT_USAGE
    assert "--breakpoint must name a line" in capsys.readouterr().err
    assert debug(program, breakpoints=tuple(range(1, 258))) == cli.EXIT_USAGE
    assert "at most 256 breakpoints" in capsys.readouterr().err


def test_debugger_enforces_interactive_breakpoint_count(tmp_path, capsys):
    path = tmp_path / "many.nex"
    path.write_text("fn main() {\n" + "    print(1)\n" * 257 + "}\n", encoding="utf-8")
    commands = "".join(f"break {line}\n" for line in range(2, 258)) + "break 258\ncontinue\n"

    assert debug(path, commands) == cli.EXIT_OK
    assert "At most 256 breakpoints" in capsys.readouterr().err


def test_debugger_passes_arguments_and_grants_file_capabilities(tmp_path, capsys):
    app = tmp_path / "capabilities.nex"
    output = tmp_path / "result.txt"
    app.write_text(
        f'uses write "{output.as_posix()}"\n\n'
        'fn main() {\n    let argument_count = List.length(args())\n'
        '    write_file("' + output.as_posix() + '", to_text(argument_count))\n}\n',
        encoding="utf-8",
    )

    assert cli._debug(str(app), "text", arguments=("written",), allow_write=(str(tmp_path),),
                      console=io.StringIO("continue\n")) == cli.EXIT_OK
    assert output.read_text(encoding="utf-8") == "1"
    assert "Program completed." in capsys.readouterr().err


def test_debugger_max_output_and_text_limits(program, tmp_path, capsys):
    output_program = tmp_path / "output.nex"
    output_program.write_text('fn main() {\n    print("hello")\n}\n', encoding="utf-8")
    assert debug(output_program, "continue\n", max_output=2) == cli.EXIT_RUNTIME_ERROR
    captured = capsys.readouterr()
    assert captured.out == "he"
    assert "output limit exceeded" in captured.err

    assert debug(output_program, "continue\n", max_text=2) == cli.EXIT_RUNTIME_ERROR
    assert "Text is longer than" in capsys.readouterr().err

    assert debug(output_program, "continue\n", max_output=20) == cli.EXIT_OK
    assert capsys.readouterr().out == "hello\n"


def test_debugger_enforces_input_limit(program, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"too-long\n"), encoding="utf-8"))
    input_program = program.with_name("input.nex")
    input_program.write_text('fn main() {\n    let value = input()\n    print(value)\n}\n', encoding="utf-8")

    assert debug(input_program, "continue\n", max_input=3) == cli.EXIT_RUNTIME_ERROR
    assert "input limit exceeded" in capsys.readouterr().err


def test_debugger_reads_bounded_and_unbounded_input(program, monkeypatch, capsys):
    input_program = program.with_name("input.nex")
    input_program.write_text('fn main() {\n    let value = input()\n    print(value)\n}\n', encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello\n"))
    assert debug(input_program, "continue\n") == cli.EXIT_OK
    assert capsys.readouterr().out == "hello\n"

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"long\n"), encoding="utf-8"))
    assert debug(input_program, "continue\n", max_text=3) == cli.EXIT_RUNTIME_ERROR
    assert "Text is longer than" in capsys.readouterr().err


def test_debugger_reports_runtime_and_contract_failures(tmp_path, capsys):
    runtime = tmp_path / "runtime.nex"
    runtime.write_text('fn main() {\n    let value = 1 / 0\n}\n', encoding="utf-8")
    assert debug(runtime, "continue\n") == cli.EXIT_RUNTIME_ERROR
    assert "runtime error" in capsys.readouterr().err

    contract = tmp_path / "contract.nex"
    contract.write_text('fn main()\n    needs false, "must hold"\n{\n}\n', encoding="utf-8")
    assert debug(contract, "continue\n") == cli.EXIT_CONTRACT_VIOLATION
    assert "contract was broken" in capsys.readouterr().err


def test_debugger_reports_analysis_memory_exhaustion(program, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "resource", SimpleNamespace(RLIMIT_AS=1, setrlimit=lambda *_: None))

    def exhaust(*_args, **_kwargs):
        raise MemoryError

    monkeypatch.setattr(cli, "analyze", exhaust)
    assert debug(program, max_memory=1024) == cli.EXIT_RUNTIME_ERROR
    assert "memory limit was exceeded" in capsys.readouterr().err


def test_debugger_reports_memory_limit_setup_failure(program, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "platform", "linux")

    def denied(*_args):
        raise OSError("not supported")

    monkeypatch.setitem(sys.modules, "resource", SimpleNamespace(RLIMIT_AS=1, setrlimit=denied))
    assert debug(program, max_memory=1024) == cli.EXIT_USAGE
    assert "requires POSIX RLIMIT_AS support" in capsys.readouterr().err


def test_debugger_propagates_memory_error_without_a_memory_limit(program, monkeypatch):
    def exhaust(*_args, **_kwargs):
        raise MemoryError

    monkeypatch.setattr(cli, "analyze", exhaust)
    with pytest.raises(MemoryError):
        debug(program)


def test_debugger_propagates_runtime_memory_error_without_a_memory_limit(program, monkeypatch):
    def exhaust(*_args, **_kwargs):
        raise MemoryError

    monkeypatch.setattr(cli, "run", exhaust)
    with pytest.raises(MemoryError):
        debug(program, console=io.StringIO("continue\n"))


def test_debugger_reports_runtime_memory_exhaustion(program, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "resource", SimpleNamespace(RLIMIT_AS=1, setrlimit=lambda *_: None))

    def exhaust(*_args, **_kwargs):
        raise MemoryError

    monkeypatch.setattr(cli, "run", exhaust)
    assert debug(program, max_memory=1024, console=io.StringIO("continue\n")) == cli.EXIT_RUNTIME_ERROR
    assert "memory limit was exceeded" in capsys.readouterr().err


def test_debugger_reports_runtime_diagnostics_as_text_and_json(program, monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise NexoraRuntimeError(Diagnostic("E3001", "runtime failure"), file=str(program))

    monkeypatch.setattr(cli, "run", fail)
    assert debug(program, "continue\n") == cli.EXIT_RUNTIME_ERROR
    assert "runtime error" in capsys.readouterr().err
    assert debug(program, "continue\n", output_format="json") == cli.EXIT_RUNTIME_ERROR
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_debug_command_parser_and_terminal_failure(program, monkeypatch, capsys):
    assert cli.main(["debug", str(program), "--help"]) == 0
    assert "--max-steps" in capsys.readouterr().out
    assert cli.main(["debug", str(program), "--max-steps", "0"]) == cli.EXIT_USAGE
    assert "--max-steps must be greater than zero" in capsys.readouterr().err

    monkeypatch.setattr(cli, "_open_debug_console", lambda: (_ for _ in ()).throw(OSError("no tty")))
    assert cli._debug(str(program), "text") == cli.EXIT_USAGE
    assert "needs a controlling terminal" in capsys.readouterr().err


def test_debug_console_opens_the_controlling_terminal_via_io(monkeypatch):
    expected = "CONIN$" if cli.os.name == "nt" else "/dev/tty"
    opened = []
    monkeypatch.setattr(cli.Path, "open", lambda path, **kwargs: opened.append((path, kwargs)) or io.StringIO())
    cli._open_debug_console()
    assert str(opened[0][0]) == expected


def test_debugger_pauses_and_resumes_the_timeout_around_prompts(program, monkeypatch):
    timers = []
    monkeypatch.setattr(cli.signal, "SIGALRM", 14, raising=False)
    monkeypatch.setattr(cli.signal, "ITIMER_REAL", 0, raising=False)
    monkeypatch.setattr(cli.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(cli.signal, "getitimer", lambda *_args: (0.5, 0), raising=False)
    monkeypatch.setattr(cli.signal, "setitimer", lambda *args: timers.append(args), raising=False)

    assert debug(program, "continue\n", timeout=1) == cli.EXIT_OK
    assert timers and all(len(timer) == 2 for timer in timers)


def test_debugger_closes_the_terminal_it_opens(program, monkeypatch):
    terminal = io.StringIO("quit\n")
    monkeypatch.setattr(cli, "_open_debug_console", lambda: terminal)
    assert cli._debug(str(program), "text") == cli.EXIT_OK
    assert terminal.closed

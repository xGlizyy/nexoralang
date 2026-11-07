"""One suite that pins the stable CLI of `check`, `run` and `test` (docs/interface-stability.md).

A change to an exit code, an option or a diagnostic code fails a test that names it. Additions are allowed:
new options and new codes only have to be added to tests/golden/cli_contract.json on purpose.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexora import cli, diagnostics

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "tests" / "golden" / "cli_contract.json").read_text(encoding="utf-8"))

OK = 'fn main() {\n    print("ok")\n}\n'
STATIC = "fn main() {\n    print(missing)\n}\n"
RUNTIME = "fn main() {\n    print(1 / 0)\n}\n"
NEEDS = (
    "fn half(n: Int) gives Int\n    needs n > 0\n{\n    return n / 2\n}\n"
    "fn main() {\n    print(half(0))\n}\n"
)
EXAMPLES = {
    "pass": "fn double(n: Int) gives Int\n    example double(2) == 4\n{\n    return n * 2\n}\n",
    "fail": "fn double(n: Int) gives Int\n    example double(2) == 5\n{\n    return n * 2\n}\n",
    "none": "fn double(n: Int) gives Int {\n    return n * 2\n}\n",
}


def nex(*arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nexora", *arguments], capture_output=True, encoding="utf-8", cwd=cwd
    )


@pytest.fixture
def source(tmp_path):
    def write(text: str) -> str:
        path = tmp_path / "program.nex"
        path.write_text(text, encoding="utf-8")
        return str(path)
    return write


@pytest.mark.parametrize("command", ["run", "check", "test"])
def test_every_pinned_option_of_the_command_still_exists(command):
    parser = cli._build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    current = {
        option
        for action in subparsers.choices[command]._actions
        for option in action.option_strings
        if option.startswith("--")
    }
    assert set(CONTRACT["options"][command]) <= current, sorted(set(CONTRACT["options"][command]) - current)


@pytest.mark.parametrize("command", ["run", "check", "test"])
def test_a_new_option_is_added_to_the_contract_on_purpose(command):
    parser = cli._build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    current = {
        option
        for action in subparsers.choices[command]._actions
        for option in action.option_strings
        if option.startswith("--")
    }
    assert current <= set(CONTRACT["options"][command]), sorted(current - set(CONTRACT["options"][command]))


def test_no_diagnostic_code_is_removed_or_changes_category():
    for code, category in CONTRACT["diagnostics"].items():
        assert diagnostics.CATEGORIES.get(code) == category, code


def test_a_new_diagnostic_code_is_added_to_the_contract_on_purpose():
    assert set(diagnostics.CATEGORIES) <= set(CONTRACT["diagnostics"]), sorted(
        set(diagnostics.CATEGORIES) - set(CONTRACT["diagnostics"])
    )


@pytest.mark.parametrize(
    ("arguments", "text", "status"),
    [
        (("check",), OK, 0),
        (("check",), STATIC, 1),
        (("run",), OK, 0),
        (("run",), STATIC, 1),
        (("run",), RUNTIME, 3),
        (("run",), NEEDS, 5),
        (("test",), EXAMPLES["pass"], 0),
        (("test",), EXAMPLES["fail"], 6),
        (("test",), EXAMPLES["none"], 6),
        (("test",), STATIC, 1),
    ],
    ids=lambda value: value if isinstance(value, int) else None,
)
def test_exit_status_of_the_real_command(arguments, text, status, source):
    assert nex(*arguments, source(text)).returncode == status


@pytest.mark.parametrize("command", ["run", "check", "test"])
def test_missing_file_is_status_4_with_e0001(command, tmp_path):
    result = nex(command, str(tmp_path / "missing.nex"))
    assert result.returncode == 4 and "E0001" in result.stderr


@pytest.mark.parametrize("arguments", [("check", "--bogus"), ("run", "--timeout", "0"), ("test", "--format", "xml")])
def test_invalid_use_is_status_2_with_nothing_on_standard_output(arguments, source):
    result = nex(*arguments, source(OK))
    assert result.returncode == 2 and result.stdout == ""


@pytest.mark.parametrize(
    ("command", "text", "code"),
    [
        ("check", STATIC, "E2005"),
        ("run", RUNTIME, "E3001"),
        ("run", NEEDS, "E4001"),
        ("test", EXAMPLES["fail"], "E4004"),
    ],
)
def test_diagnostic_code_reaches_the_user(command, text, code, source):
    result = nex(command, source(text))
    assert f"[{code}]" in result.stderr + result.stdout, (result.stdout, result.stderr)


def test_check_json_reports_the_diagnostic_code_and_category_on_standard_output(source):
    result = nex("check", "--format", "json", source(STATIC))
    document = json.loads(result.stdout)
    assert result.returncode == 1 and document["ok"] is False
    first = document["diagnostics"][0]
    assert (first["code"], first["category"]) == ("E2005", diagnostics.CATEGORIES["E2005"])


def test_test_json_exit_status_follows_the_report(source):
    result = nex("test", "--format", "json", source(EXAMPLES["fail"]))
    assert result.returncode == 6 and json.loads(result.stdout)["schema"] == "nexora.test/1"

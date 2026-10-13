"""`nexora.api`: checking and running source held in memory, as the playground does."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexora import __version__, api
from nexora.checker import BUILTINS
from nexora.tokens import KEYWORDS

from helpers import in_main, with_main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

HELLO = 'fn main() -> Void {\n    print("Hello from NEXORA")\n}\n'
RESULT_FIELDS = ["schema", "action", "status", "output", "diagnostics", "message"]


def assert_result(result: dict, action: str, status: str) -> None:
    assert list(result) == RESULT_FIELDS
    assert (result["schema"], result["action"], result["status"]) == ("nexora.result/1", action, status)
    assert isinstance(result["output"], str) and isinstance(result["diagnostics"], list)
    json.dumps(result)


# check_source

def test_check_valid_program():
    result = api.check_source(HELLO)
    assert_result(result, "check", "success")
    assert (result["output"], result["diagnostics"], result["message"]) == ("", [], None)


@pytest.mark.parametrize("source, category, code", [
    ("fn main() -> Void {\n    let x = @\n}", "lexical", "E1001"),
    ("fn main() -> Void {\n    let = 1\n}", "syntax", "E1101"),
    ("fn main() -> Void {\n    print(missing)\n}", "semantic", "E2005"),
    ('fn main() -> Void {\n    let n: Int = "a"\n}', "type", "E2011"),
])
def test_check_reports_static_errors_with_positions(source, category, code):
    result = api.check_source(source, "demo.nex")
    assert_result(result, "check", "invalid")
    (diagnostic,) = result["diagnostics"]
    assert (diagnostic["category"], diagnostic["code"], diagnostic["file"], diagnostic["line"]) == (category, code, "demo.nex", 2)


def test_check_never_runs_the_program(monkeypatch):
    def forbidden(*arguments, **options):
        raise AssertionError("check must not start the interpreter")
    monkeypatch.setattr(api, "run", forbidden)
    source = 'fn main() -> Void {\n    print("SIDE EFFECT")\n    print(1 / 0)\n}\n'
    assert api.check_source(source)["status"] == "success"


# run_source

def test_run_valid_program():
    result = api.run_source(HELLO)
    assert_result(result, "run", "success")
    assert (result["output"], result["diagnostics"]) == ("Hello from NEXORA\n", [])


def test_run_does_not_start_a_program_with_static_errors(monkeypatch):
    def forbidden(*arguments, **options):
        raise AssertionError("a program with static errors must not be started")
    monkeypatch.setattr(api, "run", forbidden)
    result = api.run_source('fn main() -> Void {\n    print("must not appear")\n    print(missing)\n}\n')
    assert_result(result, "run", "invalid")
    assert result["output"] == "" and result["diagnostics"][0]["code"] == "E2005"


def test_run_runtime_error_keeps_the_output_so_far():
    result = api.run_source(in_main('print("before")\nprint(1 / 0)\nprint("after")'))
    assert_result(result, "run", "runtime_error")
    assert result["output"] == "before\n"
    assert (result["diagnostics"][0]["code"], result["diagnostics"][0]["line"]) == ("E3001", 3)


def test_run_contract_violation_is_its_own_status():
    functions = "fn half(n: Int) -> Int {\n    requires n > 0\n    return n / 2\n}"
    result = api.run_source(with_main(functions, "print(half(8))\nprint(half(0))"))
    assert_result(result, "run", "contract_violation")
    assert result["output"] == "4\n"
    assert result["diagnostics"][0]["category"] == "contract"


def test_filename_is_only_a_label():
    # Whatever the name, nothing is opened: it only appears in the diagnostics.
    for name in ("playground.nex", "../../etc/passwd", "C:\\Windows\\win.ini", ""):
        result = api.check_source("fn main() -> Void {\n    print(x)\n}", name)
        assert result["diagnostics"][0]["file"] == name


# Limits

LOOP = "fn spam(n: Int) -> Void {\n    if n == 0 {\n        return\n    }\n    print(\"0123456789\")\n    spam(n - 1)\n}"


def test_output_limit_stops_the_program():
    result = api.run_source(with_main(LOOP, "spam(900)\nprint(\"end\")"), limits=api.Limits(output_bytes=100))
    assert_result(result, "run", "output_limit")
    assert len(result["output"].encode("utf-8")) <= 100
    assert result["output"].startswith("0123456789\n")
    assert "end" not in result["output"]
    assert result["message"] == "The program printed more than 100 bytes and was stopped."


def test_output_exactly_at_the_limit_is_not_an_error():
    result = api.run_source(in_main('print("abcd")'), limits=api.Limits(output_bytes=5))
    assert (result["status"], result["output"]) == ("success", "abcd\n")
    assert api.run_source(in_main('print("abcd")'), limits=api.Limits(output_bytes=4))["status"] == "output_limit"


def test_output_limit_counts_bytes_and_does_not_split_a_character():
    result = api.run_source(in_main('print("ñññ")'), limits=api.Limits(output_bytes=3))
    assert result["status"] == "output_limit"
    assert result["output"] == "ñ"


def test_without_limits_output_is_unbounded():
    result = api.run_source(with_main(LOOP, "spam(900)"))
    assert result["status"] == "success" and result["output"].count("\n") == 900


DOUBLE = 'fn grow(text: Text, times: Int) -> Text {\n    if times == 0 {\n        return text\n    }\n    return grow(text + text, times - 1)\n}'


def test_text_limit_is_a_runtime_error_with_its_own_code():
    result = api.run_source(with_main(DOUBLE, 'print("start")\nlet big = grow("ab", 40)\nprint("end")'),
                            limits=api.Limits(text_chars=1000))
    assert_result(result, "run", "runtime_error")
    assert result["output"] == "start\n"
    diagnostic = result["diagnostics"][0]
    assert (diagnostic["code"], diagnostic["category"], diagnostic["message"]) == ("E3006", "runtime", "Text too long")
    assert "1000 characters" in diagnostic["label"]


def test_text_within_the_limit_is_fine():
    result = api.run_source(with_main(DOUBLE, 'let text = grow("ab", 3)\nprint(text)'), limits=api.Limits(text_chars=16))
    assert (result["status"], result["output"]) == ("success", "ab" * 8 + "\n")


def test_the_cli_does_not_limit_text_length():
    result = api.run_source(with_main(DOUBLE, 'let text = grow("ab", 12)\nprint(text == text)'))
    assert (result["status"], result["output"]) == ("success", "true\n")


# The same core as the command line

def cli_json(command: str, path: Path) -> tuple[int, str, dict | None]:
    process = subprocess.run(
        [sys.executable, "-m", "nexora", command, str(path), "--format", "json"],
        capture_output=True, encoding="utf-8",
    )
    stream = process.stdout if command == "check" else process.stderr
    document = json.loads(stream) if stream.strip().startswith("{") else None
    return process.returncode, process.stdout, document


def without_file(diagnostics: list[dict]) -> list[dict]:
    return [{key: value for key, value in diagnostic.items() if key != "file"} for diagnostic in diagnostics]


STATUS_OF_EXIT = {0: "success", 1: "invalid", 3: "runtime_error", 5: "contract_violation"}


@pytest.mark.parametrize("path", sorted(EXAMPLES.rglob("*.nex")), ids=lambda path: path.relative_to(EXAMPLES).as_posix())
def test_api_and_cli_agree_on_every_example(path):
    source = path.read_text(encoding="utf-8")

    # check: same verdict and the same diagnostics, apart from the file name shown.
    code, _, document = cli_json("check", path)
    checked = api.check_source(source)
    assert checked["status"] == ("success" if code == 0 else "invalid")
    assert without_file(checked["diagnostics"]) == without_file(document["diagnostics"])

    # run: same output, same status, same diagnostics.
    code, output, document = cli_json("run", path)
    ran = api.run_source(source)
    assert ran["status"] == STATUS_OF_EXIT[code]
    assert ran["output"] == output
    assert without_file(ran["diagnostics"]) == without_file(document["diagnostics"] if document else [])


# language_info

def test_language_info_comes_from_the_implementation():
    info = api.language_info()
    assert info["version"] == __version__
    assert info["keywords"] == sorted(KEYWORDS)
    assert info["builtins"] == sorted(BUILTINS)
    assert info["types"] == ["Void", "Int", "Float", "Bool", "Text"]
    assert "while" in info["reserved_words"] and "fn" not in info["reserved_words"]
    json.dumps(info)

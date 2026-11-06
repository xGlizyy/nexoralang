"""The reference applications of decision 0021 check, test and run as documented.

Three programs in reference-apps/ are the evidence for the 1.0 subset: a pure command-line tool (textstats), a tool
that reads and writes files and is made of several modules (csvsummary), and a tool that runs an external program
under an explicit grant (envreport). Each one is run through the real command, in a separate process, and its
standard output, standard error and exit code are compared with what its README says.

The applications that write files are copied into a temporary directory first, so the tests leave the repository as
they found it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "reference-apps"
# The interpreter that runs the applications. CI points it at a clean virtual environment with the built wheel installed
# (job "reference-apps"), so the applications are checked against the package a user installs, not against this tree.
INTERPRETER = os.environ.get("NEXORA_APPS_PYTHON", sys.executable)


def nex(args: list[str], cwd: Path, stdin: str | None = None, env: dict[str, str] | None = None):
    """Runs `INTERPRETER -m nexora ARGS` in `cwd` and returns (exit code, stdout, stderr), line breaks normalized."""
    done = subprocess.run(
        [INTERPRETER, "-m", "nexora", *args], cwd=cwd, input=stdin, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", **(env or {})}, timeout=120,
    )
    return done.returncode, done.stdout.replace("\r\n", "\n"), done.stderr.replace("\r\n", "\n")


@pytest.fixture
def workspace(tmp_path: Path):
    """A copy of one application, ready to run: returns a function that copies an application and gives its folder."""

    def copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(APPS / name, target)
        return target

    return copy


# --- textstats: a pure command-line tool -------------------------------------------------------------------------------

SENTENCE = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog", "the", "end"]
SENTENCE_REPORT = (
    "characters: 51\nwords: 11\nvowels: 13\nlongest: quick\nmost frequent: the (3)\n"
)


def test_textstats_checks_and_its_examples_pass():
    folder = APPS / "textstats"
    assert nex(["check", "textstats.nex"], folder)[0] == 0
    code, out, _ = nex(["test", "textstats.nex"], folder)
    assert code == 0
    assert "15 examples passed" in out


def test_textstats_reads_its_arguments():
    code, out, err = nex(["run", "textstats.nex", "--", *SENTENCE], APPS / "textstats")
    assert (code, out, err) == (0, SENTENCE_REPORT, "")


def test_textstats_reads_a_line_of_the_standard_input():
    code, out, err = nex(["run", "textstats.nex"], APPS / "textstats", stdin="to be or not to be\n")
    assert (code, err) == (0, "")
    assert out == "characters: 18\nwords: 6\nvowels: 6\nlongest: not\nmost frequent: to (2)\n"


def test_textstats_with_an_empty_text_has_nothing_to_say_about_words():
    code, out, _ = nex(["run", "textstats.nex", "--", ""], APPS / "textstats")
    assert code == 0
    assert out == "characters: 0\nwords: 0\nvowels: 0\nlongest: -\nmost frequent: -\n"


def test_textstats_with_no_standard_input_stops_with_the_documented_error():
    code, out, err = nex(["run", "textstats.nex"], APPS / "textstats", stdin="")
    assert code == 3
    assert out == ""
    assert "E3009" in err


def test_textstats_declares_no_capability():
    lines = (APPS / "textstats" / "textstats.nex").read_text(encoding="utf-8").splitlines()
    assert not [line for line in lines if line.startswith("uses ")]


# --- csvsummary: files and modules ---------------------------------------------------------------------------------------

GRANTS = ["--allow-read", "data", "--allow-write", "out"]
SALES_SUMMARY = "units: count 4, sum 42, low 3, high 20\nrevenue: count 4, sum 1255, low 95, high 610\n"


def summarize(folder: Path, source: str, target: str = "out/summary.txt", grants: list[str] | None = None):
    return nex(["run", "main.nex", *(GRANTS if grants is None else grants), "--", source, target], folder)


def test_csvsummary_checks_and_the_examples_of_all_its_modules_pass(workspace):
    folder = workspace("csvsummary")
    assert nex(["check", "main.nex"], folder)[0] == 0
    code, out, _ = nex(["test", "main.nex"], folder)
    assert code == 0
    assert "examples passed" in out


def test_csvsummary_summarizes_a_file_and_writes_the_result(workspace):
    folder = workspace("csvsummary")
    code, out, err = summarize(folder, "data/sales.csv")
    assert (code, out, err) == (0, SALES_SUMMARY + "\n", "")
    assert (folder / "out" / "summary.txt").read_text(encoding="utf-8") == SALES_SUMMARY


def test_csvsummary_reads_a_file_written_on_windows(workspace):
    folder = workspace("csvsummary")
    assert (folder / "data" / "crlf.csv").read_bytes().count(b"\r\n") == 3
    code, out, _ = summarize(folder, "data/crlf.csv")
    assert code == 0
    assert out == "n: count 2, sum 10, low 4, high 6\n\n"


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("bad_cell.csv", "error: row 2 of column n is not a whole number: x\n"),
        ("short_row.csv", "error: line 3 has 1 fields, the header has 2\n"),
        ("empty.csv", "error: the file is empty\n"),
    ],
)
def test_csvsummary_reports_a_bad_file_and_writes_nothing(workspace, fixture, message):
    folder = workspace("csvsummary")
    code, out, err = summarize(folder, f"data/{fixture}")
    assert (code, out, err) == (0, message, "")
    assert not (folder / "out" / "summary.txt").exists()


def test_csvsummary_without_its_arguments_prints_the_usage(workspace):
    code, out, _ = nex(["run", "main.nex", *GRANTS], workspace("csvsummary"))
    assert code == 0
    assert out.startswith("usage: ")


def test_csvsummary_without_the_read_grant_is_denied(workspace):
    folder = workspace("csvsummary")
    code, _, err = summarize(folder, "data/sales.csv", grants=["--allow-write", "out"])
    assert code == 3
    assert "E3008" in err
    assert "not among the paths the user allowed to read" in err


def test_csvsummary_cannot_read_outside_what_it_declares(workspace):
    folder = workspace("csvsummary")
    (folder / "secret.csv").write_text("who,n\na,1\n", encoding="utf-8")
    code, _, err = summarize(folder, "secret.csv", grants=["--allow-read", ".", "--allow-write", "out"])
    assert code == 3
    assert "does not declare that it needs to read" in err


def test_csvsummary_cannot_write_outside_what_it_declares(workspace):
    folder = workspace("csvsummary")
    code, _, err = summarize(folder, "data/sales.csv", target="elsewhere.txt", grants=["--allow-read", "data", "--allow-write", "."])
    assert code == 3
    assert "E3008" in err
    assert not (folder / "elsewhere.txt").exists()


# --- envreport: a granted external process -------------------------------------------------------------------------------

ENVREPORT_OUTPUT = "interpreter: python\nmajor: 3\nsupported: true\ncheck: 42\n"


def python_on_the_path() -> dict[str, str]:
    """A PATH in which `python` is the interpreter that runs the applications, so the output does not depend on the machine."""
    return {"PATH": str(Path(INTERPRETER).parent) + os.pathsep + os.environ.get("PATH", "")}


def has_python_command() -> bool:
    return shutil.which("python", path=python_on_the_path()["PATH"]) is not None


def test_envreport_checks_and_its_examples_pass():
    folder = APPS / "envreport"
    assert nex(["check", "envreport.nex"], folder)[0] == 0
    code, out, _ = nex(["test", "envreport.nex"], folder)
    assert code == 0
    assert "13 examples passed" in out


@pytest.mark.skipif(not has_python_command(), reason="no `python` command on this machine")
def test_envreport_runs_the_process_it_declares_and_is_granted():
    code, out, err = nex(["run", "envreport.nex", "--allow-process", "python"], APPS / "envreport", env=python_on_the_path())
    assert (code, out, err) == (0, ENVREPORT_OUTPUT, "")


def test_envreport_without_the_grant_is_denied_and_runs_nothing():
    code, out, err = nex(["run", "envreport.nex"], APPS / "envreport", env=python_on_the_path())
    assert code == 3
    assert out == ""
    assert "E3008" in err


def test_envreport_without_the_declaration_does_not_pass_the_check(tmp_path):
    source = (APPS / "envreport" / "envreport.nex").read_text(encoding="utf-8")
    assert 'uses process "python"\n' in source
    (tmp_path / "undeclared.nex").write_text(source.replace('uses process "python"\n', ""), encoding="utf-8", newline="\n")
    code, _, err = nex(["check", "undeclared.nex"], tmp_path)
    assert code == 1
    assert "E2026" in err

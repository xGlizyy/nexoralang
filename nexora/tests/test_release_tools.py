"""The release tools of nexora/release/ are NEXORA programs: they are checked, their examples run, and the freeze check passes.

The tools themselves do the work (nexora-release.yml runs them with the native nex); these tests make the Python CI notice a broken
one, and check that the specification is what decision 0029 froze, with the reference implementation.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = sorted((ROOT / "release").glob("*.nex"))


def nex(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nexora", *arguments], capture_output=True, encoding="utf-8", cwd=ROOT,
    )


def test_the_release_tools_exist():
    assert [tool.name for tool in TOOLS] == ["check_artifacts.nex", "check_freeze.nex", "texts.nex"]


PROGRAMS = [tool for tool in TOOLS if "fn main()" in tool.read_text(encoding="utf-8")]


@pytest.mark.parametrize("tool", PROGRAMS, ids=lambda tool: tool.name)
def test_a_release_program_passes_check_without_warnings(tool):  # a module (texts.nex) has no main, so it is only tested
    result = nex("check", f"release/{tool.name}")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout.startswith("✓ Check passed:") and "warning" not in result.stdout


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_the_examples_of_a_release_tool_pass(tool):
    result = nex("test", f"release/{tool.name}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "examples passed" in result.stdout


def test_the_specification_is_what_decision_0029_froze():
    result = nex("run", "--allow-read", ".", "release/check_freeze.nex", "--", "check", "docs/language-spec.md", "release/frozen")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[0] == "the specification is what was frozen"


def frozen_lines(name: str) -> list[str]:
    return (ROOT / "release" / "frozen" / name).read_text(encoding="utf-8").splitlines()


def test_the_frozen_files_hold_what_the_reference_implementation_has():
    from nexora import diagnostics

    frozen_codes = {line.split("|")[0].strip("`") for line in frozen_lines("diagnostics.txt")}
    assert frozen_codes == set(diagnostics.CATEGORIES)
    frozen_categories = {line.split("|")[0].strip("`"): line.split("|")[2].strip("`") for line in frozen_lines("diagnostics.txt")}
    assert frozen_categories == diagnostics.CATEGORIES


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("gives   needs   promises   trust", "keywords changed since the freeze"),
        ("| `Text.length(text: Text) gives Int`", "builtins: a frozen line is gone or changed"),
        ('import_decl = "import" TEXT ;', "grammar changed since the freeze"),
    ],
    ids=["keyword", "builtin", "grammar"],
)
def test_a_change_to_the_frozen_parts_fails_the_check_with_status_5(change, expected):
    spec = (ROOT / "docs" / "language-spec.md").read_text(encoding="utf-8")
    assert change in spec
    if change.startswith("gives"):
        changed = spec.replace(change, change + "   fresh", 1)
    elif change.startswith("|"):
        changed = "\n".join(line for line in spec.splitlines() if not line.startswith(change)) + "\n"
    else:
        changed = spec.replace(change, 'import_decl = "import" NAME ;', 1)
    folder = ROOT / "release" / "frozen"
    scratch = ROOT / "release" / "_changed_spec.md"
    try:
        scratch.write_text(changed, encoding="utf-8", newline="\n")
        result = nex("run", "--allow-read", ".", "release/check_freeze.nex", "--", "check", "release/_changed_spec.md", str(folder.relative_to(ROOT)))
    finally:
        scratch.unlink(missing_ok=True)
    assert result.returncode == 5, result.stdout + result.stderr
    assert expected in result.stdout


def test_an_addition_is_a_note_and_not_a_failure():
    spec = (ROOT / "docs" / "language-spec.md").read_text(encoding="utf-8")
    anchor = "| `E0002` | File is not valid UTF-8 | `file` | The file is not encoded in UTF-8 |"
    assert anchor in spec
    added = spec.replace(anchor, anchor + "\n| `E0099` | A new code | `file` | An addition after the freeze |", 1)
    scratch = ROOT / "release" / "_added_spec.md"
    try:
        scratch.write_text(added, encoding="utf-8", newline="\n")
        result = nex("run", "--allow-read", ".", "release/check_freeze.nex", "--", "check", "release/_added_spec.md", "release/frozen")
    finally:
        scratch.unlink(missing_ok=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "note: diagnostics: new since the freeze: `E0099`|A new code|`file`" in result.stdout

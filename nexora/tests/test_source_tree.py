"""The suite refuses to test an interpreter other than the one of this tree (tests/conftest.py).

A Python with the published package installed imported that copy, and the suite reported 46
false failures of the modules of 0.11.0 that were the behaviour of 0.10.0.
"""

import os
import subprocess
import sys
from pathlib import Path

import nexora
from conftest import SOURCE, imported_from

TESTS = Path(__file__).resolve().parent


def test_the_suite_runs_against_this_source_tree():
    assert imported_from(nexora) == SOURCE


def test_another_copy_of_nexora_stops_the_suite_before_any_test(tmp_path):
    # A copy that comes first on the path, as an installed package does.
    (tmp_path / "nexora").mkdir()
    (tmp_path / "nexora" / "__init__.py").write_text('__version__ = "0.10.0"\n', encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(tmp_path)}

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS / "test_modules_syntax.py"), "-q", "-p", "no:cacheprovider"],
        capture_output=True, encoding="utf-8", env=environment, cwd=TESTS.parent,
    )

    assert result.returncode == 4, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "these tests are for the interpreter in" in output
    assert str(tmp_path) in output
    assert "passed" not in output and "failed" not in output

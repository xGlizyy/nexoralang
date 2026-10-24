"""The frozen front end of 0.11 (decision 0019, 8.2): it must keep reading what 0.11 read.

`nex migrate` checks a program with this copy before it migrates it. The 0.12 front end
changes the syntax, so the copy is tested against a corpus frozen at the commit where
phase 1 started (`tests/migration/corpus011`), not against the live front end: for every
program of the corpus it must give the diagnostics recorded there by 0.11.
"""

import ast as python_ast
import json
from pathlib import Path

import pytest

from nexora import cli
from nexora.legacy011.diagnostics import Diagnostic, Source
from nexora.legacy011.pipeline import analyze

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "migration" / "corpus011"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
LEGACY = ROOT / "src" / "nexora" / "legacy011"


def _found(path: Path, require_main: bool) -> list[list]:
    # Imports are read as `nex` reads them, with the classes of the frozen front end.
    source = Source(str(path), path.read_text(encoding="utf-8"))
    reader = cli._module_reader(source, Source, Diagnostic)
    found = analyze(source, require_main=require_main, read=reader).diagnostics
    return [[d.code, d.span.line if d.span else None, d.span.column if d.span else None] for d in found]


@pytest.mark.parametrize("entry", MANIFEST["programs"], ids=lambda entry: entry["path"])
def test_the_frozen_front_end_gives_the_diagnostics_of_0_11(entry):
    path = CORPUS / entry["path"]
    assert _found(path, True) == entry["diagnostics_011"]["with_main"]
    assert _found(path, False) == entry["diagnostics_011"]["without_main"]


def test_the_corpus_is_the_one_frozen_for_phase_1():
    assert MANIFEST["nexora_version"] == "0.11.0"
    paths = [entry["path"] for entry in MANIFEST["programs"]]
    assert len(paths) == len(set(paths))
    assert sorted(paths) == sorted(p.relative_to(CORPUS).as_posix() for p in CORPUS.rglob("*.nex"))


def test_the_frozen_front_end_has_not_changed_since_it_was_copied():
    # It is left out of the coverage threshold, because it is a copy of code that was covered
    # when it was live; what keeps it right is that it does not change at all.
    import hashlib

    recorded = json.loads((ROOT / "tests" / "migration" / "legacy011.sha256.json").read_text(encoding="utf-8"))["files"]
    found = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(LEGACY.glob("*.py")) if path.name != "__init__.py"}
    assert found == recorded


def test_the_frozen_front_end_imports_nothing_from_the_live_one():
    # A copy that reaches back into `nexora.*` would change when 0.12 does.
    for path in sorted(LEGACY.glob("*.py")):
        tree = python_ast.parse(path.read_text(encoding="utf-8"))
        for node in python_ast.walk(tree):
            if isinstance(node, python_ast.ImportFrom):
                assert node.level in (0, 1), f"{path.name}: relative import outside the package"
                if node.level == 0:
                    assert not (node.module or "").startswith("nexora"), f"{path.name}: imports {node.module}"
            elif isinstance(node, python_ast.Import):
                assert not any(alias.name.startswith("nexora") for alias in node.names), path.name

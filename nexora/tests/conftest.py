"""The suite tests the interpreter of this source tree, and refuses to test any other.

A Python that has the published package installed (`pip install nexora-lang`) imports that
copy instead of `src/nexora`, and the suite would then report the differences between the two
versions as failures of this one. Adding `src` to the path is not enough: many tests start
`python -m nexora` in another process, and the playground worker runs with `-I`, which ignores
PYTHONPATH, so those would still run the installed copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import nexora

SOURCE = (Path(__file__).resolve().parents[1] / "src" / "nexora").resolve()


def imported_from(module) -> Path:
    return Path(module.__file__).resolve().parent


def pytest_configure(config):
    found = imported_from(nexora)
    if found != SOURCE:
        pytest.exit(
            f"these tests are for the interpreter in {SOURCE}, but this Python imports {found}. "
            "Run them with the project environment (nexora/.venv/Scripts/python.exe -m pytest), "
            "or install this tree in the Python you use: pip install -e nexora[dev]",
            returncode=4,
        )

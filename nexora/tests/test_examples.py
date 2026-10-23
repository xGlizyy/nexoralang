"""The programs in examples/ behave exactly as recorded.

Each example is run through the real command, in a separate process, and its standard
output, standard error and exit code are compared with the files in tests/golden/examples/.
The same is done for `nex check`. A change in the language that alters any example makes
these tests fail, so the examples cannot drift away from the implementation.

To accept an intended change, regenerate the recorded files and review the differences:

    NEXORA_UPDATE_GOLDEN=1 python -m pytest tests/test_examples.py
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
GOLDEN = Path(__file__).resolve().parent / "golden" / "examples"

# Exit code of `nex run` and of `nex check` for every example.
EXPECTED = {
    "hello.nex": (0, 0),
    "variables.nex": (0, 0),
    "arithmetic.nex": (0, 0),
    "types.nex": (0, 0),
    "functions.nex": (0, 0),
    "contracts.nex": (0, 0),
    "refined_types.nex": (0, 0),
    "checked_examples.nex": (0, 0),
    "loops.nex": (0, 0),
    "texts.nex": (0, 0),
    "lists.nex": (0, 0),
    "records.nex": (0, 0),
    "option_result.nex": (0, 0),
    "console.nex": (0, 0),
    "files.nex": (0, 0),
    "modules/main.nex": (0, 0),
    # A module is not a program of its own: run alone it has no 'main' to run.
    "modules/models.nex": (1, 1),
    # Rejected by the static analysis: never started.
    "invalid/syntax_error.nex": (1, 1),
    "invalid/name_errors.nex": (1, 1),
    "invalid/type_errors.nex": (1, 1),
    "invalid/refinement_errors.nex": (1, 1),
    # Accepted by the static analysis, fail while running.
    "failing/runtime_error.nex": (3, 0),
    "failing/contract_violation.nex": (5, 0),
    "failing/refinement_violation.nex": (5, 0),
    "failing/loop_measure.nex": (5, 0),
    "failing/parse_number.nex": (5, 0),
}


# Exit code of `nex test` for the examples that have 'example' clauses.
TESTED = {
    "checked_examples.nex": 0,
    "loops.nex": 0,
    "texts.nex": 0,
    "modules/main.nex": 0,
}

# The standard input some examples read, and the permissions others need
# (decision 0015). The examples that use files work on the files of the directory they
# are started in, so that they never write anything inside the repository.
STANDARD_INPUT = {
    "console.nex": "Mundo\n",
}
ARGUMENTS = {
    "files.nex": ("--allow-read=datos", "--allow-write=salida"),
}
OWN_DIRECTORY = {"files.nex"}


@pytest.fixture
def own_directory(tmp_path):
    """A working directory with the files the examples that use them expect."""
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "entradas.txt").write_text("datos de ejemplo\n", encoding="utf-8")
    (tmp_path / "salida").mkdir()
    return tmp_path


def example_path(name: str, directory: Path) -> str:
    """The path of the example, relative when the program runs in the repository."""
    return f"examples/{name}" if directory == ROOT else str(EXAMPLES / name)


def nex(*arguments: str, cwd: Path = ROOT, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nexora", *arguments], capture_output=True, encoding="utf-8", cwd=cwd, input=stdin,
    )


def compare(name: str, actual: str) -> None:
    path = GOLDEN / name
    if os.environ.get("NEXORA_UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
    assert path.exists(), f"missing recorded output {path}; see the top of this file"
    assert actual == path.read_text(encoding="utf-8"), f"output differs from {path.name}"


def test_every_example_is_listed_and_nothing_else():
    found = {path.relative_to(EXAMPLES).as_posix() for path in EXAMPLES.rglob("*.nex")}
    assert found == set(EXPECTED)


def test_every_example_is_described_in_the_examples_readme():
    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED:
        assert f"({name})" in readme, name


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_example_starts_with_a_description(name):
    first = (EXAMPLES / name).read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("// ") and len(first) > 20


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_run(name, own_directory):
    directory = own_directory if name in OWN_DIRECTORY else ROOT
    result = nex("run", example_path(name, directory), *ARGUMENTS.get(name, ()),
                 cwd=directory, stdin=STANDARD_INPUT.get(name, ""))
    slug = name.replace("/", "__").removesuffix(".nex")
    assert result.returncode == EXPECTED[name][0]
    assert "Traceback" not in result.stderr
    compare(f"{slug}.run.stdout", result.stdout)
    compare(f"{slug}.run.stderr", result.stderr)


@pytest.mark.parametrize("name", sorted(TESTED))
def test_nex_test(name):
    result = nex("test", f"examples/{name}")
    slug = name.replace("/", "__").removesuffix(".nex")
    assert result.returncode == TESTED[name]
    compare(f"{slug}.test.stdout", result.stdout)
    compare(f"{slug}.test.stderr", result.stderr)


def test_every_example_with_examples_is_tested():
    with_examples = {name for name in EXPECTED if "    example " in (EXAMPLES / name).read_text(encoding="utf-8")}
    assert with_examples == set(TESTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_check(name):
    # `nex check` does not run the program: it needs no permissions and no working
    # directory of its own.
    result = nex("check", f"examples/{name}")
    slug = name.replace("/", "__").removesuffix(".nex")
    assert result.returncode == EXPECTED[name][1]
    compare(f"{slug}.check.stderr", result.stderr)
    if result.returncode == 0:
        assert result.stdout == f"✓ Check passed: examples/{name}\n"
    else:
        assert result.stdout == ""


@pytest.mark.parametrize("name", [name for name, (run_code, _) in EXPECTED.items() if run_code == 1])
def test_statically_invalid_examples_never_start(name):
    # Same diagnostics from both commands, and no output from the program itself.
    run, check = nex("run", f"examples/{name}"), nex("check", f"examples/{name}")
    assert run.stdout == ""
    assert run.stderr.rsplit("error:", 1)[0] == check.stderr.rsplit("error:", 1)[0]


def test_valid_examples_cover_every_feature_of_the_language():
    # If a keyword or built-in is added to the language, an example has to use it.
    from nexora.checker import BUILTINS
    from nexora.tokens import KEYWORDS

    valid = "\n".join(
        (EXAMPLES / name).read_text(encoding="utf-8") for name, (run_code, _) in EXPECTED.items() if run_code == 0
    )
    code_only = "\n".join(line.split("//")[0] for line in valid.splitlines())
    for word in [*KEYWORDS, *BUILTINS, "result", "Int", "Float", "Bool", "Text", "Void"]:
        assert word in code_only.replace("(", " ").replace(")", " ").replace(":", " ").split(), word

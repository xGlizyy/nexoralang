"""T1-T4 of decision 0019 (8.9): the published 0.11.0 package on the original programs of the
frozen corpus, against this version on the programs `nex migrate` wrote.

| Test | Compared |
|------|----------|
| T1 Structural | The tree of `nex inspect` of 0.11.0 and of this version, after the mapping of 8.4 |
| T2 Behaviour | Exit code, standard output and every diagnostic, by the rules of 8.9.1 |
| T3 Examples | The `status` of every example in `nex test --format json` |
| T4 Text | The bytes outside the edits of 8.5, and that the edits are only those of 8.5.2 |

What makes them independent of what they test: 0.11.0 is the package published on PyPI, pinned
by the hash of its wheel and run in an environment of its own with `python -I`, never the frozen
copy in `nexora.legacy011`. The mapping of 8.4, the edit shapes of 8.5.2 and the comparison of
8.9.1 are written again here, from the decision, without `nexora.migrate`. `nex migrate` is only
used as a command, to write the migrated corpus and to list its edits.

The corpus is the one of 8.9.1, frozen in tests/migration/corpus011. A program enters when 0.11
accepts it (its recorded diagnostics are empty); the others are refused by `nex migrate`, and
belong to T5 and T6 (test_migrate_cli.py). The command each program runs with:

| Program | T2 runs |
|---------|---------|
| An example | `nex run`, with the arguments, standard input and directory it is recorded with |
| A block marked `run` or `fails` | `nex run` |
| A block marked `test` | `nex test` |
| A block with any other marker (`valid`, `body`, `check-json`, `inspect`, `context`…) | `nex check`: the behaviour its marker states is that it passes the check |

The environment is created once, in .equivalence/ (ignored by git), and needs to reach PyPI the
first time. `NEXORA_011_PYTHON` names another Python that already has the package. Setting
`NEXORA_SKIP_EQUIVALENCE=1` skips these tests explicitly, outside continuous integration only: with
`CI` set it fails the run instead. Otherwise a missing environment fails.

The environment is checked before any comparison: the package and its metadata are 0.11.0, every
installed file has the SHA-256 its wheel recorded, and neither this repository (except the
environment itself) nor the environment that runs the tests is on its import path. The pin of the
wheel is checked by pip when the environment is made, and the environment is made again when
tests/migration/nexora-0.11.0.txt changes.
"""

import bisect
import hashlib
import json
import os
import re
import shutil
import site
import subprocess
import sys
import sysconfig
import venv
from ast import literal_eval
from dataclasses import dataclass
from pathlib import Path

import pytest

# The whole module: CI runs it in the job 'equivalence' and leaves it out of the matrix.
pytestmark = pytest.mark.equivalence

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "migration" / "corpus011"
REQUIREMENT = ROOT / "tests" / "migration" / "nexora-0.11.0.txt"
ENVIRONMENT = ROOT / ".equivalence" / "nexora-0.11.0"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))["programs"]

if os.environ.get("NEXORA_SKIP_EQUIVALENCE") == "1":
    if os.environ.get("CI", "").strip().lower() not in ("", "0", "false"):
        # In continuous integration the skip is never silent: it fails the run.
        pytest.fail("NEXORA_SKIP_EQUIVALENCE=1 is not allowed in continuous integration (CI is set): "
                    "the equivalence tests with 0.11.0 must run there", pytrace=False)
    pytest.skip("NEXORA_SKIP_EQUIVALENCE=1: the equivalence tests with 0.11.0 were skipped on purpose",
                allow_module_level=True)


# The corpus and the command of each program

def _mode(program: dict) -> str:
    # `nex test` does not require 'main' (decision 0008); every other command does.
    return "without_main" if program.get("marker") == "test" else "with_main"


ACCEPTED = [program for program in MANIFEST if not program["diagnostics_011"][_mode(program)]]
REFUSED = [program for program in MANIFEST if program["diagnostics_011"][_mode(program)]]


def _commands(program: dict) -> list[tuple[str, list[str], str]]:
    """(command, options, standard input) of T2 for a program."""
    if program["kind"] == "example":
        run = program["run"]
        return [("run", run["arguments"], run["stdin"])]
    if program["marker"] in ("run", "fails"):
        return [("run", [], "")]
    if program["marker"] == "test":
        return [("test", [], "")]
    return [("check", [], "")]


# A module is checked as a file of the program that imports it, not as a program: alone it has no
# 'main', which is why its recorded diagnostics are not empty.
MODULES = {"examples/modules/models.nex": "examples/modules/main.nex"}
PROGRAMS = [program for program in ACCEPTED]
FILES = sorted({program["path"] for program in ACCEPTED} | set(MODULES))


# The two versions

def _requirement_digest() -> str:
    return hashlib.sha256(REQUIREMENT.read_bytes()).hexdigest()


# Written in the environment once the pinned wheel is installed: an environment made for another
# pin, or left half-made, is made again instead of being trusted.
_STAMP = ENVIRONMENT / "nexora-0.11.0.requirement.sha256"


def _old_python() -> Path:
    named = os.environ.get("NEXORA_011_PYTHON")
    if named:
        return Path(named)
    python = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not (python.exists() and _STAMP.exists() and _STAMP.read_text(encoding="utf-8") == _requirement_digest()):
        venv.create(ENVIRONMENT, with_pip=True, clear=True, system_site_packages=False)
        installed = subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-deps",
             "--require-hashes", "--only-binary=:all:", "--no-cache-dir", "-r", str(REQUIREMENT)],
            capture_output=True, encoding="utf-8")
        if installed.returncode != 0:
            shutil.rmtree(ENVIRONMENT, ignore_errors=True)
            pytest.fail("could not install the published nexora-lang 0.11.0 (it needs PyPI the first time; "
                        f"NEXORA_SKIP_EQUIVALENCE=1 skips these tests outside CI):\n{installed.stderr}")
        _STAMP.write_text(_requirement_digest(), encoding="utf-8")
    return python


# Run by the Python of 0.11.0, with -I: what it imports, from where, and whether every installed file
# is still the one its wheel recorded (RECORD keeps the SHA-256 of each file of the wheel).
_PROBE = r"""
import base64, hashlib, importlib.metadata as metadata, json, sys
import nexora
dist = metadata.distribution("nexora-lang")
changed, checked = [], 0
for file in dist.files or ():
    if not file.hash or file.hash.mode != "sha256":
        continue
    digest = base64.urlsafe_b64encode(hashlib.sha256(file.locate().read_bytes()).digest()).rstrip(b"=").decode()
    checked += 1
    if digest != file.hash.value:
        changed.append(str(file))
print(json.dumps({"version": nexora.__version__, "metadata_version": dist.version, "file": nexora.__file__,
                  "path": sys.path, "prefix": sys.prefix, "checked": checked, "changed": changed}))
"""


def _development_places() -> list[Path]:
    """Where the code under development can be imported from: the package directories of the
    environment that runs the tests, the checkout of nexora/ (an editable install points there) and,
    when it is here, the repository around it (npm/python/ holds another copy of the package).

    The standard library of the base Python is not among them: the environment of 0.11.0 is made from
    that Python and shares it legitimately, even when the tests run without a virtual environment and
    the standard library is under their own sys.prefix (as on the runners of GitHub Actions)."""
    places = {Path(site.getusersitepackages()), *(Path(sysconfig.get_paths()[key]) for key in ("purelib", "platlib"))}
    # Only package directories: outside a virtual environment, on Windows, getsitepackages() also
    # names the bare prefix of the base Python, where its standard library is.
    places.update(Path(path) for path in site.getsitepackages() if Path(path).name in ("site-packages", "dist-packages"))
    places.add(ROOT)
    if (ROOT.parent / ".github").is_dir():
        places.add(ROOT.parent)
    return sorted({place.resolve() for place in places})


def _isolation_problems(probe: dict, forbidden: list[Path]) -> list[str]:
    """What the Python of 0.11.0 could import from the code under development, as described by the
    probe: every entry of its import path and the file of the `nexora` it imports. Its own
    environment is allowed, even inside the checkout (.equivalence/), and nothing else that is in
    `forbidden`; the `nexora` it imports has to come from that environment."""
    environment = Path(probe["prefix"]).resolve()
    forbidden = [place.resolve() for place in forbidden]
    problems = []
    for entry in [probe["file"], *probe["path"]]:
        if not entry:
            continue
        resolved = Path(entry).resolve()
        if resolved.is_relative_to(environment):
            continue
        problems += [f"{entry} is inside {place}" for place in forbidden if resolved.is_relative_to(place)]
    if not Path(probe["file"]).resolve().is_relative_to(environment):
        problems.append(f"nexora comes from {probe['file']}, outside the environment of 0.11.0")
    return problems


@pytest.fixture(scope="module")
def old_python() -> Path:
    python = _old_python()
    found = subprocess.run([str(python), "-I", "-c", _PROBE], capture_output=True, encoding="utf-8",
                           cwd=python.parent)
    assert found.returncode == 0, found.stderr
    probe = json.loads(found.stdout)
    # The published package, unmodified: version, metadata and every file against its wheel.
    assert (probe["version"], probe["metadata_version"]) == ("0.11.0", "0.11.0"), probe
    assert probe["checked"] > 0 and probe["changed"] == [], probe
    # Isolated: no package of the environment that runs the tests, and nothing of the checkout, is importable.
    assert _isolation_problems(probe, _development_places()) == [], probe
    if not os.environ.get("NEXORA_011_PYTHON"):
        configuration = (ENVIRONMENT / "pyvenv.cfg").read_text(encoding="utf-8")
        assert re.search(r"^include-system-site-packages\s*=\s*false\s*$", configuration, re.M), configuration
    return python


def nex(python: Path, arguments: list[str], cwd: Path, stdin: str = "") -> tuple[int, str, str]:
    # -I: neither the working directory nor PYTHONPATH reaches the interpreter of either version.
    result = subprocess.run([str(python), "-I", "-m", "nexora", *arguments], cwd=cwd, input=stdin,
                            capture_output=True, encoding="utf-8")
    return result.returncode, result.stdout, result.stderr


NEW_PYTHON = Path(sys.executable)


# The edits, as `nex migrate` lists them

_STRING = r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\""
_EDIT = re.compile(rf"^  (\d+):(\d+)  (E\w+)  ({_STRING}) -> ({_STRING})$")
_EDITS_OF = re.compile(r"^--- (.*): (\d+) edits?$")


@dataclass(frozen=True)
class Edit:
    start: int          # offset in the original text, in characters
    end: int
    kind: str
    before: str
    after: str


def _line_starts(text: str) -> list[int]:
    """The offset of every line; `\\r\\n`, `\\n` and a lone `\\r` each end one (8.5.1)."""
    starts, index = [0], 0
    while index < len(text):
        character = text[index]
        index += 2 if text.startswith("\r\n", index) else 1
        if character in "\r\n":
            starts.append(index)
    return starts


def _decode(data: bytes) -> tuple[str, bool]:
    """The text as nex reads it, and whether it had a byte-order mark (8.5.1)."""
    bom = data.startswith(b"\xef\xbb\xbf")
    return data.decode("utf-8-sig"), bom


def listed_edits(program: Path, cwd: Path) -> dict[str, list[tuple[int, int, str, str, str]]]:
    """The edits `nex migrate` (without --write) lists for every file of a program, by file name."""
    code, out, err = nex(NEW_PYTHON, ["migrate", program.name], cwd)
    assert (code, err) == (0, ""), err
    files: dict[str, list] = {}
    announced: dict[str, int] = {}
    current = None
    for line in out.splitlines():
        heading = _EDITS_OF.match(line)
        if heading:
            current = files.setdefault(Path(heading.group(1)).name, [])
            announced[Path(heading.group(1)).name] = int(heading.group(2))
            continue
        if line.startswith("--- "):
            current = None
            continue
        if current is not None:
            edit = _EDIT.match(line)
            assert edit, f"an edit line that does not read as one: {line!r}"
            current.append((int(edit.group(1)), int(edit.group(2)), edit.group(3),
                            literal_eval(edit.group(4)), literal_eval(edit.group(5))))
    assert {name: len(edits) for name, edits in files.items()} == announced, out
    return files


class Migration:
    """One file: its original text, its edits and how a position of the original moves (8.9.1)."""

    def __init__(self, original: str, listed: list[tuple[int, int, str, str, str]]) -> None:
        self.original = original
        self.old_starts = _line_starts(original)
        self.edits = []
        for line, column, kind, before, after in listed:
            start = self.old_starts[line - 1] + column - 1
            self.edits.append(Edit(start, start + len(before), kind, before, after))
        self.edits.sort(key=lambda edit: (edit.start, edit.end))
        self.migrated = self._apply()
        self.new_starts = _line_starts(self.migrated)

    def _apply(self) -> str:
        parts, position = [], 0
        for edit in self.edits:
            parts += [self.original[position:edit.start], edit.after]
            position = edit.end
        return "".join(parts) + self.original[position:]

    def offset(self, offset: int) -> int:
        """An offset of the original in the migrated text. Inside a replaced range: the start of its
        replacement. At an insertion: after it, as the output is built (8.5.3)."""
        shift = 0
        for edit in self.edits:
            if offset < edit.start:
                break
            if offset < edit.end:
                return edit.start + shift
            shift += len(edit.after) - (edit.end - edit.start)
        return offset + shift

    def position(self, line: int, column: int) -> tuple[int, int]:
        offset = self.offset(self.old_starts[line - 1] + column - 1)
        new_line = bisect.bisect_right(self.new_starts, offset)
        return new_line, offset - self.new_starts[new_line - 1] + 1


# The work: both copies of the corpus, the migrated one written by `nex migrate --write`

@dataclass
class Corpus:
    old: Path
    new: Path
    migrations: dict[str, Migration]       # corpus path -> its migration


def _prepare(directory: Path) -> None:
    shutil.copytree(CORPUS, directory)
    # What tests/test_examples.py gives files.nex in its own directory.
    (directory / "examples" / "datos").mkdir()
    (directory / "examples" / "datos" / "entradas.txt").write_text("datos de ejemplo\n", encoding="utf-8")
    (directory / "examples" / "salida").mkdir()


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Corpus:
    base = tmp_path_factory.mktemp("equivalence")
    old, new = base / "old", base / "new"
    _prepare(old)
    _prepare(new)
    migrations: dict[str, Migration] = {}
    for program in PROGRAMS:
        path = Path(program["path"])
        listed = listed_edits(path, old / path.parent)
        code, _, err = nex(NEW_PYTHON, ["migrate", path.name, "--write"], new / path.parent)
        assert (code, err) == (0, ""), (program["path"], err)
        for name, edits in listed.items():
            key = (path.parent / name).as_posix()
            original, _ = _decode((old / key).read_bytes())
            migrations[key] = Migration(original, edits)
    return Corpus(old, new, migrations)


# The isolation check of the environment of 0.11.0

# The layout of the runners of GitHub Actions: the tests run on the Python of setup-python, not in a
# virtual environment, and the environment of 0.11.0 is made from that same Python.
_BASE = Path("/opt/python/3.12")
_REPOSITORY = Path("/work/nexoralang")
_FORBIDDEN = [_BASE / "lib/python3.12/site-packages", _REPOSITORY / "nexora", _REPOSITORY]


def _probe(environment: Path, file: Path, *path: Path) -> dict:
    return {"prefix": str(environment), "file": str(file), "path": [str(entry) for entry in path]}


def test_the_isolation_check_allows_the_standard_library_of_the_base_python():
    environment = Path("/runner/temp/nexora-0.11.0")
    probe = _probe(environment, environment / "lib/python3.12/site-packages/nexora/__init__.py",
                   _BASE / "lib/python312.zip", _BASE / "lib/python3.12", _BASE / "lib/python3.12/lib-dynload",
                   environment / "lib/python3.12/site-packages")
    assert _isolation_problems(probe, _FORBIDDEN) == []
    # The environment may also be inside the checkout, as .equivalence/ is when the tests make it.
    inside = _REPOSITORY / "nexora/.equivalence/nexora-0.11.0"
    probe = _probe(inside, inside / "lib/python3.12/site-packages/nexora/__init__.py",
                   _BASE / "lib/python3.12", inside / "lib/python3.12/site-packages")
    assert _isolation_problems(probe, _FORBIDDEN) == []


@pytest.mark.parametrize("leak", [
    _BASE / "lib/python3.12/site-packages",           # the packages of the environment of the tests
    _REPOSITORY / "nexora/src",                       # the checkout, where an editable install points
    _REPOSITORY / "npm/python",                       # the copy that the npm package bundles
])
def test_the_isolation_check_refuses_the_code_under_development(leak):
    environment = Path("/runner/temp/nexora-0.11.0")
    good = environment / "lib/python3.12/site-packages/nexora/__init__.py"
    assert _isolation_problems(_probe(environment, good, _BASE / "lib/python3.12", leak), _FORBIDDEN) != []
    # And a nexora imported from there, instead of the one of 0.11.0.
    assert _isolation_problems(_probe(environment, leak / "nexora/__init__.py", _BASE / "lib/python3.12"),
                               _FORBIDDEN) != []


def test_the_places_refused_are_those_of_this_environment_and_not_its_standard_library():
    import nexora

    places = _development_places()
    # The package under development, as this process imports it, is refused.
    assert any(Path(nexora.__file__).resolve().is_relative_to(place) for place in places), (nexora.__file__, places)
    # The standard library of the Python that runs the tests is not.
    standard = Path(sysconfig.get_paths()["stdlib"]).resolve()
    assert not any(standard.is_relative_to(place) for place in places), (standard, places)


# The corpus and what 0.11.0 says of it

def test_the_corpus_is_the_one_of_8_9_1():
    assert len(MANIFEST) == 118
    assert len(ACCEPTED) == 86 and len(REFUSED) == 32
    assert sum(program["kind"] == "example" for program in ACCEPTED) == 21


@pytest.mark.parametrize("program", PROGRAMS, ids=lambda program: program["path"])
def test_the_published_0_11_0_accepts_every_program_of_the_corpus(program, old_python, corpus):
    # The corpus was recorded with the 0.11 front end of commit 1af12a9; G1 is about 0.11.0 itself.
    path = Path(program["path"])
    command = "test" if program.get("marker") == "test" else "check"
    _, out, err = nex(old_python, [command, "--format", "json", path.name], corpus.old / path.parent)
    document = json.loads(out)
    assert document["ok"] is True, (program["path"], document["diagnostics"], err)


@pytest.mark.parametrize("program", REFUSED, ids=lambda program: program["path"])
def test_the_programs_left_out_are_rejected_by_0_11_0_too(program, old_python, corpus):
    path = Path(program["path"])
    command = "test" if program.get("marker") == "test" else "check"
    code, out, _ = nex(old_python, [command, "--format", "json", path.name], corpus.old / path.parent)
    assert json.loads(out)["ok"] is False, program["path"]


# T1: structural equivalence (8.4), on the trees of `nex inspect`

_VOID = {"kind": "TypeRef", "name": "Void", "arguments": [], "qualifier": None}
_CLAUSES = {"requires": "needs", "ensures": "promises", "invariant": "keeps", "decreases": "shrinks"}
_RENAMED = {"unwrap": "value", "unwrap_or": "value_or"}


def _positionless(node):
    if isinstance(node, dict):
        return {key: _positionless(value) for key, value in node.items()
                if key != "span" and not key.endswith("_span")}
    if isinstance(node, list):
        return [_positionless(item) for item in node]
    return node


def _mapped_011(node):
    """A 0.11 tree with the mapping of 8.4 applied."""
    if isinstance(node, list):
        return [_mapped_011(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _mapped_011(value) for key, value in node.items()}
    if node.get("kind") == "Function" and node["return_type"] == _VOID:
        node["return_type"] = None
    if node.get("kind") in ("Contract", "LoopClause"):
        node["clause"] = _CLAUSES[node["clause"]]
    if node.get("kind") == "Call":
        owner, _, name = node["callee"].partition(".")
        if owner in ("Option", "Result") and name in _RENAMED:
            node["callee"] = f"{owner}.{_RENAMED[name]}"
    return node


def _projected_012(node):
    """A 0.12 tree with its header projected onto the two lists of 0.11 (8.4.1). A name is kept
    only when it is not null, so that a name 0.11 cannot have makes the trees differ."""
    if isinstance(node, list):
        return [_projected_012(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _projected_012(value) for key, value in node.items()}
    if node.get("kind") == "Function":
        header = node.pop("header")
        node["contracts"] = [item for item in header if item["kind"] == "Contract"]
        node["examples"] = [item for item in header if item["kind"] == "Example"]
    if node.get("kind") in ("Contract", "LoopClause") and node.get("name") is None:
        node.pop("name", None)
    return node


@pytest.mark.parametrize("file", FILES)
def test_t1_the_trees_are_equal_after_the_mapping(file, old_python, corpus):
    path = Path(file)
    code_old, out_old, _ = nex(old_python, ["inspect", path.name], corpus.old / path.parent)
    code_new, out_new, _ = nex(NEW_PYTHON, ["inspect", path.name], corpus.new / path.parent)
    old, new = json.loads(out_old), json.loads(out_new)
    assert (old["schema"], new["schema"]) == ("nexora.inspect/2", "nexora.inspect/3")
    assert old["program"] is not None and old["complete"] is True
    assert (old["ok"], old["complete"], code_old) == (new["ok"], new["complete"], code_new)
    assert [d["code"] for d in old["diagnostics"]] == [d["code"] for d in new["diagnostics"]]
    # Types included: every expression has the same type in both.
    assert _mapped_011(_positionless(old["program"])) == _projected_012(_positionless(new["program"]))


def test_t1_notices_a_change_the_mapping_does_not_allow():
    tree = {"kind": "Function", "return_type": _VOID, "contracts": [], "examples": [],
            "body": {"kind": "Block", "statements": [{"kind": "Call", "callee": "Option.unwrap", "qualifier": "Option"}]}}
    new = {"kind": "Function", "return_type": None, "header": [],
           "body": {"kind": "Block", "statements": [{"kind": "Call", "callee": "Option.value", "qualifier": "Option"}]}}
    assert _mapped_011(tree) == _projected_012(new)
    named = {**new, "header": [{"kind": "Contract", "clause": "needs", "name": "n", "condition": None, "message": None}]}
    unnamed = {**tree, "contracts": [{"kind": "Contract", "clause": "requires", "condition": None, "message": None}]}
    assert _mapped_011(unnamed) != _projected_012(named)
    other = {**new, "body": {"kind": "Block", "statements": [{"kind": "Call", "callee": "Option.value_or",
                                                               "qualifier": "Option"}]}}
    assert _mapped_011(tree) != _projected_012(other)


# T4: the text outside the edits (G2), and that the edits are those of 8.5.2

_EOL = r"(?:\r\n|\n|\r)"


def _ending_before(text: str, offset: int) -> str:
    """The line ending that ends just before `offset`, or "" when there is none."""
    if text[:offset].endswith("\r\n"):
        return "\r\n"
    return text[offset - 1] if offset and text[offset - 1] in "\r\n" else ""

_SHAPES = {
    "E1": lambda edit, text: (edit.before, edit.after) == ("->", "gives"),
    "E2": lambda edit, text: re.fullmatch(r"[ \t]*->[ \t]*Void", edit.before) and edit.after == "",
    "E3": lambda edit, text: _CLAUSES.get(edit.before) == edit.after,
    "E4": lambda edit, text: (_RENAMED.get(edit.before) == edit.after
                              and re.search(r"\b(Option|Result)\.$", text[:edit.start]) is not None),
    "E5a": lambda edit, text: re.fullmatch(r"[ \t]*\{", edit.before) and edit.after == "",
    "E5b": lambda edit, text: (re.fullmatch(rf"[ \t]*\{{[ \t]*{_EOL}", edit.before) and edit.after == ""
                               and (edit.start == 0 or text[edit.start - 1] in "\r\n")),
    "E5c": lambda edit, text: (re.fullmatch(r"\{[ \t]*", edit.before) and edit.after == ""
                               and text.startswith("//", edit.end)),
    # An insertion at the start of a line, ending with the line ending of the line before it.
    "E6": lambda edit, text: (edit.before == "" and re.fullmatch(rf"[ \t]*\{{{_EOL}", edit.after)
                              and _ending_before(text, edit.start) != ""
                              and edit.after.endswith(_ending_before(text, edit.start))),
    "E7": lambda edit, text: ((edit.after == "" and re.fullmatch(rf"[ \t]*\{{[ \t]*{_EOL}", edit.before)
                               and (edit.start == 0 or text[edit.start - 1] in "\r\n"))
                              or (edit.before == "" and edit.after == " {")),
}


@pytest.mark.parametrize("file", FILES)
def test_t4_only_the_edits_change_and_every_other_byte_is_kept(file, corpus):
    migration = corpus.migrations[file]
    original_bytes = (corpus.old / file).read_bytes()
    written = (corpus.new / file).read_bytes()
    _, bom = _decode(original_bytes)
    assert migration.edits, f"{file}: a 0.11 program of the corpus without edits"
    previous_end = 0
    for edit in migration.edits:
        assert migration.original[edit.start:edit.end] == edit.before, (file, edit)
        assert _SHAPES[edit.kind](edit, migration.original), (file, edit)
        assert edit.start >= previous_end, f"{file}: edits overlap at {edit}"
        previous_end = edit.end
    # The output is the original with the listed edits, and nothing else. It is built here from the
    # original, so the gaps between edits are the original characters; written in UTF-8 with the
    # same mark, they are the same bytes (8.5.4). Comparing with what nex migrate wrote checks both.
    expected = (b"\xef\xbb\xbf" if bom else b"") + migration.migrated.encode("utf-8")
    assert written == expected, file


@pytest.mark.parametrize("kind, before, after, text, start", [
    ("E3", "requires", "promises", "    requires x > 0\n", 4),      # the wrong 0.12 word
    ("E1", "->", "gives ", "fn f() -> Int {\n", 7),                # one more space
    ("E4", "unwrap", "value", "    mine.unwrap(x)\n", 9),           # not after Option. or Result.
    ("E5a", " { x", "", "fn f() -> Int { x\n", 13),                # more than the '{'
    ("E6", "", "{\n", "a\r\n    b\r\n", 3),                        # a line ending the line before does not have
    ("E7", "", "{", "fn f() -> Int\n", 13),                        # the insertion of E7 is ' {'
])
def test_t4_rejects_an_edit_that_8_5_2_does_not_allow(kind, before, after, text, start):
    assert not _SHAPES[kind](Edit(start, start + len(before), kind, before, after), text)


# T2 and T3: behaviour (8.9.1)

# The correspondence of 8.9.1. A clause word is mapped where it names the kind of a clause: quoted
# ('requires') or before the condition it introduces (": requires b != 0.0"). The same word as an
# ordinary noun ("Loop invariant violated", the message of E4005, unchanged in 0.12) is not.
_CLAUSE_KIND = re.compile(r"(?<=')(requires|ensures|invariant|decreases)(?=')|(?<=: )(requires|ensures|invariant|decreases)\b")
_FUNCTIONS = re.compile(r"\b(Option|Result)\.(unwrap_or|unwrap)\b")


def _words(text: str) -> str:
    text = _CLAUSE_KIND.sub(lambda match: _CLAUSES[match.group(0)], text)
    return _FUNCTIONS.sub(lambda match: f"{match.group(1)}.{_RENAMED[match.group(2)]}", text)


_TEXT_FIELDS = ("message", "label", "hint")
_CODE_FIELDS = ("expression", "call")     # text of the program, in nexora.test/1


class Carried:
    """A 0.11 document with every position, line number and clause word carried to the migrated
    program, so that it can be compared with the 0.12 document field by field."""

    def __init__(self, corpus: Corpus, program: Path) -> None:
        self.corpus, self.directory = corpus, program.parent

    def migration(self, file: str | None) -> Migration | None:
        if file is None:
            return None
        return self.corpus.migrations.get((self.directory / file).as_posix())

    def text(self, text: str, migration: Migration | None) -> str:
        text = _words(text)
        if migration is None:
            return text

        def line_and_column(match):
            line, column = migration.position(int(match.group(1)), int(match.group(2)))
            return f"line {line}, column {column}"

        text = re.sub(r"line (\d+), column (\d+)", line_and_column, text)
        return re.sub(r"line (\d+)(?!\d|, column)", lambda match: f"line {migration.position(int(match.group(1)), 1)[0]}",
                      text)

    def document(self, node, file: str | None = None):
        if isinstance(node, list):
            return [self.document(item, file) for item in node]
        if not isinstance(node, dict):
            return node
        file = node.get("file", file)
        migration = self.migration(file)
        node = {key: self.document(value, file) for key, value in node.items()}
        if migration is not None:
            for line, column in (("line", "column"), ("end_line", "end_column")):
                if isinstance(node.get(line), int) and isinstance(node.get(column), int):
                    node[line], node[column] = migration.position(node[line], node[column])
        for key in (*_TEXT_FIELDS, *_CODE_FIELDS):
            if isinstance(node.get(key), str):
                node[key] = self.text(node[key], migration)
        if isinstance(node.get("notes"), list):
            node["notes"] = [self.text(note, migration) for note in node["notes"]]
        node.pop("nexora_version", None)
        return node


def _behaviour(program: dict, command: str, options: list[str], stdin: str, old_python: Path, corpus: Corpus):
    path = Path(program["path"])
    arguments = [command, "--format", "json", *options, path.name]
    old = nex(old_python, arguments, corpus.old / path.parent, stdin)
    new = nex(NEW_PYTHON, arguments, corpus.new / path.parent, stdin)
    return path, old, new


def _document_of(text: str) -> dict | None:
    return json.loads(text) if text else None


T2_CASES = [(program, command, options, stdin) for program in PROGRAMS for command, options, stdin in _commands(program)]


@pytest.mark.parametrize("program, command, options, stdin", T2_CASES,
                         ids=[f"{case[0]['path']}:{case[1]}" for case in T2_CASES])
def test_t2_the_migrated_program_behaves_the_same(program, command, options, stdin, old_python, corpus):
    path, (old_code, old_out, old_err), (new_code, new_out, new_err) = _behaviour(
        program, command, options, stdin, old_python, corpus)
    carried = Carried(corpus, path)
    assert old_code == new_code, (program["path"], old_err, new_err)
    if program["kind"] == "example":
        assert old_code == program["run"]["expected_exit"]
    if command == "run":
        # The output of the program, byte for byte; the diagnostics, as one JSON document on stderr.
        assert old_out == new_out
        old_document, new_document = _document_of(old_err), _document_of(new_err)
    else:
        assert (old_err, new_err) == ("", "")
        old_document, new_document = json.loads(old_out), json.loads(new_out)
    if old_document is None:
        assert new_document is None
        return
    old_document = carried.document(old_document, path.name)
    new_document = {key: value for key, value in new_document.items() if key != "nexora_version"}
    # Code and category in the same order, then every other field: positions carried, words mapped.
    assert [(d["code"], d["category"]) for d in old_document["diagnostics"]] == \
        [(d["code"], d["category"]) for d in new_document["diagnostics"]]
    assert old_document == new_document


def test_t2_carries_a_position_through_the_edits():
    original = "fn f(x: Int) -> Int {\n    requires x > 0\n    return x\n}\n"
    edits = [(1, 14, "E1", "->", "gives"), (1, 20, "E5a", " {", ""), (2, 5, "E3", "requires", "needs"),
             (3, 1, "E6", "", "{\n")]
    migration = Migration(original, edits)
    assert migration.migrated == "fn f(x: Int) gives Int\n    needs x > 0\n{\n    return x\n}\n"
    assert migration.position(3, 5) == (4, 5)            # after the inserted line
    assert migration.position(2, 14) == (2, 11)          # after 'requires' became 'needs'
    assert migration.position(1, 14) == (1, 14)          # inside an edit: the start of its replacement
    assert migration.position(1, 21) == (1, 23)          # inside the deleted ' {'
    assert _words("breaks a 'requires' condition; is false: decreases n - i") == \
        "breaks a 'needs' condition; is false: shrinks n - i"
    assert _words("Loop invariant violated") == "Loop invariant violated"
    assert _words("Option.unwrap_or(x, 0) and Result.unwrap(r)") == "Option.value_or(x, 0) and Result.value(r)"


_EXAMPLES: dict[str, bool] = {}


def _has_examples(file: Path, corpus: Corpus, old_python: Path) -> bool:
    """Whether a function of the program declares an 'example', in the tree of 0.11.0."""
    if file.as_posix() not in _EXAMPLES:
        _, out, _ = nex(old_python, ["inspect", file.name], corpus.old / file.parent)
        _EXAMPLES[file.as_posix()] = any(function["examples"] for function in json.loads(out)["program"]["functions"])
    return _EXAMPLES[file.as_posix()]


@pytest.mark.parametrize("program", PROGRAMS, ids=lambda program: program["path"])
def test_t3_every_example_ends_the_same(program, old_python, corpus):
    path = Path(program["path"])
    if not _has_examples(path, corpus, old_python):
        return      # T3 is for the programs with an 'example'; the count is checked below
    old = nex(old_python, ["test", "--format", "json", path.name], corpus.old / path.parent)
    new = nex(NEW_PYTHON, ["test", "--format", "json", path.name], corpus.new / path.parent)
    assert old[0] == new[0]
    old_document, new_document = json.loads(old[1]), json.loads(new[1])
    assert old_document["status"] == new_document["status"]
    statuses = [[(e["function"], e["index"], e["status"]) for e in d["examples"] or []]
                for d in (old_document, new_document)]
    assert statuses[0] == statuses[1]
    assert statuses[0], f"{program['path']} has examples and none was evaluated"


def test_t3_covers_every_program_with_examples(old_python, corpus):
    with_examples = [program["path"] for program in PROGRAMS
                     if _has_examples(Path(program["path"]), corpus, old_python)]
    assert with_examples == [
        "examples/checked_examples.nex", "examples/loops.nex", "examples/modules/main.nex", "examples/texts.nex",
        "docs/nexora__docs__contracts__006.nex", "docs/nexora__docs__contracts__007.nex",
        "docs/nexora__docs__decisions__0019-identidad-propia-del-lenguaje__000.nex"]

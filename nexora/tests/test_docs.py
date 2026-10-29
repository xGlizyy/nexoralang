"""The documentation says what the implementation does.

Every NEXORA code block in the Markdown files is executed by these tests, and the output
shown next to it is compared, character by character, with what the current interpreter
produces. A code block is tied to a check by an HTML comment on the line before it:

    <!-- nex:run -->            the next `nex` block is a program that runs and exits with 0;
                                the `text` block after it is exactly what it prints
    <!-- nex:fails exit=3 -->   the program fails while running with that exit code;
                                the `text` block is its output followed by the diagnostics
    <!-- nex:check-fails -->    `nex check` rejects the program;
                                the `text` block is exactly the diagnostics
    <!-- nex:check-json -->     the `json` block is exactly the output of `nex check --format json`
    <!-- nex:inspect -->        the `json` block is exactly the output of `nex inspect`
    <!-- nex:context -->        the `text` block is exactly the output of `nex context`
    <!-- nex:context-json -->   the `json` block is exactly the output of `nex context --format json`
    <!-- nex:symbols-json -->   the `json` block is exactly the output of `nex symbols --format json`
    <!-- nex:test exit=6 -->    `nex test` evaluates the examples of the program with that exit code;
                                the `text` block is its standard output followed by its errors
    <!-- nex:valid -->          the program passes `nex check` (no output is shown)
    <!-- nex:body -->           statements that pass `nex check` once placed inside `main`
    <!-- nex:body-fails codes=E2011,E2005 -->
                                statements that, inside `main`, produce exactly those errors

A `nex` block that contains `fn main` and has no marker is an error: a complete program in
the documentation must be checked. Programs are saved as `program.nex`, which is the file
name the documented diagnostics show.

The decisions in docs/decisions/ are records: their programs are written in the syntax of the
version that decided them. Up to 0.11 that syntax is no longer accepted (decision 0019), so a
checked block of a decision is checked with the frozen front end and interpreter of 0.11,
`nexora.legacy011`, and its documented output is compared, character by character, with what
`nex run` of 0.11 printed: the same interpreter and the same rendering of the diagnostics. A
decision is never rewritten, so its expected output is never regenerated either.

After an intended change in the output, rewrite the expected blocks and review the result:

    NEXORA_UPDATE_DOCS=1 python -m pytest tests/test_docs.py
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from nexora import __version__, cli
from nexora.diagnostics import CATEGORIES, CODES
from nexora.legacy011 import diagnostics as diagnostics011
from nexora.legacy011 import interpreter as interpreter011
from nexora.legacy011 import pipeline as pipeline011

from helpers import in_continuous_integration

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
DOCUMENTS = sorted(
    path for path in ROOT.rglob("*.md")
    if not any(part.startswith(".") or part.endswith(".egg-info") for part in path.relative_to(ROOT).parts)
)
MARKER = re.compile(r"<!--\s*nex:([\w-]+)((?:\s+\w+=[\w,]+)*)\s*-->")
FENCE = re.compile(r"^```(\w*)\s*$")
EXPECTS_OUTPUT = {
    "run": "text", "fails": "text", "check-fails": "text", "check-json": "json", "inspect": "json",
    "context": "text", "context-json": "json", "symbols-json": "json", "test": "text",
}
MARKERS = {*EXPECTS_OUTPUT, "valid", "body", "body-fails"}


@dataclass
class Block:
    document: Path
    language: str
    start: int          # index of the first content line
    end: int            # index of the closing fence
    text: str
    marker: str | None = None
    ordinal: int = -1   # position among the checked blocks of its document
    options: dict = field(default_factory=dict)
    expected: "Block | None" = None

    @property
    def label(self) -> str:
        return f"{self.document.relative_to(ROOT).as_posix()}:{self.start}"


def blocks_of(document: Path) -> list[Block]:
    lines = document.read_text(encoding="utf-8").split("\n")
    blocks: list[Block] = []
    pending: tuple[str, dict] | None = None
    waiting: Block | None = None
    index = 0
    while index < len(lines):
        marker = MARKER.search(lines[index])
        fence = FENCE.match(lines[index])
        if marker:
            options = dict(item.split("=") for item in marker.group(2).split())
            pending = (marker.group(1), options)
        elif fence:
            end = index + 1
            while end < len(lines) and lines[end].rstrip() != "```":
                end += 1
            block = Block(document, fence.group(1), index + 1, end, "\n".join(lines[index + 1:end]))
            if block.language == "nex":
                if pending:
                    block.marker, block.options = pending
                waiting = block if block.marker in EXPECTS_OUTPUT else None
            elif waiting is not None and block.language == EXPECTS_OUTPUT[waiting.marker]:
                # The expected output is the first block of the right kind after the program;
                # a `bash` block showing the command may sit in between.
                waiting.expected = block
                waiting = None
            pending = None
            blocks.append(block)
            index = end
        index += 1
    for ordinal, block in enumerate(block for block in blocks if block.marker):
        block.ordinal = ordinal
    return blocks


ALL_BLOCKS = [block for document in DOCUMENTS for block in blocks_of(document)]
CHECKED = [block for block in ALL_BLOCKS if block.marker]


def execute(command: list[str], source: str, tmp_path, monkeypatch, capsys) -> tuple[int, str, str]:
    (tmp_path / "program.nex").write_text(source + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    code = cli.main([*command[:1], "program.nex", *command[1:]])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def in_main(body: str) -> str:
    return "fn main() {\n" + "\n".join(f"    {line}" for line in body.split("\n")) + "\n}"


def assert_expected(block: Block, actual: str) -> None:
    expected = block.expected
    assert expected is not None and expected.language == EXPECTS_OUTPUT[block.marker], (
        f"{block.label}: a `{EXPECTS_OUTPUT[block.marker]}` block with the expected output must follow"
    )
    actual = "\n".join(line.rstrip() for line in actual.strip("\n").split("\n"))
    if os.environ.get("NEXORA_UPDATE_DOCS") and expected.text != actual:
        # The document is parsed again: an earlier rewrite in this same run may have moved
        # every line after it, so the positions recorded at collection time cannot be trusted.
        fresh = [candidate for candidate in blocks_of(block.document) if candidate.marker][block.ordinal].expected
        lines = block.document.read_text(encoding="utf-8").split("\n")
        lines[fresh.start:fresh.end] = actual.split("\n")
        block.document.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        pytest.skip(f"{block.label}: expected output rewritten; run the tests again")
    assert expected.text == actual, f"{block.label}: the documented output is not what NEXORA produces"


def run_0_11(source: str) -> tuple[int, str]:
    """What `nex run program.nex` of 0.11 exits with and writes (standard output, then errors)."""
    file = diagnostics011.Source("program.nex", source + "\n")
    analysis = pipeline011.analyze(file)
    assert analysis.ok, [(d.code, d.label) for d in analysis.diagnostics]
    printed: list[str] = []
    try:
        interpreter011.run(analysis.checked, printed.append)
    except diagnostics011.NexoraRuntimeError as error:
        contract = error.diagnostic.category == diagnostics011.CONTRACT
        summary = "a contract was broken" if contract else "of a runtime error"
        report = f"{diagnostics011.render(error.diagnostic, file)}\n\nerror: program.nex: the program stopped because {summary}\n"
        return (5 if contract else 3), "".join(printed) + report
    return 0, "".join(printed)


def check_record_of_0_11(block: Block) -> None:
    """A checked block of a decision, with the frozen front end and interpreter of 0.11."""
    assert block.marker in ("run", "fails", "valid", "check-fails"), f"{block.label}: nex:{block.marker}"
    analysis = pipeline011.analyze(diagnostics011.Source("program.nex", block.text + "\n"))
    assert analysis.ok is (block.marker != "check-fails"), f"{block.label}: {analysis.diagnostics}"
    if block.marker in ("run", "fails"):
        code, output = run_0_11(block.text)
        assert code == int(block.options.get("exit", 0)), f"{block.label}: exit code {code}"
        assert block.expected is not None, f"{block.label}: a `text` block with the expected output must follow"
        actual = "\n".join(line.rstrip() for line in output.strip("\n").split("\n"))
        assert block.expected.text == actual, f"{block.label}: the record is not what NEXORA 0.11 produced"


def test_the_documentation_has_checked_examples():
    assert len(CHECKED) >= 40
    assert {block.marker for block in CHECKED} == MARKERS


def test_every_normative_language_section_has_an_executable_example():
    """Stable subject areas in the spec always have a checked example anchoring their rules."""
    spec = ROOT / "docs" / "language-spec.md"
    lines = spec.read_text(encoding="utf-8").splitlines()
    sections = []
    for block in blocks_of(spec):
        if not block.marker:
            continue
        section = None
        for line in lines[:block.start]:
            match = re.match(r"^## (\d+)\.", line)
            if match:
                section = int(match.group(1))
        if section is not None:
            sections.append(section)
    required = set(range(2, 13))
    assert required <= set(sections), f"sections without an executable example: {sorted(required - set(sections))}"


def test_language_spec_is_normative_and_the_design_document_is_a_draft():
    spec = (ROOT / "docs" / "language-spec.md").read_text(encoding="utf-8")
    draft = (ROOT.parent / "docs" / "fase-1-diseno.md").read_text(encoding="utf-8")
    assert "normative for the NEXORA 0.13 language" in spec
    assert "This specification takes precedence over the draft" in spec
    assert "Status: historical design draft" in draft
    assert "[language specification](../nexora/docs/language-spec.md)" in draft


def test_ebnf_capability_declarations_cover_every_host_operation():
    spec = (ROOT / "docs" / "language-spec.md").read_text(encoding="utf-8")
    uses = re.search(r"^uses_decl\s*=\s*(.+)$", spec, flags=re.M)
    assert uses is not None
    assert set(re.findall(r'"(read|write|network|process)"', uses.group(1))) == {
        "read", "write", "network", "process",
    }


def test_every_marker_is_known():
    for block in CHECKED:
        assert block.marker in MARKERS, f"{block.label}: unknown marker nex:{block.marker}"


def test_every_complete_program_in_the_documentation_is_checked():
    unchecked = [block.label for block in ALL_BLOCKS
                 if block.language == "nex" and "fn main" in block.text and not block.marker]
    assert unchecked == []


@pytest.mark.parametrize("block", CHECKED, ids=lambda block: block.label)
def test_documented_example(block, tmp_path, monkeypatch, capsys):
    run = lambda *command: execute(list(command), source, tmp_path, monkeypatch, capsys)  # noqa: E731
    source = block.text

    if DECISIONS in block.document.parents:
        check_record_of_0_11(block)
        return
    if block.marker == "run":
        code, out, err = run("run")
        assert (code, err) == (0, ""), f"{block.label}: {err}"
        assert_expected(block, out)
    elif block.marker == "fails":
        assert run("check")[0] == 0, f"{block.label}: must pass the static check and fail only when run"
        code, out, err = run("run")
        assert code == int(block.options["exit"]), f"{block.label}: exit code {code}"
        assert_expected(block, out + err)
    elif block.marker == "check-fails":
        code, out, err = run("check")
        assert (code, out) == (1, ""), block.label
        assert_expected(block, err)
    elif block.marker == "check-json":
        code, out, err = run("check", "--format", "json")
        assert err == "", block.label
        assert_expected(block, out)
    elif block.marker == "inspect":
        code, out, err = run("inspect")
        assert err == "", block.label
        assert_expected(block, out)
    elif block.marker in ("context", "context-json", "symbols-json"):
        command = block.marker.split("-")[0]
        code, out, err = run(command, *(["--format", "json"] if block.marker.endswith("json") else []))
        assert err == "", block.label
        assert_expected(block, out)
    elif block.marker == "test":
        code, out, err = run("test")
        assert code == int(block.options["exit"]), f"{block.label}: exit code {code}: {err}"
        assert_expected(block, out + err)
    elif block.marker == "valid":
        code, out, err = run("check")
        assert code == 0, f"{block.label}: {err}"
    elif block.marker == "body":
        source = in_main(block.text)
        code, out, err = run("check")
        assert code == 0, f"{block.label}: {err}"
    elif block.marker == "body-fails":
        source = in_main(block.text)
        code, out, err = run("check")
        found = set(re.findall(r"error\[(E\d{4})\]", err))
        assert code == 1 and found == set(block.options["codes"].split(",")), f"{block.label}: found {sorted(found)}"


# Cross-references

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_relative_links_point_to_files_that_exist(document):
    text = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.S)
    # A link that leaves nexora/ points into the rest of the repository (the VS Code extension, for
    # one), which a source distribution does not carry. It is checked whenever the repository is
    # there, and always in continuous integration; anywhere else the skip names it.
    repository = (ROOT.parent / ".github").is_dir()
    unchecked = []
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = (document.parent / target.split("#")[0]).resolve()
        if not path.exists() and not path.is_relative_to(ROOT) and not repository and not in_continuous_integration():
            unchecked.append(target)
            continue
        assert path.exists(), f"{document.name}: broken link {target}"
    if unchecked:
        pytest.skip(f"{document.name}: every link inside nexora/ exists; not checked, because the repository "
                    f"around nexora/ is not here: {', '.join(unchecked)}")


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_links_to_headings_point_to_headings_that_exist(document):
    def anchors(path: Path) -> set[str]:
        found = set()
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for heading in re.findall(r"^#+\s+(.*)$", text, flags=re.M):
            slug = re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
            found.add(slug)
        # An explicit anchor on its own line keeps an old link working after a heading is renamed.
        found.update(re.findall(r'^<a id="([\w-]+)"></a>$', text, flags=re.M))
        return found

    text = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.S)
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:")) or "#" not in target:
            continue
        file_part, anchor = target.split("#", 1)
        path = (document.parent / file_part).resolve() if file_part else document
        if path.suffix == ".md":
            assert anchor in anchors(path), f"{document.name}: no heading for {target}"


def test_documents_are_reachable_from_the_index():
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    for path in (ROOT / "docs").glob("*.md"):
        if path.name != "index.md":
            assert f"({path.name})" in index, f"docs/index.md does not link to {path.name}"


# Facts that are stated in more than one place

def test_the_version_in_the_documentation_is_the_version_of_the_package():
    for name in ("README.md", "docs/language-spec.md", "docs/cli-reference.md", "docs/installation.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        mentioned = {
            *re.findall(r"NEXORA (\d+\.\d+\.\d+)", text),
            *re.findall(r"`nexora` (\d+\.\d+\.\d+)", text),
            *re.findall(r"nexora-(\d+\.\d+\.\d+)", text),
        }
        assert mentioned <= {__version__}, f"{name} mentions {mentioned}"
    assert f"NEXORA {__version__}" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_cli_reference_documents_every_command_option_and_exit_code():
    reference = (ROOT / "docs" / "cli-reference.md").read_text(encoding="utf-8")
    parser = cli._build_parser()
    subcommands = next(action for action in parser._actions if hasattr(action, "choices") and action.choices)
    for name, subparser in subcommands.choices.items():
        assert f"`nex {name}" in reference, name
        for action in subparser._actions:
            for option in action.option_strings:
                if option.startswith("--") and option != "--help":
                    assert f"`{option}" in reference or f"{option} " in reference, f"{name} {option}"
            for choice in action.choices or ():
                assert f"`{choice}`" in reference, f"{name}: {choice}"
    for name, value in vars(cli).items():
        if name.startswith("EXIT_"):
            assert f"| `{value}` |" in reference, name
    assert "NEXORA_DEBUG" in reference


def test_exit_codes_are_the_same_everywhere():
    def table(name: str) -> set[str]:
        return set(re.findall(r"^\| `(\d+)` \|", (ROOT / name).read_text(encoding="utf-8"), flags=re.M))

    expected = {str(value) for name, value in vars(cli).items() if name.startswith("EXIT_")}
    assert table("docs/cli-reference.md") == expected
    assert table("docs/language-spec.md") >= expected
    for code in expected:
        assert re.search(rf"^\s+{code}\s", cli._EPILOG, flags=re.M), code


def test_the_diagnostics_guide_explains_every_code():
    guide = (ROOT / "docs" / "diagnostics.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| `([EW]\d{4})` \| ([^|]+?) \|", guide, flags=re.M))
    assert rows == CODES
    for category in set(CATEGORIES.values()):
        assert f"`{category}`" in guide, category


def test_planned_features_are_not_presented_as_working():
    # Words reserved for the future must not appear in a code block that is checked as valid.
    from nexora.tokens import RESERVED_WORDS

    for block in CHECKED:
        if block.marker in ("run", "valid", "body", "fails"):
            code = "\n".join(line.split("//")[0] for line in block.text.split("\n"))
            code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
            used = set(re.findall(r"[A-Za-z_]\w*", code)) & RESERVED_WORDS
            assert used == set(), f"{block.label} uses {used}"

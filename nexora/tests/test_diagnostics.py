import re
from pathlib import Path

import pytest

from nexora.diagnostics import CATEGORIES, CODES, Diagnostic, Source, Span, render
from nexora.pipeline import analyze

SPEC = Path(__file__).resolve().parents[1] / "docs" / "language-spec.md"


def rendered(text: str, name: str = "hello.nex") -> list[str]:
    source = Source(name, text)
    return [render(diagnostic, source) for diagnostic in analyze(source).diagnostics]


def test_render_shows_severity_code_file_position_line_and_caret():
    (output,) = rendered('fn main() -> Void {\n    print("hi")\n    let = "Hello"\n}\n')
    assert output == "\n".join([
        "syntax error[E1101]: Unexpected token",
        " --> hello.nex:3:9",
        "  |",
        '3 |     let = "Hello"',
        "  |         ^ Expected a variable name after 'let', found '='",
    ])


def test_caret_underlines_the_whole_span():
    (output,) = rendered("fn main() -> Void {\n    print(total)\n}\n")
    lines = output.splitlines()
    assert lines[3] == "2 |     print(total)"
    assert lines[4].startswith("  |           ^^^^^ ")


def test_notes_and_hints_follow_the_code():
    (output,) = rendered("fn main() -> Void {\n    let x = 1\n    let x = 2\n}\n")
    assert output.splitlines()[5:] == [
        "  = note: It was first declared at line 2, column 9.",
        "  = hint: Choose a different name: a visible name cannot be declared again.",
    ]


def test_gutter_grows_with_the_line_number():
    text = "fn main() -> Void {\n" + "    print(1)\n" * 9 + "    print(x)\n}\n"
    (output,) = rendered(text)
    assert output.splitlines()[1:5] == [
        "  --> hello.nex:11:11",
        "   |",
        "11 |     print(x)",
        "   |           ^ There is no variable named 'x' here",
    ]


def test_caret_lines_up_under_tabs():
    (output,) = rendered("fn main() -> Void {\n\tprint(x)\n}\n")
    lines = output.splitlines()
    assert lines[3] == "2 | \tprint(x)"
    assert lines[4].startswith("  | \t      ^ ")


def test_diagnostic_without_a_position():
    (output,) = rendered("")
    assert output.splitlines()[:3] == [
        "semantic error[E2001]: Missing main function",
        " --> hello.nex",
        "  = This program has no 'main' function, so there is nothing to run",
    ]


def test_error_at_the_end_of_the_file():
    (output,) = rendered("fn main() -> Void {\n    print(1)")
    lines = output.splitlines()
    assert lines[1] == " --> hello.nex:2:13"
    assert lines[4].startswith("  |             ^ Expected '}'")


def test_reported_position_matches_the_source_text():
    source = Source("t.nex", 'fn main() -> Void {\n    let a = 1\n\n    let b = a + "x"\n}\n')
    (diagnostic,) = analyze(source).diagnostics
    span = diagnostic.span
    assert source.line_text(span.line)[span.column - 1:span.end_column - 1] == "+"


def test_to_dict_is_complete_and_json_friendly():
    diagnostic = Diagnostic("E2005", "There is no variable named 'x' here", Span(2, 11, 2, 12), "Declare it first with 'let'.")
    assert diagnostic.to_dict("a.nex") == {
        "severity": "error",
        "category": "semantic",
        "code": "E2005",
        "message": "Unknown variable",
        "label": "There is no variable named 'x' here",
        "hint": "Declare it first with 'let'.",
        "notes": [],
        "file": "a.nex",
        "line": 2,
        "column": 11,
        "end_line": 2,
        "end_column": 12,
    }
    assert Diagnostic("E2001", "no main").to_dict("a.nex")["line"] is None


def test_every_code_is_documented_in_the_spec_with_the_same_title_and_category():
    rows = re.findall(r"^\| `(E\d{4})` \| ([^|]+?) \| `(\w+)` \|", SPEC.read_text(encoding="utf-8"), re.MULTILINE)
    assert {code: title for code, title, _ in rows} == CODES
    assert {code: category for code, _, category in rows} == CATEGORIES


@pytest.mark.parametrize("text, header", [
    ("fn main() -> Void {\n    let x = @\n}", "lexical error[E1001]: Unexpected character"),
    ("fn main() -> Void {\n    let = 1\n}", "syntax error[E1101]: Unexpected token"),
    ("fn main() -> Void {\n    print(x)\n}", "semantic error[E2005]: Unknown variable"),
    ('fn main() -> Void {\n    let x: Int = "a"\n}', "type error[E2011]: Type mismatch"),
])
def test_the_header_names_the_kind_of_problem(text, header):
    (output,) = rendered(text)
    assert output.splitlines()[0] == header


def test_every_category_has_a_stage_and_codes_follow_their_ranges():
    prefixes = {"file": "E0", "lexical": "E10", "syntax": "E11", "semantic": "E2", "type": "E2",
                "runtime": "E3", "contract": "E4", "test": "E4"}
    assert set(CATEGORIES.values()) == set(prefixes)
    for code, category in CATEGORIES.items():
        assert code.startswith(prefixes[category]), code


def test_every_code_in_the_source_is_registered():
    package = Path(__file__).resolve().parents[1] / "src" / "nexora"
    used = set()
    for path in package.glob("*.py"):
        used.update(re.findall(r'"(E\d{4})"', path.read_text(encoding="utf-8")))
    assert used == set(CODES)

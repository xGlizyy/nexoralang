"""Source positions and diagnostics shared by every stage.

A diagnostic is plain data (code, position, label, hint, notes) so it can be rendered
as text for people or serialised as JSON for tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINE_BREAK = re.compile(r"\r\n|\n|\r")


@dataclass(frozen=True)
class Span:
    """A region of source text. Lines and columns start at 1; the end is exclusive.

    Columns count Unicode code points, and a tab counts as one column.
    """

    line: int
    column: int
    end_line: int
    end_column: int

    def to(self, other: Span) -> Span:
        """The span from the start of this one to the end of `other`."""
        return Span(self.line, self.column, other.end_line, other.end_column)


class Source:
    """A program's text together with the name it is reported under."""

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text
        self._lines = _LINE_BREAK.split(text)

    def line_text(self, line: int) -> str:
        if 1 <= line <= len(self._lines):
            return self._lines[line - 1]
        return ""

    def text_of(self, span: Span) -> str:
        """The source text a span covers, exactly as it was written."""
        if span.line == span.end_line:
            return self.line_text(span.line)[span.column - 1:span.end_column - 1]
        lines = [self.line_text(span.line)[span.column - 1:]]
        lines.extend(self.line_text(number) for number in range(span.line + 1, span.end_line))
        lines.append(self.line_text(span.end_line)[:span.end_column - 1])
        return "\n".join(lines)


# The most errors one stage reports for one file. Past this point more errors do not help
# anyone, and a file that is not NEXORA at all could produce one per character or per line.
MAX_DIAGNOSTICS = 100

# Categories: which stage found the problem, and therefore what kind of problem it is.
FILE = "file"            # the file could not be loaded
LEXICAL = "lexical"      # the text contains something that is not a NEXORA token
SYNTAX = "syntax"        # the tokens do not follow the grammar
SEMANTIC = "semantic"    # names, scopes and program structure, checked without running
TYPE = "type"            # types, checked without running
RUNTIME = "runtime"      # depends on the values computed while the program runs
CONTRACT = "contract"    # a rule the program declares was broken while running: a 'requires' or
                         # 'ensures' condition, or the condition of a refined type
TEST = "test"            # an 'example' evaluated by `nex test` turned out false

# Every diagnostic code: its title and its category. A code never changes meaning; a code that
# stops being used is retired, not reused (E1104 and E2003 are retired, see the spec).
# docs/language-spec.md documents the same table, and tests/test_diagnostics.py checks that
# the two stay in sync.
_REGISTRY: dict[str, tuple[str, str]] = {
    "E0001": ("Cannot read file", FILE),
    "E0002": ("File is not valid UTF-8", FILE),

    "E1001": ("Unexpected character", LEXICAL),
    "E1002": ("Unterminated string", LEXICAL),
    "E1003": ("Invalid escape sequence", LEXICAL),
    "E1004": ("Invalid number literal", LEXICAL),
    "E1005": ("Unescaped '{' in string", LEXICAL),

    "E1101": ("Unexpected token", SYNTAX),
    "E1102": ("Unclosed block", SYNTAX),
    "E1103": ("Reserved word", SYNTAX),
    "E1105": ("Expression too deeply nested", SYNTAX),
    "E1106": ("Misplaced contract clause", SYNTAX),

    "E2001": ("Missing main function", SEMANTIC),
    "E2002": ("Duplicate function", SEMANTIC),
    "E2004": ("Invalid return type", TYPE),
    "E2005": ("Unknown variable", SEMANTIC),
    "E2006": ("Name already declared", SEMANTIC),
    "E2007": ("Cannot reassign variable", SEMANTIC),
    "E2008": ("Unknown function", SEMANTIC),
    "E2009": ("Wrong number of arguments", TYPE),
    "E2010": ("Unused value", SEMANTIC),
    "E2011": ("Type mismatch", TYPE),
    "E2012": ("Invalid type", TYPE),
    "E2013": ("Invalid parameter", SEMANTIC),
    "E2014": ("Missing return", SEMANTIC),
    "E2015": ("Unreachable code", SEMANTIC),
    "E2016": ("Invalid type declaration", SEMANTIC),
    "E2017": ("Value outside refined type", TYPE),
    "E2018": ("Invalid refinement condition", SEMANTIC),
    "E2019": ("Too many refinement checks", SEMANTIC),
    "E2020": ("Example without its function", SEMANTIC),
    "E2021": ("Missing loop measure", SEMANTIC),

    "E3001": ("Division by zero", RUNTIME),
    "E3002": ("Integer overflow", RUNTIME),
    "E3003": ("Float result out of range", RUNTIME),
    "E3004": ("Too many nested calls", RUNTIME),
    "E3005": ("Conversion out of range", RUNTIME),
    "E3006": ("Text too long", RUNTIME),
    "E3007": ("Out of memory", RUNTIME),

    "E4001": ("Precondition violated", CONTRACT),
    "E4002": ("Postcondition violated", CONTRACT),
    "E4003": ("Refinement violated", CONTRACT),
    "E4005": ("Loop invariant violated", CONTRACT),
    "E4006": ("Loop measure did not decrease", CONTRACT),

    "E4004": ("Example failed", TEST),
}

CODES: dict[str, str] = {code: title for code, (title, _) in _REGISTRY.items()}
CATEGORIES: dict[str, str] = {code: category for code, (_, category) in _REGISTRY.items()}


@dataclass(frozen=True)
class Diagnostic:
    """One problem found in a program."""

    code: str
    label: str
    span: Span | None = None
    hint: str | None = None
    notes: tuple[str, ...] = ()
    severity: str = "error"

    @property
    def message(self) -> str:
        return CODES[self.code]

    @property
    def category(self) -> str:
        return CATEGORIES[self.code]

    def to_dict(self, file: str) -> dict:
        """JSON-friendly form. Position fields are null when the problem has no position."""
        span = self.span
        return {
            "severity": self.severity,
            "category": self.category,
            "code": self.code,
            "message": self.message,
            "label": self.label,
            "hint": self.hint,
            "notes": list(self.notes),
            "file": file,
            "line": span.line if span else None,
            "column": span.column if span else None,
            "end_line": span.end_line if span else None,
            "end_column": span.end_column if span else None,
        }


def render(diagnostic: Diagnostic, source: Source) -> str:
    """Formats a diagnostic for a terminal, quoting the offending line.

        syntax error[E1101]: Unexpected token
         --> hello.nex:3:9
          |
        3 |     let = "Hello"
          |         ^ Expected a variable name after 'let', found '='
    """
    lines = [f"{diagnostic.category} {diagnostic.severity}[{diagnostic.code}]: {diagnostic.message}"]
    span = diagnostic.span

    if span is None:
        lines.append(f" --> {source.name}")
        lines.append(f"  = {diagnostic.label}")
    else:
        text = source.line_text(span.line)
        number = str(span.line)
        gutter = " " * len(number)
        if span.end_line == span.line:
            width = span.end_column - span.column
        else:
            width = len(text) - span.column + 1
        # Tabs are copied into the padding so the caret lines up however wide the terminal draws them.
        padding = "".join("\t" if char == "\t" else " " for char in text[: span.column - 1])
        padding = padding.ljust(span.column - 1)

        lines.append(f"{gutter}--> {source.name}:{span.line}:{span.column}")
        lines.append(f"{gutter} |")
        lines.append(f"{number} | {text}")
        lines.append(f"{gutter} | {padding}{'^' * max(1, width)} {diagnostic.label}")
        gutter_note = f"{gutter} "
        lines.extend(f"{gutter_note}= note: {note}" for note in diagnostic.notes)
        if diagnostic.hint:
            lines.append(f"{gutter_note}= hint: {diagnostic.hint}")
        return "\n".join(lines)

    lines.extend(f"  = note: {note}" for note in diagnostic.notes)
    if diagnostic.hint:
        lines.append(f"  = hint: {diagnostic.hint}")
    return "\n".join(lines)


class NexoraRuntimeError(Exception):
    """A NEXORA program failed while running. Carries the diagnostic to show."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.label)
        self.diagnostic = diagnostic

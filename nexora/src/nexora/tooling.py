"""Analysis tools for programs that work with NEXORA code: editors, scripts, AI agents.

This is the public, programmatic interface of NEXORA's static analysis. The `nex check`,
`nex inspect`, `nex context` and `nex symbols` commands, and the optional MCP server, are
thin layers over the functions below, so they all return exactly the same data.

    from nexora.tooling import check_source, inspect_source, get_context, get_symbols

Three rules hold for every function here:

* **Nothing is executed.** The source goes through the lexer, the parser and the checker,
  never through the interpreter.
* **Nothing is guessed.** Every fact comes from that analysis. What the analysis could not
  establish is reported as `null` or left out, never filled in.
* **No file is opened** on behalf of the caller. Functions take source text; `filename` is
  only the name shown in the results. (The one exception is `get_language_spec`, which
  reads the specification that ships with the project, and nothing else.)

Each function returns a plain dictionary, ready for `json.dumps`, that starts with a
`schema` field naming its format and version. The formats are described in
docs/json-protocol.md and, as JSON Schema, in docs/schemas/.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import ast_nodes as ast
from .checker import BUILTINS, MAX_REFINEMENT_STEPS, CheckedProgram, Signature
from .diagnostics import CATEGORIES, CODES, MAX_DIAGNOSTICS, Source, Span
from .interpreter import MAX_CALL_DEPTH
from .parser import MAX_EXPRESSION_DEPTH, MAX_NESTING
from .pipeline import Analysis, analyze
from .prelude import CONTRACTS, IMPLEMENTATIONS, requirements
from .tokens import KEYWORDS, RESERVED_WORDS, TokenType
from .values import INT, INT_MAX, INT_MIN, TEXT, VALUE_TYPES, VOID
from .version import __version__

DIAGNOSTICS_SCHEMA = "nexora.diagnostics/1"
INSPECT_SCHEMA = "nexora.inspect/2"
SYMBOLS_SCHEMA = "nexora.symbols/1"
CONTEXT_SCHEMA = "nexora.context/1"
SPEC_SCHEMA = "nexora.spec/1"
CAPABILITIES_SCHEMA = "nexora.capabilities/1"

DEFAULT_FILENAME = "source.nex"

# The specification that ships with a source checkout of the project.
_SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "language-spec.md"


class ToolingError(ValueError):
    """A request to the tooling that cannot be answered (an unknown section, for instance).
    `code` is a stable identifier; the message is for people."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# Shared pieces

def _span(span: Span | None) -> dict | None:
    return ast.to_dict(span) if span is not None else None


def _header(schema: str, filename: str, diagnostics) -> dict:
    return {
        "schema": schema,
        "nexora_version": __version__,
        "file": filename,
        "ok": not diagnostics,
        "diagnostics": [diagnostic.to_dict(filename) for diagnostic in diagnostics],
    }


def diagnostics_document(filename: str, diagnostics) -> dict:
    """The `nexora.diagnostics/1` document for a list of diagnostics."""
    return _header(DIAGNOSTICS_SCHEMA, filename, tuple(diagnostics))


def _signature_text(function: ast.Function) -> str:
    params = ", ".join(f"{param.name}: {param.type.name}" for param in function.params)
    return f"fn {function.name}({params}) -> {function.return_type.name}"


def _text_of(source: Source, span: Span) -> str:
    """The source text a span covers, exactly as it was written."""
    return source.text_of(span)


# check and inspect

def check_source(source: str, filename: str = DEFAULT_FILENAME) -> dict:
    """Static analysis of a program: syntax, names, scopes, types and return paths.

    Returns a `nexora.diagnostics/1` document. `ok` is true when there are no diagnostics.
    """
    return diagnostics_document(filename, analyze(Source(filename, source)).diagnostics)


def inspect_document(analysis: Analysis) -> dict:
    document = _header(INSPECT_SCHEMA, analysis.source.name, analysis.diagnostics)
    document["complete"] = analysis.complete
    document["program"] = None if analysis.program is None else ast.to_dict(analysis.program, analysis.types)
    return document


def inspect_source(source: str, filename: str = DEFAULT_FILENAME) -> dict:
    """The syntax tree of a program, with the type of every expression the checker could type.

    Returns a `nexora.inspect/2` document. With syntax errors the tree is partial and
    `complete` is false: the statements with errors, and the functions whose declaration has
    them, are missing. `program` is null when the text has lexical errors.
    """
    return inspect_document(analyze(Source(filename, source)))


# Symbols

def _symbol_entries(facts: CheckedProgram) -> list[dict]:
    entries = []
    for symbol in facts.symbols:
        entry = {
            "name": symbol.name,
            "category": symbol.category,
            "type": symbol.type,
            "function": symbol.function,
            "declaration": _span(symbol.span),
            "scope": _span(symbol.scope),
            "references": [_span(reference) for reference in symbol.references],
            "mutable": symbol.mutable,
            "assignments": [_span(assignment) for assignment in symbol.assignments],
        }
        if symbol.category == "function":
            declaration = facts.functions[symbol.name]
            entry["signature"] = _signature_text(declaration)
            entry["params"] = [{"name": param.name, "type": param.type.name} for param in declaration.params]
            entry["return_type"] = declaration.return_type.name
        entries.append(entry)
    return entries


def _builtin_entries() -> list[dict]:
    def describe(signature: Signature) -> dict:
        return {
            "name": signature.name,
            "signature": signature.describe(),
            "params": [{"name": name, "type": kind} for name, kind in signature.params],
            "return_type": signature.return_type,
            # Decision 0011, 7.4: an agent must not take an `ensures` for something checked.
            "contracts": [
                {"clause": contract.clause, "condition": contract.source, "message": contract.message,
                 "checked_at_run_time": contract.checked_at_run_time}
                for contract in CONTRACTS.get(signature.name, ())
            ],
        }
    return [describe(BUILTINS[name]) for name in sorted(BUILTINS)]


def symbols_document(analysis: Analysis, *, name: str | None = None, function: str | None = None) -> dict:
    document = _header(SYMBOLS_SCHEMA, analysis.source.name, analysis.diagnostics)
    document["complete"] = analysis.complete
    document["filter"] = {"name": name, "function": function}
    if analysis.facts is None:
        document["symbols"] = None
    else:
        entries = _symbol_entries(analysis.facts)
        if name is not None:
            entries = [entry for entry in entries if entry["name"] == name]
        if function is not None:
            entries = [
                entry for entry in entries
                if entry["function"] == function or (entry["category"] == "function" and entry["name"] == function)
            ]
        document["symbols"] = entries
    # The functions the language itself provides. They have no declaration in the file.
    document["builtins"] = _builtin_entries()
    return document


def get_symbols(source: str, filename: str = DEFAULT_FILENAME, *, name: str | None = None,
                function: str | None = None) -> dict:
    """The functions, parameters and variables a program declares, and where each is used.

    Returns a `nexora.symbols/1` document. Every symbol and every reference was resolved by
    the checker with the scoping rules of the language; nothing is inferred from names.
    `name` keeps only the symbols with that name; `function` keeps a function and what is
    declared inside it. With syntax errors the list covers only the code that parsed and
    `complete` is false. `symbols` is null when the text has lexical errors.
    """
    return symbols_document(analyze(Source(filename, source)), name=name, function=function)


# Context

def _walk(node):
    """Every node of a tree, parents first."""
    if isinstance(node, ast.Node):
        yield node
        for field in node.__dataclass_fields__:
            yield from _walk(getattr(node, field))
    elif isinstance(node, tuple):
        for item in node:
            yield from _walk(item)


def _reaches(calls: dict[str, list[str]], start: str, target: str) -> bool:
    """Whether `target` can be reached from `start` by following calls (at least one)."""
    seen, pending = set(), list(calls.get(start, ()))
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(calls.get(current, ()))
    return False


# What a program uses, decided from the nodes of its tree. Each entry: (feature, test on a node).
_FEATURES = (
    ("conditionals", lambda node, types: isinstance(node, ast.If)),
    ("contracts", lambda node, types: isinstance(node, ast.Contract)),
    ("refined_types", lambda node, types: isinstance(node, ast.TypeDecl)),
    ("examples", lambda node, types: isinstance(node, ast.Example)),
    ("mutable_variables", lambda node, types: isinstance(node, ast.Var)),
    ("loops", lambda node, types: isinstance(node, ast.While)),
    ("loop_invariants", lambda node, types: isinstance(node, ast.LoopClause) and node.clause == "invariant"),
    ("type_annotations", lambda node, types: isinstance(node, ast.Let) and node.declared_type is not None),
    ("arithmetic", lambda node, types: isinstance(node, ast.Binary) and node.operator in ("+", "-", "*", "/")
        and types.get(id(node)) != TEXT),
    ("text_concatenation", lambda node, types: isinstance(node, ast.Binary) and types.get(id(node)) == TEXT),
    ("comparisons", lambda node, types: isinstance(node, ast.Binary)
        and node.operator in ("==", "!=", "<", "<=", ">", ">=")),
    ("logic", lambda node, types: (isinstance(node, ast.Binary) and node.operator in ("and", "or"))
        or (isinstance(node, ast.Unary) and node.operator == "not")),
    ("conversions", lambda node, types: isinstance(node, ast.Call)
        and node.callee in ("to_text", "to_float", "to_int")),
)


def _features(analysis: Analysis, recursive: bool) -> list[str]:
    program, types = analysis.program, analysis.types or {}
    refined = analysis.checked.refined if analysis.checked is not None else {}

    def root(kind: str | None) -> str | None:
        return refined[kind].root if kind in refined else kind

    found = set()
    for node in _walk(program):
        for feature, uses in _FEATURES:
            if uses(node, types):
                found.add(feature)
        # Decision 0011, 7.4: a function of a type, or two texts compared by order.
        if (isinstance(node, ast.Call) and node.callee in IMPLEMENTATIONS) or (
                isinstance(node, ast.Binary) and node.operator in ("<", "<=", ">", ">=")
                and root(types.get(id(node.left))) == TEXT):
            found.add("text_operations")
        if isinstance(node, ast.Block) and any(isinstance(statement, ast.Block) for statement in node.statements):
            found.add("nested_blocks")
    if len(program.functions) > 1 or any(function.name != "main" for function in program.functions):
        found.add("user_functions")
    if recursive:
        found.add("recursion")
    return sorted(found)


def _notes(analysis: Analysis, features: list[str], reserved_used: list[str]) -> list[str]:
    """Facts about the language that matter for this particular program. Each one is tied to
    something found in it; none is a judgement about the code."""
    notes = []
    if "contracts" in features:
        notes.append("Contracts ('requires', 'ensures') are checked while the program runs, on the calls "
                     "that execute. This analysis verified their types, not that they hold.")
    if "refined_types" in features:
        notes.append("Every value of a refined type satisfies its condition. This analysis checked the "
                     "constants given to refined types; any other value is checked by 'Type(x)' while the "
                     "program runs (E4003).")
    if "loops" in features:
        notes.append("Every loop declares a measure ('decreases') that is checked on every turn: a loop ends, or "
                     "stops with E4006. Invariants are checked before every evaluation of the loop condition "
                     "(E4005). This analysis verified their types, not that they hold.")
    if "recursion" in features:
        notes.append(f"Recursion is limited to {MAX_CALL_DEPTH} nested calls (runtime error E3004).")
    types = analysis.types or {}
    if analysis.program is not None and any(
        isinstance(node, ast.Binary) and node.operator == "/" and types.get(id(node)) == INT
        for node in _walk(analysis.program)
    ):
        notes.append("Int / Int produces an Int: the fractional part is dropped. Division by zero is a runtime "
                     "error (E3001) that static analysis does not detect.")
    if reserved_used:
        notes.append("The program uses words reserved for features that are not implemented: "
                     + ", ".join(reserved_used) + ".")
    if analysis.program is None:
        notes.append("The text could not be read as NEXORA code, so its structure could not be analysed. "
                     "Only the diagnostics are available.")
    elif not analysis.complete:
        notes.append("The program has syntax errors, so this summary is partial: it covers only the code that "
                     "could be parsed. Statements with errors, and functions whose declaration has errors, are "
                     "missing, and a type that depends on them is unknown.")
    return notes


def _function_context(function: ast.Function, analysis: Analysis, calls: dict[str, list[str]],
                      callers: dict[str, list[str]]) -> dict:
    facts = analysis.facts
    variables = [
        {
            "name": symbol.name,
            "type": symbol.type,
            "line": symbol.span.line,
            "mutable": symbol.mutable,
        }
        for symbol in facts.symbols
        if symbol.category == "variable" and symbol.function == function.name
    ]
    return {
        "name": function.name,
        "signature": _signature_text(function),
        "params": [{"name": param.name, "type": param.type.name} for param in function.params],
        "return_type": function.return_type.name,
        "span": _span(function.span),
        "contracts": [
            {"clause": contract.clause, "condition": _text_of(analysis.source, contract.condition.span),
             "message": contract.message, "line": contract.span.line}
            for contract in function.contracts
        ],
        "variables": variables,
        "calls": sorted({callee for callee in calls.get(function.name, ()) if callee not in BUILTINS}),
        "builtins_called": sorted({callee for callee in calls.get(function.name, ()) if callee in BUILTINS}),
        "called_by": sorted(set(callers.get(function.name, ()))),
        "recursive": _reaches({name: [c for c in callees if c not in BUILTINS] for name, callees in calls.items()},
                              function.name, function.name),
        # Last: a field added to an object goes at the end (decision 0008, section 8). The examples
        # are listed as written; the analysis never evaluates them.
        "examples": [
            {"condition": _text_of(analysis.source, example.condition.span), "message": example.message,
             "line": example.span.line}
            for example in function.examples
        ],
        # The loops of the function and the requirements each one declares (decision 0010).
        "loops": [_loop_context(loop, analysis.source) for loop in _walk(function.body) if isinstance(loop, ast.While)],
    }


def _loop_context(loop: ast.While, source: Source) -> dict:
    def clause(node: ast.LoopClause) -> dict:
        return {"condition": _text_of(source, node.condition.span), "message": node.message, "line": node.span.line}

    measures = [node for node in loop.clauses if node.clause == "decreases"]
    return {
        "line": loop.span.line,
        "condition": _text_of(source, loop.condition.span),
        "invariants": [clause(node) for node in loop.clauses if node.clause == "invariant"],
        "measure": clause(measures[0]) if measures else None,
    }


def _type_entries(analysis: Analysis) -> list[dict]:
    """The refined types the program declares, as written. `root` is null when the declaration
    has an error that leaves the type unusable."""
    refined = analysis.facts.refined
    return [
        {
            "name": declaration.name,
            "base": declaration.base.name,
            "root": refined[declaration.name].root if declaration.name in refined else None,
            "condition": _text_of(analysis.source, declaration.condition.span),
            "message": declaration.message,
            "line": declaration.span.line,
        }
        for declaration in analysis.program.types
    ]


def context_document(analysis: Analysis) -> dict:
    document = _header(CONTEXT_SCHEMA, analysis.source.name, analysis.diagnostics)
    document["executed"] = False
    document["lines"] = analysis.source.text.count("\n") + (0 if analysis.source.text.endswith("\n") else 1) \
        if analysis.source.text else 0

    reserved_used = sorted({token.lexeme for token in analysis.tokens or () if token.type is TokenType.RESERVED})
    document["reserved_words_used"] = reserved_used if analysis.tokens is not None else None

    if analysis.facts is None:
        document.update(analysed=False, complete=False, entry_point=None, types=None, functions=None,
                        features=None)
        document["notes"] = _notes(analysis, [], reserved_used)
        return document

    facts = analysis.facts
    calls: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}
    for caller, callee in facts.calls:
        calls.setdefault(caller, []).append(callee)
        if callee not in BUILTINS:
            callers.setdefault(callee, []).append(caller)

    functions = [_function_context(function, analysis, calls, callers) for function in facts.functions.values()]
    features = _features(analysis, any(function["recursive"] for function in functions))
    document.update(
        analysed=True,
        complete=analysis.complete,
        entry_point="main" if "main" in facts.functions else None,
        types=_type_entries(analysis),
        functions=functions,
        features=features,
    )
    document["notes"] = _notes(analysis, features, reserved_used)
    return document


def get_context(source: str, filename: str = DEFAULT_FILENAME) -> dict:
    """A compact technical summary of a program, for a tool or an AI agent that is about to
    read or modify it: functions and their signatures, contracts, variables with their types,
    who calls whom, the language features in use, and the current diagnostics.

    Returns a `nexora.context/1` document. It is computed by the same static analysis as
    `check_source`. The program is not run and no model is involved; the same source always
    gives the same document.
    """
    return context_document(analyze(Source(filename, source)))


def render_context(document: dict) -> str:
    """A `nexora.context/1` document as text for people (what `nex context` prints)."""
    lines = [f"{document['file']} | NEXORA {document['nexora_version']} | {document['lines']} lines"]
    count = len(document["diagnostics"])
    lines.append("Static analysis: no errors." if document["ok"]
                 else f"Static analysis: {count} error{'' if count == 1 else 's'}.")
    lines.append("The program was not run to produce this summary.")

    if document["analysed"]:
        if not document["complete"]:
            lines.append("Partial summary: only the code that could be parsed is described.")
        entry = document["entry_point"]
        lines.append(f"Entry point: {entry}" if entry else "Entry point: none (the program has no 'main').")
        lines.append("")
        if document["types"]:
            lines.append(f"Types ({len(document['types'])}):")
            for kind in document["types"]:
                lines.append(f"  type {kind['name']} = {kind['base']} where {kind['condition']}    "
                             f"[line {kind['line']}]")
                if kind["message"]:
                    lines.append(f"      reason: {kind['message']}")
            lines.append("")
        lines.append(f"Functions ({len(document['functions'])}):")
        for function in document["functions"]:
            lines.append(f"  {function['signature']}    [line {function['span']['line']}]")
            for contract in function["contracts"]:
                lines.append(f"      {contract['clause']} {contract['condition']}")
                if contract["message"]:
                    lines.append(f"          reason: {contract['message']}")
            if function["variables"]:
                variables = ", ".join(f"{'var ' if v['mutable'] else ''}{v['name']}: {v['type'] or '?'}"
                                      for v in function["variables"])
                lines.append(f"      variables: {variables}")
            for loop in function["loops"]:
                lines.append(f"      loop at line {loop['line']}: while {loop['condition']}")
                for clause, entry in [*(("invariant", item) for item in loop["invariants"]),
                                      *([("decreases", loop["measure"])] if loop["measure"] else [])]:
                    lines.append(f"          {clause} {entry['condition']}")
                    if entry["message"]:
                        lines.append(f"              reason: {entry['message']}")
            if function["calls"]:
                lines.append(f"      calls: {', '.join(function['calls'])}")
            if function["builtins_called"]:
                lines.append(f"      built-ins: {', '.join(function['builtins_called'])}")
                for name in function["builtins_called"]:
                    for contract in requirements(name):
                        lines.append(f"          {name} requires {contract.source}")
                        lines.append(f"              reason: {contract.message}")
            if function["called_by"]:
                lines.append(f"      called by: {', '.join(function['called_by'])}")
            if function["recursive"]:
                lines.append("      recursive")
            for example in function["examples"]:
                lines.append(f"      example {example['condition']}")
                if example["message"]:
                    lines.append(f"          reason: {example['message']}")
        lines.append("")
        lines.append("Features used: " + (", ".join(document["features"]) or "none"))

    if document["diagnostics"]:
        lines.append("")
        lines.append("Diagnostics:")
        for diagnostic in document["diagnostics"]:
            where = f"{diagnostic['line']}:{diagnostic['column']}" if diagnostic["line"] is not None else "-"
            lines.append(f"  {diagnostic['category']} {diagnostic['code']} at {where}: {diagnostic['label']}")
    if document["notes"]:
        lines.append("")
        lines.append("Notes:")
        lines.extend(f"  - {note}" for note in document["notes"])
    return "\n".join(lines)


def render_symbols(document: dict) -> str:
    """A `nexora.symbols/1` document as text for people (what `nex symbols` prints)."""
    if document["symbols"] is None:
        return "No symbols: the text could not be read as NEXORA code."
    partial = "Partial list: the program has syntax errors, and the code with errors is not included."
    if not document["symbols"]:
        return "No symbols match." if document["complete"] else f"No symbols match.\n{partial}"
    lines = [] if document["complete"] else [partial]
    for symbol in document["symbols"]:
        where = f"{symbol['declaration']['line']}:{symbol['declaration']['column']}"
        if symbol["category"] == "function":
            head = f"function   {symbol['signature']}"
        else:
            head = f"{symbol['category']:<10} {symbol['name']}: {symbol['type'] or '?'}    in {symbol['function']}"
        uses = ", ".join(f"{reference['line']}:{reference['column']}" for reference in symbol["references"])
        lines.append(f"{head}    [declared at {where}]")
        lines.append(f"    used at: {uses or 'nowhere'}")
    return "\n".join(lines)


# The language itself

def _slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _spec_sections(text: str) -> list[dict]:
    """The sections of the specification: level-2 and level-3 headings outside code blocks."""
    sections = []
    in_code = False
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("```") or line.startswith("````"):
            in_code = not in_code
        match = None if in_code else re.match(r"^(##|###) (.+)$", line)
        if match:
            title = re.sub(r"[*`]", "", match.group(2)).strip()
            sections.append({"id": _slug(match.group(2)), "title": title, "level": len(match.group(1)), "start": index})
    for position, section in enumerate(sections):
        end = len(lines)
        for later in sections[position + 1:]:
            if later["level"] <= section["level"]:
                end = later["start"]
                break
        section["text"] = "\n".join(lines[section["start"]:end]).strip()
    return sections


def get_language_spec(section: str | None = None) -> dict:
    """The official language specification, or one section of it.

    Without `section`, returns the list of sections. With a section id (taken from that
    list), also returns the Markdown text of that section. The text comes from
    docs/language-spec.md of the project and from nowhere else: `section` is looked up in
    the list of headings, never used as a path.

    Returns a `nexora.spec/1` document. `available` is false when NEXORA was installed
    without its documentation (from a wheel), in which case there are no sections.
    Raises ToolingError("unknown_section") for an id that is not in the list.
    """
    document = {
        "schema": SPEC_SCHEMA,
        "nexora_version": __version__,
        "available": False,
        "spec_version": None,
        "language": "es",
        "sections": [],
        "section": None,
    }
    try:
        text = _SPEC_PATH.read_text(encoding="utf-8")
    except OSError:
        return document

    version = re.search(r"\*\*Versión de la especificación:\*\*\s*([\d.]+)", text)
    sections = _spec_sections(text)
    document.update(
        available=True,
        spec_version=version.group(1) if version else None,
        sections=[{"id": s["id"], "title": s["title"], "level": s["level"]} for s in sections],
    )
    if section is not None:
        wanted = next((s for s in sections if s["id"] == section), None)
        if wanted is None:
            raise ToolingError("unknown_section", f"The specification has no section with the id '{section}'.")
        document["section"] = {"id": wanted["id"], "title": wanted["title"], "text": wanted["text"]}
    return document


def get_capabilities() -> dict:
    """What this version of NEXORA is: its words, types, built-in functions, diagnostic codes,
    limits and output formats. Everything is read from the implementation, so it cannot drift."""
    return {
        "schema": CAPABILITIES_SCHEMA,
        "nexora_version": __version__,
        "language": {
            "keywords": sorted(KEYWORDS),
            "reserved_words": sorted(RESERVED_WORDS),
            "types": [VOID, *VALUE_TYPES],
            "builtins": _builtin_entries(),
        },
        "diagnostics": [
            {"code": code, "message": CODES[code], "category": CATEGORIES[code]} for code in sorted(CODES)
        ],
        "limits": {
            "max_call_depth": MAX_CALL_DEPTH,
            "max_nesting": MAX_NESTING,
            "max_expression_depth": MAX_EXPRESSION_DEPTH,
            "max_diagnostics_per_stage": MAX_DIAGNOSTICS,
            "max_refinement_steps": MAX_REFINEMENT_STEPS,
            "int_min": INT_MIN,
            "int_max": INT_MAX,
        },
        "schemas": [DIAGNOSTICS_SCHEMA, INSPECT_SCHEMA, SYMBOLS_SCHEMA, CONTEXT_SCHEMA, SPEC_SCHEMA,
                    CAPABILITIES_SCHEMA],
        "analysis_executes_code": False,
    }

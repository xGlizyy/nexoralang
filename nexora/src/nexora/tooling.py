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
from collections.abc import Sequence
from pathlib import Path

from . import ast_nodes as ast
from .checker import BUILTINS, MAX_REFINEMENT_STEPS, CheckedProgram, Signature
from .diagnostics import CATEGORIES, CODES, MAX_DIAGNOSTICS, Source, Span
from .interpreter import MAX_CALL_DEPTH
from .parser import MAX_EXPRESSION_DEPTH, MAX_NESTING
from .pipeline import Analysis, analyze
from .prelude import CONTRACTS, IMPLEMENTATIONS, requirements
from .tokens import KEYWORDS, OLD_CLAUSE_WORDS, RESERVED_WORDS, TokenType
from .values import INT, INT_MAX, INT_MIN, TEXT, VALUE_TYPES, VOID
from .version import __version__

DIAGNOSTICS_SCHEMA = "nexora.diagnostics/1"
INSPECT_SCHEMA = "nexora.inspect/3"
SYMBOLS_SCHEMA = "nexora.symbols/2"
CONTEXT_SCHEMA = "nexora.context/2"
SPEC_SCHEMA = "nexora.spec/2"
CAPABILITIES_SCHEMA = "nexora.capabilities/1"
EVIDENCE_SCHEMA = "nexora.evidence/1"

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


def _header(schema: str, filename: str, diagnostics: tuple, files: Sequence[str] | None = None) -> dict:
    """The common part of every document: its schema, its version, its file and its errors.

    `files` names the file each diagnostic belongs to, when a program is made of several
    files (decision 0018). The document keeps `filename` as the file of the program itself.
    """
    return {
        "schema": schema,
        "nexora_version": __version__,
        "file": filename,
        "ok": not diagnostics,
        "diagnostics": [diagnostic.to_dict(files[index] if files else filename)
                        for index, diagnostic in enumerate(diagnostics)],
    }


def diagnostics_document(filename: str, diagnostics, *, files: Sequence[str] | None = None) -> dict:
    """The `nexora.diagnostics/1` document for a list of diagnostics."""
    return _header(DIAGNOSTICS_SCHEMA, filename, tuple(diagnostics), files)


def _signature_text(function: ast.Function) -> str:
    params = ", ".join(f"{param.name}: {param.type.name}" for param in function.params)
    if function.return_type is None:
        return f"fn {function.name}({params})"
    return f"fn {function.name}({params}) gives {function.return_type.name}"


def _return_type_name(function: ast.Function) -> str:
    """The type a function gives: Void when it has no 'gives' (decision 0019)."""
    return VOID if function.return_type is None else function.return_type.name


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

    Returns a `nexora.inspect/3` document. With syntax errors the tree is partial and
    `complete` is false: the statements with errors, and the functions whose declaration has
    them, are missing. `program` is null when the text has lexical errors.
    """
    return inspect_document(analyze(Source(filename, source)))


# Symbols

def _module_files(analysis: Analysis) -> dict[str, str]:
    """The file each module comes from: what a module declares belongs to that file.

    An analysis of a single file has no modules, and every name belongs to the file it
    was given (decision 0018).
    """
    if analysis.project is None:
        return {}
    return {module.name: module.source.name for module in analysis.project.modules}


def _declared_function(facts: CheckedProgram, symbol) -> ast.Function | None:
    """The declaration a function symbol names.

    A function of a module is stored with its module in front (`models.area`), while its
    symbol keeps the name as it is written inside the module, so the position of the
    declaration is what tells the two apart (decision 0018, 5). In the file that runs no
    name is qualified, and the position tells them apart there too.
    """
    for declaration in facts.functions.values():
        if declaration.name_span == symbol.span:
            return declaration
    return None


def _symbol_entries(facts: CheckedProgram, files: dict[str, str], entry_file: str) -> list[dict]:
    """Every name the program declares, each with the file that declares it.

    A name of a module belongs to the file that module comes from, and a name of the file
    that runs belongs to `entry_file` (decision 0018).
    """
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
            declaration = _declared_function(facts, symbol)
            if declaration is not None:
                entry["signature"] = _signature_text(declaration)
                entry["params"] = [{"name": param.name, "type": param.type.name} for param in declaration.params]
                entry["return_type"] = _return_type_name(declaration)
        # Last: a field added to an object goes at the end (decision 0008, section 8).
        entry["file"] = entry_file if symbol.module is None else files.get(symbol.module, entry_file)
        entries.append(entry)
    return entries


# `nexora.capabilities/1` keeps the clause names of 0.11 for the contracts of the built-in
# functions: adopting `needs` and `promises` there is a change of that format, to be versioned
# explicitly (decision of the person responsible, 2026-10-24). `nexora.symbols/2` uses the new ones
# (decision 0019, 8.8).
_CLAUSES_OF_CAPABILITIES_1 = {"needs": "requires", "promises": "ensures"}


def _builtin_entries(clause_names: dict[str, str] | None = None) -> list[dict]:
    def describe(signature: Signature) -> dict:
        return {
            "name": signature.name,
            "signature": signature.describe(),
            "params": [{"name": name, "type": kind} for name, kind in signature.params],
            "return_type": signature.return_type,
            # Decision 0011, 7.4: an agent must not take a `promises` for something checked.
            "contracts": [
                {"clause": (clause_names or {}).get(contract.clause, contract.clause),
                 "condition": contract.source, "message": contract.message,
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
        entries = _symbol_entries(analysis.facts, _module_files(analysis), analysis.source.name)
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

    Returns a `nexora.symbols/2` document. Every symbol and every reference was resolved by
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
    ("records", lambda node, types: isinstance(node, ast.RecordDecl)),
    ("examples", lambda node, types: isinstance(node, ast.Example)),
    ("mutable_variables", lambda node, types: isinstance(node, ast.Var)),
    ("loops", lambda node, types: isinstance(node, (ast.While, ast.For))),
    ("loop_invariants", lambda node, types: isinstance(node, ast.LoopClause) and node.clause == "keeps"),
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
    # The input and the files (decision 0015).
    ("arguments", lambda node, types: isinstance(node, ast.Call) and node.callee == "args"),
    ("input", lambda node, types: isinstance(node, ast.Call) and node.callee == "input"),
    ("file_access", lambda node, types: isinstance(node, ast.UsesDecl)),
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
        notes.append("Contracts ('needs', 'promises') are checked while the program runs, on the calls "
                     "that execute; a 'trust' is never checked. This analysis verified their types, not that "
                     "they hold.")
    if "refined_types" in features:
        notes.append("Every value of a refined type satisfies its condition. This analysis checked the "
                     "constants given to refined types; any other value is checked by 'Type(x)' while the "
                     "program runs (E4003).")
    if "records" in features:
        notes.append("A record is a type the program declares: its fields never change, and two records "
                     "are different types even when they have the same fields.")
    if "loops" in features:
        notes.append("Every 'while' declares a measure ('shrinks') that is checked on every turn: a loop ends, or "
                     "stops with E4006. A 'for' walks a finite list and needs no measure. Invariants are checked "
                     "before every turn and once after the last one (E4005). This analysis verified their types, "
                     "not that they hold.")
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


def _module_of_key(key: str) -> str | None:
    """The module a key belongs to: `models.area` is `models`; `main` belongs to no module."""
    return key.rsplit(".", 1)[0] if "." in key else None


def _function_context(key: str, function: ast.Function, analysis: Analysis, calls: dict[str, list[str]],
                      callers: dict[str, list[str]]) -> dict:
    """The context of one function. `key` is its name qualified with its module, which is
    what the call graph uses to tell two same-named functions apart (decision 0018, 5)."""
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
        "return_type": _return_type_name(function),
        "span": _span(function.span),
        "contracts": [
            {"clause": contract.clause, "condition": _text_of(analysis.source, contract.condition.span),
             "message": contract.message, "line": contract.span.line, "name": contract.name}
            for contract in function.contracts
        ],
        "variables": variables,
        "calls": sorted({callee for callee in calls.get(key, ()) if callee not in BUILTINS}),
        "builtins_called": sorted({callee for callee in calls.get(key, ()) if callee in BUILTINS}),
        "called_by": sorted(set(callers.get(key, ()))),
        "recursive": _reaches({name: [c for c in callees if c not in BUILTINS] for name, callees in calls.items()},
                              key, key),
        # Last: a field added to an object goes at the end (decision 0008, section 8). The examples
        # are listed as written; the analysis never evaluates them.
        "examples": [
            {"condition": _text_of(analysis.source, example.condition.span), "message": example.message,
             "line": example.span.line}
            for example in function.examples
        ],
        # The loops of the function and the requirements each one declares (decisions 0010 and 0012).
        "loops": [_loop_context(loop, analysis.source) for loop in _walk(function.body)
                  if isinstance(loop, (ast.While, ast.For))],
    }


def _loop_context(loop: ast.While | ast.For, source: Source) -> dict:
    def clause(node: ast.LoopClause) -> dict:
        return {"condition": _text_of(source, node.condition.span), "message": node.message, "line": node.span.line,
                "name": node.name}

    measures = [] if isinstance(loop, ast.For) else [node for node in loop.clauses if node.clause == "shrinks"]
    if isinstance(loop, ast.For):
        kind = "for"
        header = f"{loop.name} in {_text_of(source, loop.iterable.span)}"
    else:
        kind = "while"
        header = _text_of(source, loop.condition.span)
    return {
        "line": loop.span.line,
        "kind": kind,
        "condition": header,
        "invariants": [clause(node) for node in loop.clauses if node.clause == "keeps"],
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


def _record_entries(analysis: Analysis) -> list[dict]:
    """The record types the program declares, as written.

    `valid` says whether the declaration can be used as a type; `reason` says why it
    cannot, when it cannot (decision 0014, 6).
    """
    facts = analysis.facts
    entries = []
    for declaration in analysis.program.records:
        record = facts.records.get(declaration.name) if facts is not None else None
        entries.append({
            "name": declaration.name,
            "fields": [
                {"name": field.name, "type": record.field_type(field.name) if record else None}
                for field in declaration.fields
            ],
            "valid": record is not None,
            "line": declaration.span.line,
            "reason": None if record is not None else _record_reason(analysis, declaration),
        })
    return entries


def _record_reason(analysis: Analysis, declaration: ast.RecordDecl) -> str | None:
    """Why a record declaration cannot be used: the error that was found in it."""
    for diagnostic in analysis.diagnostics:
        span = diagnostic.span
        if span is None:
            continue
        if declaration.span.line <= span.line <= declaration.span.end_line:
            return diagnostic.label
    for diagnostic in analysis.diagnostics:
        if declaration.name in diagnostic.label:
            return diagnostic.label
    return None


def _capability_entries(analysis: Analysis) -> list[dict]:
    """The capabilities the program declares it needs, as they were written.

    Declaring a capability does not grant it: the user has to allow it too, and the
    environment has to permit it (decision 0015, 3).
    """
    return [
        {"capability": declaration.capability, "path": declaration.path}
        for declaration in analysis.program.uses
    ]


def context_document(analysis: Analysis) -> dict:
    document = _header(CONTEXT_SCHEMA, analysis.source.name, analysis.diagnostics)
    document["executed"] = False
    document["lines"] = analysis.source.text.count("\n") + (0 if analysis.source.text.endswith("\n") else 1) \
        if analysis.source.text else 0

    reserved_used = sorted({token.lexeme for token in analysis.tokens or () if token.type is TokenType.RESERVED})
    document["reserved_words_used"] = reserved_used if analysis.tokens is not None else None

    if analysis.facts is None:
        document.update(analysed=False, complete=False, entry_point=None, types=None, records=None,
                        capabilities=None, functions=None, features=None)
        document["notes"] = _notes(analysis, [], reserved_used)
        return document

    facts = analysis.facts
    calls: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}
    for caller, callee in facts.calls:
        calls.setdefault(caller, []).append(callee)
        if callee not in BUILTINS:
            callers.setdefault(callee, []).append(caller)

    files = _module_files(analysis)
    functions = []
    for key, function in facts.functions.items():
        entry = _function_context(key, function, analysis, calls, callers)
        # Last: a field added to an object goes at the end (decision 0008, section 8).
        module = _module_of_key(key)
        entry["file"] = analysis.source.name if module is None else files.get(module, analysis.source.name)
        functions.append(entry)
    features = _features(analysis, any(function["recursive"] for function in functions))
    document.update(
        analysed=True,
        complete=analysis.complete,
        entry_point="main" if "main" in facts.functions else None,
        types=_type_entries(analysis),
        records=_record_entries(analysis),
        capabilities=_capability_entries(analysis),
        functions=functions,
        features=features,
    )
    document["notes"] = _notes(analysis, features, reserved_used)
    return document


def get_context(source: str, filename: str = DEFAULT_FILENAME) -> dict:
    """A compact technical summary of a program, for a tool or an AI agent that is about to
    read or modify it: functions and their signatures, contracts, variables with their types,
    who calls whom, the language features in use, and the current diagnostics.

    Returns a `nexora.context/2` document. It is computed by the same static analysis as
    `check_source`. The program is not run and no model is involved; the same source always
    gives the same document.
    """
    return context_document(analyze(Source(filename, source)))


def render_context(document: dict) -> str:
    """A `nexora.context/2` document as text for people (what `nex context` prints)."""
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
        if document["records"]:
            lines.append(f"Records ({len(document['records'])}):")
            for record in document["records"]:
                fields = ", ".join(f"{field['name']}: {field['type'] or '?'}" for field in record["fields"])
                lines.append(f"  type {record['name']} = {{ {fields} }}    [line {record['line']}]")
                if record["reason"]:
                    lines.append(f"      reason: {record['reason']}")
            lines.append("")
        if document["capabilities"]:
            lines.append(f"Capabilities ({len(document['capabilities'])}):")
            for capability in document["capabilities"]:
                lines.append(f"  uses {capability['capability']} \"{capability['path']}\"")
            lines.append("")
        lines.append(f"Functions ({len(document['functions'])}):")
        for function in document["functions"]:
            lines.append(f"  {function['signature']}    [line {function['span']['line']}]")
            for contract in function["contracts"]:
                name = f"{contract['name']}: " if contract["name"] else ""
                lines.append(f"      {contract['clause']} {name}{contract['condition']}")
                if contract["message"]:
                    lines.append(f"          reason: {contract['message']}")
            if function["variables"]:
                variables = ", ".join(f"{'var ' if v['mutable'] else ''}{v['name']}: {v['type'] or '?'}"
                                      for v in function["variables"])
                lines.append(f"      variables: {variables}")
            for loop in function["loops"]:
                lines.append(f"      loop at line {loop['line']}: {loop['kind']} {loop['condition']}")
                for clause, entry in [*(("keeps", item) for item in loop["invariants"]),
                                      *([("shrinks", loop["measure"])] if loop["measure"] else [])]:
                    name = f"{entry['name']}: " if entry["name"] else ""
                    lines.append(f"          {clause} {name}{entry['condition']}")
                    if entry["message"]:
                        lines.append(f"              reason: {entry['message']}")
            if function["calls"]:
                lines.append(f"      calls: {', '.join(function['calls'])}")
            if function["builtins_called"]:
                lines.append(f"      built-ins: {', '.join(function['builtins_called'])}")
                for name in function["builtins_called"]:
                    for contract in requirements(name):
                        lines.append(f"          {name} needs {contract.source}")
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
    """A `nexora.symbols/2` document as text for people (what `nex symbols` prints)."""
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


# Evidence (decision 0019, section 5)

# Whether the language evaluates each kind of clause when the program runs (5.2).
_ENFORCEMENT = {"needs": "checked", "promises": "checked", "keeps": "checked", "shrinks": "checked",
                "trust": "trusted"}
_NOT_APPLICABLE = {"status": "not_applicable"}


def _static_of(kind: str) -> dict:
    """Only a `needs` can be decided at its call sites, and no phase before 4 does it (5.3)."""
    if kind == "needs":
        return {"status": "not_computed", "reason": "phase_not_implemented"}
    return dict(_NOT_APPLICABLE)


def _observed_of(kind: str) -> dict:
    """A `trust` is never evaluated; the rest could be observed, but the analysis runs nothing (5.3)."""
    if kind == "trust":
        return dict(_NOT_APPLICABLE)
    return {"status": "not_computed", "reason": "analysis_only"}


def _path_parts(path: str) -> list[str]:
    """The parts of a path, with `.` and `..` resolved on the text: no file is looked at."""
    parts: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append(part)
        elif part != ".":
            parts.append(part)
    return parts


def _module_id(path: str, entry_path: str) -> str:
    """A module as 7.1 identifies it: its path relative to the directory of the entry file, with
    `/`; `""` for the entry file. Computed on the text of the paths, as the analysis knows them."""
    if path == entry_path:
        return ""
    target, base = _path_parts(path), _path_parts(entry_path)[:-1]
    shared = 0
    while shared < min(len(target), len(base)) and target[shared] == base[shared]:
        shared += 1
    if shared == 0 and target and (target[0] == "" or target[0].endswith(":")):
        return "/".join(target)     # an absolute path outside the directory: no relative path
    return "/".join([".."] * (len(base) - shared) + target[shared:])


def _clauses_of(function: ast.Function) -> list[ast.Contract | ast.LoopClause]:
    """The `needs`, `promises`, `trust`, `keeps` and `shrinks` of a function, in the order of the
    file: the header first, then the loops of the body."""
    loops = [clause for node in _walk(function.body) if isinstance(node, (ast.While, ast.For))
             for clause in node.clauses]
    return [*function.contracts, *loops]


def _evidence_entry(module: str, function: ast.Function, clause: ast.Contract | ast.LoopClause,
                    source: Source) -> dict:
    kind = clause.clause
    return {
        # Only a named clause has an identity that survives an edit (7.1).
        "id": {"module": module, "function": function.name, "name": clause.name, "kind": kind,
               "stable": clause.name is not None},
        "condition": _text_of(source, clause.condition.span),
        "message": clause.message,
        "enforcement": _ENFORCEMENT[kind],
        "static": _static_of(kind),
        "observed": _observed_of(kind),
        # 5.5: with nothing observed and nothing decided, the word comes from the enforcement.
        "summary": _ENFORCEMENT[kind],
    }


def evidence_document(analysis: Analysis) -> dict:
    """The `nexora.evidence/1` document of an analysis (`nex check --evidence`): what backs every
    clause of the program. Only the enforcement dimension is computed; nothing is run, decided or
    observed. `clauses` is null when the program has errors."""
    if analysis.project is not None:
        reports = analysis.project.reports()
        document = _header(EVIDENCE_SCHEMA, analysis.source.name, tuple(d for d, _ in reports),
                           [file.name for _, file in reports])
    else:
        document = _header(EVIDENCE_SCHEMA, analysis.source.name, analysis.diagnostics)
    document["computed"] = {"static": False, "observed": False}
    if analysis.checked is None:
        document["clauses"] = None
        return document

    if analysis.project is not None:
        # Each module is known by the path it is shown with, relative to the program (decision 0018).
        entry_path = analysis.project.entry.source.name
        modules = [(_module_id(module.source.name, entry_path), module) for module in analysis.project.modules]
        files = [(name, module.program, module.source) for name, module in modules]
    else:
        files = [("", analysis.program, analysis.source)]
    clauses = []
    # By module path, compared by code point, as 7.2 orders a report; the entry file, "", first.
    for name, program, source in sorted(files, key=lambda item: item[0]):
        for function in program.functions:
            clauses += [_evidence_entry(name, function, clause, source) for clause in _clauses_of(function)]
    document["clauses"] = clauses
    return document


def get_evidence(source: str, filename: str = DEFAULT_FILENAME) -> dict:
    """What backs every `needs`, `promises`, `trust`, `keeps` and `shrinks` of a program, as a
    `nexora.evidence/1` document. Computed by the same analysis as `check_source`: the program is
    not run, so the only dimension computed is the enforcement (decision 0019, section 5)."""
    return evidence_document(analyze(Source(filename, source)))


def _count_of(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def render_evidence(document: dict) -> str:
    """A `nexora.evidence/1` document as text for people (what `nex check --evidence` prints)."""
    clauses = document["clauses"]
    functions: dict[tuple[str, str], list[dict]] = {}
    for clause in clauses:
        functions.setdefault((clause["id"]["module"], clause["id"]["function"]), []).append(clause)
    computed = ", ".join(["enforcement", *(name for name in ("static", "observed") if document["computed"][name])])
    lines = [f"{document['file']}: {_count_of(len(clauses), 'promise')} in "
             f"{_count_of(len(functions), 'function')} (computed: {computed})"]

    def label(clause: dict) -> str:
        return f"{clause['id']['kind']} {clause['id']['name'] or clause['condition']}"

    width = max((len(label(clause)) for clause in clauses), default=0) + 4
    for (module, function), entries in functions.items():
        lines.append(f"  {function}" if module == "" else f"  {function} ({module})")
        lines.extend(f"    {label(clause):<{width}}{clause['summary']}" for clause in entries)
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

    Returns a `nexora.spec/2` document. `available` is false when NEXORA was installed
    without its documentation (from a wheel), in which case there are no sections.
    Raises ToolingError("unknown_section") for an id that is not in the list.
    """
    document = {
        "schema": SPEC_SCHEMA,
        "nexora_version": __version__,
        "available": False,
        "spec_version": None,
        "language": "en",
        "sections": [],
        "section": None,
    }
    try:
        text = _SPEC_PATH.read_text(encoding="utf-8")
    except OSError:
        return document

    version = re.search(r"\*\*Specification version:\*\*\s*([\d.]+)", text)
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
            "reserved_words": sorted(RESERVED_WORDS | OLD_CLAUSE_WORDS.keys()),
            "types": [VOID, *VALUE_TYPES],
            "builtins": _builtin_entries(_CLAUSES_OF_CAPABILITIES_1),
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
                    CAPABILITIES_SCHEMA, EVIDENCE_SCHEMA],
        "analysis_executes_code": False,
    }

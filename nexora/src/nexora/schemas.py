"""JSON Schemas (draft 2020-12) of the documents NEXORA produces.

The files in docs/schemas/ are copies of what `all_schemas()` returns; a test fails if they
differ. The part that describes the syntax tree is derived from the node classes themselves,
so a node cannot change without its schema changing with it.

Compatibility rule, the same for every schema: objects may gain fields. A consumer must
ignore fields it does not know (`additionalProperties` is left open on purpose). Removing or
renaming a field, or changing its meaning, changes the number after the slash in `schema`.
"""

from __future__ import annotations

import types
import typing
from dataclasses import fields

from . import ast_nodes as ast
from .diagnostics import CATEGORIES, Span

_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_BASE = "https://nexora.invalid/schemas/"   # identifiers only: nothing is published at this address

_NULLABLE_INT = {"type": ["integer", "null"], "minimum": 1}
_NULLABLE_STRING = {"type": ["string", "null"]}

SPAN = {
    "description": "A region of the source. Lines and columns start at 1; the end is exclusive. "
                   "Columns count Unicode code points.",
    "type": "object",
    "required": ["line", "column", "end_line", "end_column"],
    "properties": {name: {"type": "integer", "minimum": 1} for name in ("line", "column", "end_line", "end_column")},
}

DIAGNOSTIC = {
    "type": "object",
    "required": ["severity", "category", "code", "message", "label", "hint", "notes", "file",
                 "line", "column", "end_line", "end_column"],
    "properties": {
        "severity": {"const": "error"},
        "category": {"enum": sorted(set(CATEGORIES.values()))},
        "code": {"type": "string", "pattern": "^E[0-9]{4}$", "description": "Stable identifier of the problem."},
        "message": {"type": "string", "description": "Fixed title of the code."},
        "label": {"type": "string", "description": "What is wrong in this particular case."},
        "hint": {**_NULLABLE_STRING, "description": "A suggested fix, only when a rule of the language supports it."},
        "notes": {"type": "array", "items": {"type": "string"}, "description": "Related information."},
        "file": {"type": "string"},
        "line": _NULLABLE_INT, "column": _NULLABLE_INT, "end_line": _NULLABLE_INT, "end_column": _NULLABLE_INT,
    },
}

_HEADER_REQUIRED = ["schema", "nexora_version", "file", "ok", "diagnostics"]


def _header(schema: str) -> dict:
    return {
        "schema": {"const": schema},
        "nexora_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "file": {"type": "string", "description": "The name the source was given. A label, not necessarily a path."},
        "ok": {"type": "boolean", "description": "True when the static analysis found no errors."},
        "diagnostics": {"type": "array", "items": {"$ref": "#/$defs/diagnostic"}},
    }


def _document(name: str, title: str, properties: dict, required: list[str], definitions: dict) -> dict:
    return {
        "$schema": _DRAFT,
        "$id": f"{_BASE}{name}.schema.json",
        "title": title,
        "type": "object",
        "required": required,
        "properties": properties,
        "$defs": definitions,
    }


# The syntax tree, derived from the node classes

def _field_schema(annotation) -> dict:
    origin = typing.get_origin(annotation)
    if annotation is Span:
        return {"$ref": "#/$defs/span"}
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if origin is tuple:
        return {"type": "array", "items": _field_schema(typing.get_args(annotation)[0])}
    if origin in (typing.Union, types.UnionType):
        options = [option for option in typing.get_args(annotation) if option is not type(None)]
        nullable = len(options) != len(typing.get_args(annotation))
        kinds = [_field_schema(option) for option in options]
        if nullable:
            kinds.append({"type": "null"})
        return kinds[0] if len(kinds) == 1 else {"oneOf": kinds}
    return {"$ref": f"#/$defs/{annotation.__name__}"}


def node_definitions() -> dict:
    """One definition per kind of node, with exactly the fields `ast_nodes.to_dict` writes."""
    classes = [value for value in vars(ast).values()
               if isinstance(value, type) and issubclass(value, ast.Node) and value is not ast.Node]
    definitions = {}
    for node_class in classes:
        hints = typing.get_type_hints(node_class, vars(ast))
        properties = {"kind": {"const": node_class.__name__}}
        required = ["kind"]
        for field in fields(node_class):
            properties[field.name] = _field_schema(hints[field.name])
            required.append(field.name)
        if node_class in ast.EXPRESSION_NODES:
            properties["type"] = {
                "type": ["string", "null"],
                "description": "The type the checker computed: Int, Float, Bool, Text, Void, a list type such as "
                               "List[Int], or the name of a refined type the program declares. Null if the "
                               "expression has an error.",
            }
            required.append("type")
        definitions[node_class.__name__] = {"type": "object", "required": required, "properties": properties}
    return definitions


# The documents

_PARAM = {"type": "object", "required": ["name", "type"],
          "properties": {"name": {"type": "string"}, "type": _NULLABLE_STRING}}

_SYMBOL = {
    "type": "object",
    "required": ["name", "category", "type", "function", "declaration", "scope", "references", "mutable",
                 "assignments"],
    "properties": {
        "name": {"type": "string"},
        "category": {"enum": ["function", "parameter", "variable"]},
        "type": {**_NULLABLE_STRING, "description": "Its type; for a function, its return type. "
                                                    "Null if it could not be determined."},
        "function": {**_NULLABLE_STRING, "description": "The function it is declared in. Null for a function."},
        "declaration": {"$ref": "#/$defs/span"},
        "scope": {"oneOf": [{"$ref": "#/$defs/span"}, {"type": "null"}],
                  "description": "The block where the name is visible. Null for a function (visible everywhere)."},
        "references": {"type": "array", "items": {"$ref": "#/$defs/span"},
                       "description": "Every use the checker resolved to this symbol."},
        "mutable": {"type": "boolean", "description": "True only for a variable declared with 'var'."},
        "assignments": {"type": "array", "items": {"$ref": "#/$defs/span"},
                        "description": "Where a 'var' is given a new value. Each one is also in references."},
        "signature": {"type": "string", "description": "Functions only."},
        "params": {"type": "array", "items": {"$ref": "#/$defs/param"}, "description": "Functions only."},
        "return_type": {"type": "string", "description": "Functions only."},
    },
}

_BUILTIN_CONTRACT = {
    "type": "object",
    "required": ["clause", "condition", "message", "checked_at_run_time"],
    "properties": {
        "clause": {"enum": ["requires", "ensures"]},
        "condition": {"type": "string", "description": "The condition, written in NEXORA."},
        "message": {"type": "string", "description": "Why the rule exists."},
        "checked_at_run_time": {
            "type": "boolean",
            "description": "True for 'requires', checked on every call. False for 'ensures', which the "
                           "implementation keeps and the tests check, but the program does not.",
        },
    },
}

_BUILTIN = {
    "type": "object",
    "required": ["name", "signature", "params", "return_type", "contracts"],
    "properties": {"name": {"type": "string", "description": "Text.length for a function of a type."},
                   "signature": {"type": "string"},
                   "params": {"type": "array", "items": {"$ref": "#/$defs/param"}}, "return_type": {"type": "string"},
                   "contracts": {"type": "array", "items": _BUILTIN_CONTRACT}},
}

_CONTEXT_FUNCTION = {
    "type": "object",
    "required": ["name", "signature", "params", "return_type", "span", "contracts", "variables", "calls",
                 "builtins_called", "called_by", "recursive", "examples", "loops"],
    "properties": {
        "name": {"type": "string"},
        "signature": {"type": "string"},
        "params": {"type": "array", "items": {"$ref": "#/$defs/param"}},
        "return_type": {"type": "string"},
        "span": {"$ref": "#/$defs/span"},
        "contracts": {"type": "array", "items": {
            "type": "object", "required": ["clause", "condition", "message", "line"],
            "properties": {"clause": {"enum": ["requires", "ensures"]},
                           "condition": {"type": "string", "description": "The condition, as written in the source."},
                           "message": {**_NULLABLE_STRING, "description": "The explanation written after the "
                                                                          "condition, if any."},
                           "line": {"type": "integer", "minimum": 1}}}},
        "variables": {"type": "array", "items": {
            "type": "object", "required": ["name", "type", "line", "mutable"],
            "properties": {"name": {"type": "string"}, "type": _NULLABLE_STRING,
                           "line": {"type": "integer", "minimum": 1},
                           "mutable": {"type": "boolean", "description": "True if declared with 'var'."}}}},
        "calls": {"type": "array", "items": {"type": "string"},
                  "description": "Functions of the program this one calls, sorted, without repetitions."},
        "builtins_called": {"type": "array", "items": {"type": "string"}},
        "called_by": {"type": "array", "items": {"type": "string"}},
        "recursive": {"type": "boolean", "description": "True if the function can reach itself through calls."},
        "examples": {"type": "array", "description": "The 'example' clauses of the function, as written. The "
                                                     "analysis never evaluates them; only `nex test` does.",
                     "items": {
                         "type": "object", "required": ["condition", "message", "line"],
                         "properties": {"condition": {"type": "string", "description": "The expression, as written."},
                                        "message": {**_NULLABLE_STRING,
                                                    "description": "The explanation written after it, if any."},
                                        "line": {"type": "integer", "minimum": 1}}}},
        "loops": {"type": "array", "description": "The loops of the function, in source order, with the "
                                                  "requirements each one declares. Checked on every turn when "
                                                  "the program runs; the analysis never evaluates them.",
                  "items": {
                      "type": "object", "required": ["line", "kind", "condition", "invariants", "measure"],
                      "properties": {
                          "line": {"type": "integer", "minimum": 1},
                          "kind": {"enum": ["while", "for"],
                                   "description": "Which form of loop this is."},
                          "condition": {"type": "string",
                                        "description": "The text after the keyword: the condition of a 'while', "
                                                       "or 'name in iterable' for a 'for'."},
                          "invariants": {"type": "array", "items": {"$ref": "#/$defs/loop_clause"}},
                          "measure": {"oneOf": [{"$ref": "#/$defs/loop_clause"}, {"type": "null"}],
                                      "description": "The 'decreases' clause. Null for every 'for' loop and "
                                                     "in a program with errors (E2021)."}}}},
    },
}

_LOOP_CLAUSE = {
    "type": "object", "required": ["condition", "message", "line"],
    "properties": {"condition": {"type": "string", "description": "The expression, as written."},
                   "message": {**_NULLABLE_STRING, "description": "The explanation written after it, if any."},
                   "line": {"type": "integer", "minimum": 1}},
}


_CONTEXT_TYPE = {
    "type": "object",
    "required": ["name", "base", "root", "condition", "message", "line"],
    "properties": {
        "name": {"type": "string"},
        "base": {"type": "string", "description": "The type it refines, as written."},
        "root": {**_NULLABLE_STRING, "description": "The built-in type its values have. Null when the declaration "
                                                    "has an error."},
        "condition": {"type": "string", "description": "The condition after 'where', as written in the source."},
        "message": {**_NULLABLE_STRING, "description": "The explanation written after the condition, if any."},
        "line": {"type": "integer", "minimum": 1},
    },
}

_CONTEXT_RECORD_FIELD = {
    "type": "object",
    "required": ["name", "type"],
    "properties": {
        "name": {"type": "string", "description": "The name of the field."},
        "type": {**_NULLABLE_STRING, "description": "The type of the field. Null when it could not be resolved."},
    },
}

_CONTEXT_RECORD = {
    "type": "object",
    "required": ["name", "fields", "valid", "line", "reason"],
    "properties": {
        "name": {"type": "string", "description": "The name of the record type."},
        "fields": {"type": "array", "items": {"$ref": "#/$defs/record_field"},
                   "description": "The fields of the record, in the order of the declaration."},
        "valid": {"type": "boolean", "description": "True when the declaration can be used as a type."},
        "line": {"type": "integer", "minimum": 1},
        "reason": {**_NULLABLE_STRING, "description": "Why the declaration cannot be used, if it cannot."},
    },
}


_TEST_CALL = {
    "type": "object",
    "required": ["call", "span", "type", "status", "value"],
    "properties": {
        "call": {"type": "string", "description": "The call, as written in the source."},
        "span": {"$ref": "#/$defs/span"},
        "type": {**_NULLABLE_STRING, "description": "Its type, from the static analysis."},
        "status": {"enum": ["returned", "stopped"],
                   "description": "'returned': it returned a value. 'stopped': it was invoked, but the evaluation "
                                  "stopped inside it."},
        "value": {**_NULLABLE_STRING, "description": "The value it returned, written as in the source. Null only "
                                                    "when status is 'stopped': NEXORA has no null value."},
    },
}

_TEST_SKIPPED_CALL = {
    "type": "object",
    "required": ["call", "span", "type", "reason"],
    "properties": {
        "call": {"type": "string"},
        "span": {"$ref": "#/$defs/span"},
        "type": _NULLABLE_STRING,
        "reason": {"enum": ["short_circuit", "stopped_before"],
                   "description": "'short_circuit': in an operand that 'and' or 'or' did not need. "
                                  "'stopped_before': the evaluation stopped before reaching it."},
    },
}

_TEST_EXAMPLE = {
    "type": "object",
    "required": ["function", "index", "span", "expression", "message", "status", "values", "not_evaluated",
                 "diagnostic", "output"],
    "properties": {
        "function": {"type": "string", "description": "The function that declares the example."},
        "index": {"type": "integer", "minimum": 1,
                  "description": "Its position among the examples of that function, from 1."},
        "span": {"$ref": "#/$defs/span"},
        "expression": {"type": "string", "description": "The expression of the example, as written."},
        "message": {**_NULLABLE_STRING, "description": "The explanation written after it, if any."},
        "status": {"enum": ["passed", "failed", "error"]},
        "values": {"type": "array", "items": {"$ref": "#/$defs/call"},
                   "description": "The own calls that were invoked, in the order they were invoked."},
        "not_evaluated": {"type": "array", "items": {"$ref": "#/$defs/skipped_call"},
                          "description": "The own calls that were never invoked, in the order of the text."},
        "diagnostic": {"oneOf": [{"$ref": "#/$defs/diagnostic"}, {"type": "null"}],
                       "description": "Null if passed; E4004 if failed; the original diagnostic, with a note "
                                      "naming the example, if error."},
        "output": {"type": "string", "description": "What was printed while the example was evaluated."},
    },
}


_COMPLETE = {
    "type": "boolean",
    "description": "True when the analysis covers the whole file. False when syntax errors left out the "
                   "statements and functions that have them, or when there is no structure at all.",
}


def all_schemas() -> dict[str, dict]:
    """Every schema, keyed by the file name it has in docs/schemas/."""
    base = {"span": SPAN, "diagnostic": DIAGNOSTIC}
    nullable = lambda schema: {"oneOf": [schema, {"type": "null"}]}  # noqa: E731

    diagnostics = _document(
        "nexora-diagnostics", "nexora.diagnostics/1: the result of a static analysis",
        _header("nexora.diagnostics/1"), _HEADER_REQUIRED, base,
    )
    inspect = _document(
        "nexora-inspect", "nexora.inspect/2: the syntax tree of a program",
        {**_header("nexora.inspect/2"),
         "complete": _COMPLETE,
         "program": {**nullable({"$ref": "#/$defs/Program"}),
                     "description": "Partial when 'complete' is false. Null when the source has lexical errors."}},
        [*_HEADER_REQUIRED, "complete", "program"], {**base, **node_definitions()},
    )
    symbols = _document(
        "nexora-symbols", "nexora.symbols/1: the names a program declares and where they are used",
        {**_header("nexora.symbols/1"),
         "complete": _COMPLETE,
         "filter": {"type": "object", "required": ["name", "function"],
                    "properties": {"name": _NULLABLE_STRING, "function": _NULLABLE_STRING}},
         "symbols": {**nullable({"type": "array", "items": {"$ref": "#/$defs/symbol"}}),
                     "description": "Partial when 'complete' is false. Null when the source has lexical errors."},
         "builtins": {"type": "array", "items": {"$ref": "#/$defs/builtin"}}},
        [*_HEADER_REQUIRED, "complete", "filter", "symbols", "builtins"],
        {**base, "param": _PARAM, "symbol": _SYMBOL, "builtin": _BUILTIN},
    )
    context = _document(
        "nexora-context", "nexora.context/1: a technical summary of a program",
        {**_header("nexora.context/1"),
         "executed": {"const": False, "description": "The program is never run to produce this document."},
         "lines": {"type": "integer", "minimum": 0},
         "analysed": {"type": "boolean",
                      "description": "False when the source has lexical errors: there is no structure."},
         "complete": _COMPLETE,
         "entry_point": _NULLABLE_STRING,
         "types": {**nullable({"type": "array", "items": {"$ref": "#/$defs/type"}}),
                   "description": "The refined types the program declares. Null when there is no structure."},
         "records": {**nullable({"type": "array", "items": {"$ref": "#/$defs/record"}}),
                     "description": "The record types the program declares. Null when there is no structure."},
         "functions": nullable({"type": "array", "items": {"$ref": "#/$defs/function"}}),
         "features": nullable({"type": "array", "items": {"type": "string"}}),
         "reserved_words_used": {**nullable({"type": "array", "items": {"type": "string"}}),
                                 "description": "Words reserved for unimplemented features. Null if the text "
                                                "could not be split into tokens."},
         "notes": {"type": "array", "items": {"type": "string"}}},
        [*_HEADER_REQUIRED, "executed", "lines", "analysed", "complete", "entry_point", "types", "records",
         "functions", "features", "reserved_words_used", "notes"],
        {**base, "param": _PARAM, "function": _CONTEXT_FUNCTION, "type": _CONTEXT_TYPE, "loop_clause": _LOOP_CLAUSE,
         "record": _CONTEXT_RECORD, "record_field": _CONTEXT_RECORD_FIELD},
    )
    spec = _document(
        "nexora-spec", "nexora.spec/1: the language specification, or one section of it",
        {"schema": {"const": "nexora.spec/1"},
         "nexora_version": {"type": "string"},
         "available": {"type": "boolean",
                       "description": "False when NEXORA was installed without its documentation."},
         "spec_version": _NULLABLE_STRING,
         "language": {"const": "es", "description": "The specification is written in Spanish."},
         "sections": {"type": "array", "items": {
             "type": "object", "required": ["id", "title", "level"],
             "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "level": {"enum": [2, 3]}}}},
         "section": nullable({"type": "object", "required": ["id", "title", "text"],
                              "properties": {"id": {"type": "string"}, "title": {"type": "string"},
                                             "text": {"type": "string", "description": "Markdown."}}})},
        ["schema", "nexora_version", "available", "spec_version", "language", "sections", "section"], {},
    )
    capabilities = _document(
        "nexora-capabilities", "nexora.capabilities/1: what this version of NEXORA is",
        {"schema": {"const": "nexora.capabilities/1"},
         "nexora_version": {"type": "string"},
         "language": {"type": "object", "required": ["keywords", "reserved_words", "types", "builtins"],
                      "properties": {"keywords": {"type": "array", "items": {"type": "string"}},
                                     "reserved_words": {"type": "array", "items": {"type": "string"}},
                                     "types": {"type": "array", "items": {"type": "string"}},
                                     "builtins": {"type": "array", "items": {"$ref": "#/$defs/builtin"}}}},
         "diagnostics": {"type": "array", "items": {
             "type": "object", "required": ["code", "message", "category"],
             "properties": {"code": {"type": "string"}, "message": {"type": "string"},
                            "category": {"type": "string"}}}},
         "limits": {"type": "object", "additionalProperties": {"type": "integer"}},
         "schemas": {"type": "array", "items": {"type": "string"}},
         "analysis_executes_code": {
             "const": False,
             "description": "The analysis never runs the program: no statement or function is executed. It only "
                            "evaluates the conditions of refined types on literal constants; those conditions call "
                            "no function of the program, and the work is bounded (limit max_refinement_steps)."}},
        ["schema", "nexora_version", "language", "diagnostics", "limits", "schemas", "analysis_executes_code"],
        {"param": _PARAM, "builtin": _BUILTIN},
    )
    test = _document(
        "nexora-test", "nexora.test/1: the outcome of evaluating the 'example' clauses of a program (nex test)",
        {**_header("nexora.test/1"),
         "status": {"enum": ["passed", "failed", "no_examples", "not_run"],
                    "description": "'ok' is the result of the static analysis; this is the result of the examples."},
         "filter": {"type": "object", "required": ["function"], "properties": {"function": _NULLABLE_STRING}},
         "summary": {"oneOf": [{"type": "object", "required": ["total", "passed", "failed", "error"],
                                "properties": {name: {"type": "integer", "minimum": 0}
                                               for name in ("total", "passed", "failed", "error")}},
                               {"type": "null"}],
                     "description": "Counts of the selected examples. Null when nothing was evaluated."},
         "examples": {"oneOf": [{"type": "array", "items": {"$ref": "#/$defs/example"}}, {"type": "null"}],
                      "description": "One result per selected example, in the order of evaluation. Null when "
                                     "nothing was evaluated (not_run)."}},
        [*_HEADER_REQUIRED, "status", "filter", "summary", "examples"],
        {**base, "example": _TEST_EXAMPLE, "call": _TEST_CALL, "skipped_call": _TEST_SKIPPED_CALL},
    )
    result = _document(
        "nexora-result", "nexora.result/1: the outcome of checking or running a program (nexora.api, playground)",
        {"schema": {"const": "nexora.result/1"},
         "action": {"enum": ["check", "run"]},
         "status": {"enum": ["success", "invalid", "runtime_error", "contract_violation", "output_limit",
                             "memory_limit", "timeout"],
                    "description": "'timeout' is added by a host that stops the process; the core never returns it."},
         "output": {"type": "string"},
         "diagnostics": {"type": "array", "items": {"$ref": "#/$defs/diagnostic"}},
         "message": _NULLABLE_STRING},
        ["schema", "action", "status", "output", "diagnostics", "message"], base,
    )
    return {
        "nexora-diagnostics.schema.json": diagnostics,
        "nexora-inspect.schema.json": inspect,
        "nexora-symbols.schema.json": symbols,
        "nexora-context.schema.json": context,
        "nexora-spec.schema.json": spec,
        "nexora-capabilities.schema.json": capabilities,
        "nexora-result.schema.json": result,
        "nexora-test.schema.json": test,
    }

"""D01/B7: the `shrinks` measure decision uses the type model, keeping observable semantics.

Before B7 `Checker._while` compared the rooted measure type with the string `Int`. Now the rooted
type is resolved with `_current_type_model` and decided with `equal` against `type_model.INT`. A
name outside the model (`ANY_VALUE`, unknown names, unenabled generics, dropped refinements) is not
an Int and keeps the same diagnostic. The legacy decision is kept here as an independent reference
(`legacy_while`) that never uses the model to decide whether the measure is valid.

Only the measure decision changes: the expression is still evaluated once, and the message, hint,
span, notes, the `keeps` branch, the `E2021` checks and the loop body are untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexora import ast_nodes as ast
from nexora import tooling
from nexora import types as type_model
from nexora.checker import ANY_VALUE, Checker, Symbol, _Scope
from nexora.diagnostics import Source, Span
from nexora.pipeline import analyze
from nexora.type_adapter import TypeAdapter
from nexora.values import BOOL, FLOAT, INT, TEXT, VOID

from helpers import in_main, parse_text, with_main

PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "percent"'
SMALL = 'type Small = Percent where value < 10, "small"'
ACCEPTED = "type Accepted = Bool where value"
DROPPED = "type Child = Parent where value > 0\ntype Parent = Int where value + 1"
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples"
SPAN = Span(1, 1, 1, 3)
HINT = "The measure is a whole number that gets smaller on every turn and never goes below 0."


def checker_with_types(text: str) -> Checker:
    """A checker whose refined-type registry comes from `text` (declarations only)."""
    program, _ = parse_text(text)
    checker = Checker()
    checker.require_main = False
    checker.check(program)
    return checker


def legacy_while(self: Checker, statement: ast.While, scope: _Scope) -> None:
    """The reference `_while` from before B7, with the old root-string measure decision.

    Its measure check uses `_root` and a string comparison with `Int`; it never calls
    `_current_type_model` nor the model's `equal` to decide whether the measure is valid.
    """
    self._condition(statement.condition, scope, "'while'")
    measures = [clause for clause in statement.clauses if clause.clause == "shrinks"]
    for clause in statement.clauses:
        if clause.clause == "keeps":
            self._condition(clause.condition, scope, "'keeps'")
            continue
        found = self._expression(clause.condition, scope)
        if found is not None and self._root(found) != INT:
            self._report(
                "E2011",
                f"The measure of 'shrinks' must be Int, found {found}",
                clause.condition.span,
                hint=HINT,
            )
    if not measures:
        keyword = statement.span
        self._report(
            "E2021",
            "This loop does not say why it ends",
            Span(keyword.line, keyword.column, keyword.line, keyword.column + len("while")),
            hint="Add 'shrinks <expression>' to the header of the loop, with an Int that gets smaller on "
                 "every turn and never goes below 0, for example 'shrinks n - i'.",
        )
    for extra in measures[1:]:
        first = measures[0].span
        self._report(
            "E2021",
            "A loop has exactly one measure",
            extra.span,
            hint="Combine them into one Int that gets smaller on every turn.",
            notes=(f"The first 'shrinks' is at line {first.line}, column {first.column}.",),
        )
    self._block(statement.body, _Scope(scope))


def check_pair(monkeypatch, text: str, *, require_main: bool = True):
    """Check `text` with the new and the legacy `_while`, on independent checkers."""
    program, _ = parse_text(text)
    new_checker = Checker()
    new_checker.require_main = require_main
    new_checked, new_diagnostics = new_checker.check(program)

    with monkeypatch.context() as patch:
        patch.setattr(Checker, "_while", legacy_while)
        old_checker = Checker()
        old_checker.require_main = require_main
        old_checked, old_diagnostics = old_checker.check(program)

    assert new_diagnostics == old_diagnostics
    assert new_checked.types == old_checked.types
    assert new_checked.symbols == old_checked.symbols
    assert new_checked.calls == old_checked.calls
    assert new_checked.refined == old_checked.refined
    assert new_checked.functions == old_checked.functions
    return new_checked, new_diagnostics, old_checked, old_diagnostics


def parse_loop(measure: str = "m", condition: str = "true") -> ast.While:
    """A parsed `while` whose only clause is `shrinks {measure}` and whose body is empty."""
    program, _ = parse_text(in_main(f"while {condition}\n    shrinks {measure}\n{{\n}}"))
    (loop,) = program.functions[0].body.statements
    assert isinstance(loop, ast.While)
    return loop


def scope_with(found: str | None) -> _Scope:
    """A scope that declares the measure variable `m` with the string type `found`."""
    scope = _Scope()
    scope.names["m"] = Symbol("m", "variable", found, SPAN, "main", None)
    return scope


def pinned_checker(found: str | None) -> Checker:
    """A checker where every expression has the string type `found`.

    The loop condition is pinned too, so only the measure decision runs. `ANY_VALUE`,
    `Range[Int]`, unknown names and dropped refinements cannot be the type of a real
    expression (the adapter would reject recording them), so they are supplied here.
    """
    checker = Checker()
    checker._condition = lambda condition, scope, owner: None
    checker._expression = lambda condition, scope: found
    return checker


def measure_case(found: str | None, registry: str = ""):
    """Run the new `_while` and the legacy reference over the same loop and type.

    Returns `(new_diagnostics, old_diagnostics)`, each sliced from the checker's previous state.
    """
    loop = parse_loop()
    new_checker = checker_with_types(registry) if registry else Checker()
    old_checker = checker_with_types(registry) if registry else Checker()
    for checker in (new_checker, old_checker):
        checker._condition = lambda condition, scope, owner: None
        checker._expression = lambda condition, scope: found
    new_start, old_start = len(new_checker._diagnostics), len(old_checker._diagnostics)
    new_checker._while(loop, scope_with(found))
    legacy_while(old_checker, loop, scope_with(found))
    return new_checker._diagnostics[new_start:], old_checker._diagnostics[old_start:]


# A. The decision table


def test_the_measure_decision_matches_legacy_for_every_type():
    cases = (
        (INT, ""),
        (FLOAT, ""),
        (BOOL, ""),
        (TEXT, ""),
        (VOID, ""),
        (ANY_VALUE, ""),
        ("Range[Int]", ""),
        ("Missing", ""),
        (None, ""),
        ("Percent", PERCENT),
        ("Small", f"{PERCENT}\n{SMALL}"),
        ("Accepted", ACCEPTED),
        ("Parent", DROPPED),
    )
    for found, registry in cases:
        new_diagnostics, old_diagnostics = measure_case(found, registry)
        assert new_diagnostics == old_diagnostics, found


def test_the_measure_decision_accepts_only_an_int_root():
    accepted = ((INT, ""), ("Percent", PERCENT), ("Small", f"{PERCENT}\n{SMALL}"))
    rejected = (
        (FLOAT, ""),
        (BOOL, ""),
        (TEXT, ""),
        (VOID, ""),
        (ANY_VALUE, ""),
        ("Range[Int]", ""),
        ("Missing", ""),
        ("Accepted", ACCEPTED),
        ("Parent", DROPPED),
    )
    for found, registry in accepted:
        new_diagnostics, old_diagnostics = measure_case(found, registry)
        assert new_diagnostics == old_diagnostics == [], found
    for found, registry in rejected:
        new_diagnostics, old_diagnostics = measure_case(found, registry)
        assert new_diagnostics == old_diagnostics, found
        assert [diagnostic.code for diagnostic in new_diagnostics] == ["E2011"], found


# B. Exact diagnostics


def test_a_rejected_measure_keeps_the_complete_diagnostic():
    loop = parse_loop()
    for found in (FLOAT, BOOL, TEXT, VOID):
        new_diagnostics, old_diagnostics = measure_case(found)
        assert new_diagnostics == old_diagnostics
        (error,) = new_diagnostics
        assert error.code == "E2011"
        assert error.label == f"The measure of 'shrinks' must be Int, found {found}"
        assert error.hint == HINT
        assert error.span == loop.clauses[0].condition.span
        assert error.notes == ()


def test_the_message_of_a_rejected_refinement_uses_its_name_not_its_root():
    new_diagnostics, old_diagnostics = measure_case("Accepted", ACCEPTED)
    assert new_diagnostics == old_diagnostics
    (error,) = new_diagnostics
    assert error.label == "The measure of 'shrinks' must be Int, found Accepted"
    assert "Bool" not in error.label


# C. Refined types in real loops


def test_refined_measures_in_real_loops(monkeypatch):
    text = with_main(
        f"{PERCENT}\n{SMALL}\n{ACCEPTED}",
        "var i = 0\n"
        "while i < 3\n"
        "    shrinks Percent(3 - i)\n"
        "{\n"
        "    i = i + 1\n"
        "}\n"
        "var j = 0\n"
        "while j < 3\n"
        "    shrinks Small(3 - j)\n"
        "{\n"
        "    j = j + 1\n"
        "}\n"
        "var ok: Accepted = true\n"
        "var k = 0\n"
        "while k < 3\n"
        "    shrinks ok\n"
        "{\n"
        "    k = k + 1\n"
        "}\n"
        "print(i + j + k)\n",
    )
    new_checked, diagnostics, old_checked, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    (error,) = diagnostics
    assert error.label == "The measure of 'shrinks' must be Int, found Accepted"
    new_symbols = {symbol.name: symbol.type for symbol in new_checked.symbols}
    old_symbols = {symbol.name: symbol.type for symbol in old_checked.symbols}
    assert new_symbols["ok"] == old_symbols["ok"] == "Accepted"


# D. Unresolved expressions, Void and ordering


def test_an_unresolved_measure_adds_no_second_diagnostic(monkeypatch):
    text = in_main("var i = 0\nwhile i < 3\n    shrinks missing\n{\n    i = i + 1\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2005"]
    assert all("measure" not in diagnostic.label for diagnostic in diagnostics)


def test_a_void_measure_is_rejected(monkeypatch):
    text = in_main("var i = 0\nwhile i < 3\n    shrinks print(1)\n{\n    i = i + 1\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    (error,) = diagnostics
    assert error.code == "E2011"
    assert error.label == "The measure of 'shrinks' must be Int, found Void"
    assert error.hint == HINT


def test_clause_diagnostics_keep_their_order_and_notes(monkeypatch):
    text = in_main(
        "var i = 0\n"
        "var b = true\n"
        "while i\n"
        "    keeps 1\n"
        "    shrinks b\n"
        "    shrinks 1.5\n"
        "{\n"
        "    i = i + 1\n"
        "}"
    )
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011", "E2011", "E2011", "E2021"]
    assert diagnostics == old_diagnostics
    labels = [diagnostic.label for diagnostic in diagnostics]
    assert labels[0] == "The condition of 'while' must be Bool, found Int"
    assert labels[1] == "The condition of 'keeps' must be Bool, found Int"
    assert labels[2] == "The measure of 'shrinks' must be Int, found Bool"
    assert labels[3] == "The measure of 'shrinks' must be Int, found Float"
    assert labels[4] == "A loop has exactly one measure"
    assert diagnostics[4].notes == ("The first 'shrinks' is at line 6, column 9.",)
    assert (diagnostics[3].span.line, diagnostics[3].span.column) == (7, 17)
    assert (diagnostics[4].span.line, diagnostics[4].span.column) == (7, 9)


def test_a_loop_without_a_measure_is_unchanged(monkeypatch):
    text = in_main("var i = 0\nwhile i < 3 {\n    i = i + 1\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    (error,) = diagnostics
    assert (error.code, error.label) == ("E2021", "This loop does not say why it ends")
    assert "shrinks n - i" in error.hint


# E. Real valid measures


def test_valid_arithmetic_and_refined_measures_are_differentially_equivalent(monkeypatch):
    text = with_main(
        f"{PERCENT}\n{SMALL}",
        "var i = 0\n"
        "while i < 10\n"
        "    shrinks 10 - i\n"
        "{\n"
        "    i = i + 1\n"
        "}\n"
        "var j = 0\n"
        "while j < 10\n"
        "    shrinks 10 - 2 * j\n"
        "{\n"
        "    j = j + 1\n"
        "}\n"
        "var k = 0\n"
        "while k < 10\n"
        "    shrinks Percent(10 - k)\n"
        "{\n"
        "    k = k + 1\n"
        "}\n"
        "var l = 0\n"
        "while l < 10\n"
        "    shrinks Small(10 - l)\n"
        "{\n"
        "    l = l + 1\n"
        "}\n"
        "print(i + j + k + l)\n",
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert diagnostics == []


def test_a_text_length_measure_is_valid(monkeypatch):
    text = in_main(
        'var t = "abc"\n'
        'var i = 0\n'
        'while i < Text.length(t)\n'
        '    shrinks Text.length(t) - i\n'
        '{\n'
        '    i = i + 1\n'
        '}\n'
        'print(i)\n'
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert diagnostics == []


# F. The model bridge


def test_a_missing_primitive_model_raises(monkeypatch):
    checker = pinned_checker(INT)
    real = checker._type_adapter.resolve
    monkeypatch.setattr(
        checker._type_adapter, "resolve", lambda name, real=real: None if name == INT else real(name)
    )
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._while(parse_loop(), scope_with(INT))


def test_a_missing_refined_model_raises(monkeypatch):
    checker = checker_with_types(PERCENT)
    checker._condition = lambda condition, scope, owner: None
    checker._expression = lambda condition, scope: "Percent"
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
        checker._while(parse_loop(), scope_with("Percent"))


def test_the_measure_bridge_does_not_hide_a_missing_primitive(monkeypatch):
    # `_root` is pinned so the failure comes from `_while`'s own `_current_type_model` path.
    checker = pinned_checker(INT)
    real = checker._type_adapter.resolve
    monkeypatch.setattr(checker, "_root", lambda kind: INT)
    monkeypatch.setattr(
        checker._type_adapter, "resolve", lambda name, real=real: None if name == INT else real(name)
    )
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._while(parse_loop(), scope_with(INT))


def test_the_measure_bridge_does_not_hide_a_missing_refined(monkeypatch):
    checker = checker_with_types(PERCENT)
    checker._condition = lambda condition, scope, owner: None
    checker._expression = lambda condition, scope: "Percent"
    monkeypatch.setattr(checker, "_root", lambda kind: "Percent")
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
        checker._while(parse_loop(), scope_with("Percent"))


def test_a_historical_refinement_is_not_accepted_again():
    checker = checker_with_types(DROPPED)
    assert "Parent" not in checker._refined
    historical = {type_model.display(kind) for kind in checker._type_adapter.resolved_types.values()}
    assert "Parent" in historical

    new_diagnostics, old_diagnostics = measure_case("Parent", DROPPED)
    assert new_diagnostics == old_diagnostics
    (error,) = new_diagnostics
    assert error.code == "E2011"
    assert error.label == "The measure of 'shrinks' must be Int, found Parent"


def test_no_measure_operation_was_added_to_the_model_or_adapter():
    for name in ("measure_type", "measure_result", "decreases_type", "is_measure", "assignable_measure"):
        assert not hasattr(type_model, name)
        assert not hasattr(TypeAdapter(), name)


def test_the_legacy_reference_reproduces_the_pre_b7_behaviour():
    accepted = Checker()
    legacy_while(accepted, parse_loop(), scope_with(INT))
    assert accepted._diagnostics == []

    rejected = Checker()
    legacy_while(rejected, parse_loop(), scope_with(FLOAT))
    (error,) = rejected._diagnostics
    assert error.code == "E2011"
    assert error.label == "The measure of 'shrinks' must be Int, found Float"


# G. Differential over the examples


def test_the_measure_decision_is_differentially_equivalent_on_examples(monkeypatch):
    """The model-backed measure decision must produce the same analysis and the same documents."""
    builders = {
        "check": tooling.check_source,
        "inspect": tooling.inspect_source,
        "symbols": tooling.get_symbols,
        "context": tooling.get_context,
    }
    paths = sorted(EXAMPLE_DIR.rglob("*.nex"))
    assert len(paths) == 26
    for path in paths:
        text = path.read_text(encoding="utf-8")
        program, _ = parse_text(text)

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)
        new_documents = {name: builder(text) for name, builder in builders.items()}

        with monkeypatch.context() as patch:
            patch.setattr(Checker, "_while", legacy_while)
            old_checker = Checker()
            old_checked, old_diagnostics = old_checker.check(program)
            old_documents = {name: builder(text) for name, builder in builders.items()}

        assert new_diagnostics == old_diagnostics, path
        assert new_checked.types == old_checked.types, path
        assert new_checked.symbols == old_checked.symbols, path
        assert new_checked.calls == old_checked.calls, path
        assert new_checked.refined == old_checked.refined, path
        assert new_checked.functions == old_checked.functions, path
        assert new_documents == old_documents, path


# H. Public contracts


def test_public_type_surface_is_unchanged():
    text = with_main(
        f"{PERCENT}\n{SMALL}\n{ACCEPTED}",
        "var i = 0\n"
        "while i < 3\n"
        "    shrinks Percent(3 - i)\n"
        "{\n"
        "    i = i + 1\n"
        "}\n"
        "print(i)\n",
    )
    analysis = analyze(Source("test.nex", text))
    assert analysis.diagnostics == ()
    assert analysis.checked is not None

    assert analysis.types == analysis.checked.types
    assert all(isinstance(kind, str) for kind in analysis.checked.types.values())

    symbols = {symbol.name: symbol for symbol in analysis.checked.symbols}
    assert symbols["i"].type == "Int"
    assert isinstance(symbols["i"].type, str)

    documents = {
        "check": tooling.check_source(text),
        "inspect": tooling.inspect_source(text),
        "symbols": tooling.get_symbols(text),
        "context": tooling.get_context(text),
    }
    for document in documents.values():
        json.dumps(document)

    builtins = {entry["name"]: entry for entry in documents["symbols"]["builtins"]}
    assert builtins["print"]["signature"] == "fn print(value: Int | Float | Bool | Text)"

    types = {entry["name"]: entry for entry in documents["context"]["types"]}
    assert (types["Percent"]["root"], types["Small"]["root"], types["Accepted"]["root"]) == (
        "Int",
        "Int",
        "Bool",
    )

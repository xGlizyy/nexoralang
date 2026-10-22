"""D01/B4: `Checker._condition` decides with the type model, keeping the observable semantics.

The condition of an `if`, a `while`, an `invariant`, a contract, an `example` or a `where`
must be `Bool`. Before B4 the checker compared `_root(found)` with the string `"Bool"`. Now a
representable `found` is decided with `assignable(Bool, found)`; only a name outside the model
keeps the old root comparison, and a representable type missing from the model raises instead
of being hidden by the fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexora import ast_nodes as ast
from nexora import tooling
from nexora.checker import ANY_VALUE, Checker, Symbol, _Scope
from nexora.diagnostics import Source, Span
from nexora.pipeline import analyze
from nexora.values import BOOL, FLOAT, INT, VOID

from helpers import in_main, parse_text, with_main

PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "percent"'
SMALL = 'type Small = Percent where value < 10, "small"'
ACCEPTED = "type Accepted = Bool where value"
DROPPED = "type Child = Parent where value > 0\ntype Parent = Int where value + 1"
SPAN = Span(1, 1, 1, 3)
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples"


def shadow(text: str, *, require_main: bool = True) -> tuple[Checker, object, list]:
    """Check a source and return the checker, the checked program and its diagnostics."""
    program, _ = parse_text(text)
    checker = Checker()
    checker.require_main = require_main
    checked, diagnostics = checker.check(program)
    return checker, checked, diagnostics


def legacy_condition(checker: Checker, condition: ast.Expr, scope: _Scope, owner: str) -> None:
    """The reference `_condition` from before B4, with the old root-string decision."""
    found = checker._expression(condition, scope)
    if found is None or checker._root(found) == BOOL:
        return
    hint = None
    if found in (INT, FLOAT):
        hint = "A number is not a condition. Compare it explicitly, for example: x != 0"
    elif found == VOID:
        hint = "A call to a Void function does not produce a value."
    checker._report("E2011", f"The condition of {owner} must be Bool, found {found}", condition.span, hint=hint)


def scope_with(name: str, kind: str):
    """A builder for a scope that declares `name` with the string type `kind`."""
    def build() -> _Scope:
        scope = _Scope()
        scope.names[name] = Symbol(name, "variable", kind, SPAN, "main", None)
        return scope
    return build


def condition_pair(text: str, condition: ast.Expr, owner: str = "'if'", scope_builder=None) -> tuple[list, list]:
    """Run the current and legacy `_condition` on independent checkers over the same source."""
    new_checker, _, new_diagnostics = shadow(text)
    old_checker, _, old_diagnostics = shadow(text)
    assert new_diagnostics == old_diagnostics
    new_scope = scope_builder() if scope_builder else _Scope()
    old_scope = scope_builder() if scope_builder else _Scope()
    new_start, old_start = len(new_checker._diagnostics), len(old_checker._diagnostics)
    new_checker._condition(condition, new_scope, owner)
    legacy_condition(old_checker, condition, old_scope, owner)
    return new_checker._diagnostics[new_start:], old_checker._diagnostics[old_start:]


def outside_model_condition(found, text: str | None = None, owner: str = "'if'") -> tuple[list, list]:
    """Run new and legacy `_condition` with `_expression` pinned to `found`.

    Production reaches `_condition` through `_expression`, which records every non-None type
    in the adapter and therefore rejects a name outside the model before the decision. This
    direct test isolates the fallback branch that B4 keeps for those names, and the synthetic
    cases (`ANY_VALUE`, a dropped refinement) that no public program can produce today.
    """
    if text is None:
        new_checker, old_checker = Checker(), Checker()
    else:
        new_checker, _, new_diagnostics = shadow(text)
        old_checker, _, old_diagnostics = shadow(text)
        assert new_diagnostics == old_diagnostics
    node = ast.BoolLiteral(span=SPAN, value=True)
    new_checker._expression = lambda condition, scope: found
    old_checker._expression = lambda condition, scope: found
    new_start, old_start = len(new_checker._diagnostics), len(old_checker._diagnostics)
    new_checker._condition(node, _Scope(), owner)
    legacy_condition(old_checker, node, _Scope(), owner)
    return new_checker._diagnostics[new_start:], old_checker._diagnostics[old_start:]


def check_pair(monkeypatch, text: str, *, require_main: bool = True):
    """Check `text` with the new and the legacy `_condition`, on independent checkers."""
    program, _ = parse_text(text)
    new_checker = Checker()
    new_checker.require_main = require_main
    new_checked, new_diagnostics = new_checker.check(program)

    with monkeypatch.context() as patch:
        patch.setattr(Checker, "_condition", legacy_condition)
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


# A. Direct differential


def test_condition_matches_legacy_for_bool():
    new, old = condition_pair(in_main("let n = 1"), ast.BoolLiteral(span=SPAN, value=True))
    assert new == old == []


def test_condition_keeps_the_numeric_label_and_hint():
    new, old = condition_pair(in_main("let n = 1"), ast.IntLiteral(span=SPAN, value=1))
    assert new == old
    assert new[0].label == "The condition of 'if' must be Bool, found Int"
    assert new[0].hint == "A number is not a condition. Compare it explicitly, for example: x != 0"


@pytest.mark.parametrize("node", [
    ast.IntLiteral(span=SPAN, value=1),
    ast.FloatLiteral(span=SPAN, value=1.0),
    ast.TextLiteral(span=SPAN, value="x"),
])
def test_condition_matches_legacy_for_non_bool_literals(node):
    new, old = condition_pair(in_main("let n = 1"), node)
    assert [diagnostic.code for diagnostic in new] == ["E2011"]
    assert new == old


def test_condition_accepts_a_refined_bool():
    text = with_main(ACCEPTED, "let n = 1")
    node = ast.Name(span=SPAN, name="ok")
    new, old = condition_pair(text, node, scope_builder=scope_with("ok", "Accepted"))
    assert new == old == []


def test_condition_rejects_a_refined_int():
    text = with_main(f"{PERCENT}\n{SMALL}", "let n = 1")
    node = ast.Name(span=SPAN, name="p")
    new, old = condition_pair(text, node, scope_builder=scope_with("p", "Small"))
    assert [diagnostic.code for diagnostic in new] == ["E2011"]
    assert new == old


def test_condition_matches_legacy_for_a_void_expression():
    node = ast.Call(span=SPAN, callee="print", callee_span=SPAN, arguments=(ast.IntLiteral(span=SPAN, value=1),))
    new, old = condition_pair(in_main("let n = 1"), node)
    assert new == old
    assert new[0].hint == "A call to a Void function does not produce a value."


def test_condition_matches_legacy_for_an_unknown_name():
    new, old = condition_pair(in_main("let n = 1"), ast.Name(span=SPAN, name="missing"))
    assert [diagnostic.code for diagnostic in new] == ["E2005"]
    assert new == old


def test_condition_exits_immediately_when_found_is_none():
    new, old = outside_model_condition(None)
    assert new == old == []


@pytest.mark.parametrize("found", [ANY_VALUE, "Missing", "Range[Int]"])
def test_condition_keeps_the_legacy_fallback_outside_the_model(found):
    new, old = outside_model_condition(found)
    assert [diagnostic.code for diagnostic in new] == ["E2011"]
    assert new == old


def test_condition_keeps_the_legacy_fallback_for_a_dropped_refinement():
    new, old = outside_model_condition("Parent", text=with_main(DROPPED, "let n = 1"))
    assert [diagnostic.code for diagnostic in new] == ["E2011"]
    assert new == old


def test_condition_does_not_route_through_accepts():
    # B4 resolves `found` and uses `assignable` directly; it must not call `_accepts`, which
    # would resolve the expected `Bool` model as well. This keeps the exact B4 strategy.
    checker, _, diagnostics = shadow(with_main(PERCENT, "let n = 1"))
    assert diagnostics == []

    def fail(*args, **kwargs):
        raise AssertionError("_condition must not call _accepts")

    checker._accepts = fail
    checker._condition(ast.BoolLiteral(span=SPAN, value=True), _Scope(), "'if'")
    checker._condition(ast.IntLiteral(span=SPAN, value=1), _Scope(), "'if'")
    assert [diagnostic.code for diagnostic in checker._diagnostics] == ["E2011"]


def test_condition_does_not_hide_a_missing_primitive_model(monkeypatch):
    node = ast.BoolLiteral(span=SPAN, value=True)
    new_checker, old_checker = Checker(), Checker()
    for checker in (new_checker, old_checker):
        real_resolve = checker._type_adapter.resolve
        monkeypatch.setattr(
            checker._type_adapter, "resolve", lambda name, real=real_resolve: None if name == BOOL else real(name)
        )
        checker._expression = lambda condition, scope: BOOL
    with pytest.raises(RuntimeError, match="primitive type 'Bool' is missing"):
        new_checker._condition(node, _Scope(), "'if'")
    with pytest.raises(RuntimeError, match="primitive type 'Bool' is missing"):
        legacy_condition(old_checker, node, _Scope(), "'if'")


def test_condition_does_not_hide_a_missing_refined_model(monkeypatch):
    node = ast.BoolLiteral(span=SPAN, value=True)
    for implementation in ("new", "legacy"):
        checker, _, diagnostics = shadow(with_main(PERCENT, "let n = 1"))
        assert diagnostics == []
        monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
        checker._expression = lambda condition, scope: "Percent"
        with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
            if implementation == "new":
                checker._condition(node, _Scope(), "'if'")
            else:
                legacy_condition(checker, node, _Scope(), "'if'")


# B. Language contexts


def test_if_condition_is_checked(monkeypatch):
    text = in_main("let n = 1\nif n {\n    print(n)\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'if' must be Bool, found Int"


def test_if_condition_with_a_plain_bool_passes(monkeypatch):
    text = in_main('if true {\n    print("yes")\n}')
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert diagnostics == []


def test_if_condition_with_a_refined_bool_passes(monkeypatch):
    text = with_main(ACCEPTED, "let ok: Accepted = true\nif ok {\n    print(1)\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert diagnostics == []


def test_while_condition_is_checked(monkeypatch):
    text = in_main("var i = 0\nwhile i {\n    decreases 3 - i\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'while' must be Bool, found Int"


def test_while_invariant_is_checked(monkeypatch):
    text = in_main("var i = 0\nwhile i < 3 {\n    invariant 1\n    decreases 3 - i\n}")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'invariant' must be Bool, found Int"


def test_requires_condition_is_checked(monkeypatch):
    text = with_main("fn f(n: Int) -> Int {\n    requires n\n    return n\n}", "print(f(1))")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'requires' must be Bool, found Int"


def test_ensures_condition_is_checked(monkeypatch):
    text = with_main("fn f(n: Int) -> Int {\n    ensures result\n    return n\n}", "print(f(1))")
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'ensures' must be Bool, found Int"


def test_example_condition_is_checked(monkeypatch):
    text = "fn double(n: Int) -> Int {\n    example double(2) + 1\n    return n * 2\n}\n"
    _, diagnostics, _, _ = check_pair(monkeypatch, text, require_main=False)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'example' must be Bool, found Int"


def test_refined_where_condition_is_checked_and_pruned(monkeypatch):
    text = with_main("type Bad = Int where value + 1\ntype Good = Bad where value > 0", "let n = 1")
    new_checked, diagnostics, old_checked, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].label == "The condition of 'where' in 'Bad' must be Bool, found Int"
    assert new_checked.refined == old_checked.refined == {}


def test_a_void_call_is_not_a_condition(monkeypatch):
    text = in_main('if print(1) {\n    print("x")\n}')
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert diagnostics[0].hint == "A call to a Void function does not produce a value."


def test_diagnostic_order_is_preserved_on_a_mixed_program(monkeypatch):
    text = with_main(
        PERCENT,
        "let n = 1\nif n {\n    print(n)\n}\nlet x: Percent = n\nif 1 {\n    print(1)\n}",
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011", "E2011"]


# C. Differential over the examples


def test_condition_is_differentially_equivalent_on_examples(monkeypatch):
    """The model-backed `_condition` must produce the same analysis, and the same documents."""
    builders = {
        "check": tooling.check_source,
        "inspect": tooling.inspect_source,
        "symbols": tooling.get_symbols,
        "context": tooling.get_context,
    }
    paths = sorted(EXAMPLE_DIR.rglob("*.nex"))
    assert len(paths) == 24
    for path in paths:
        text = path.read_text(encoding="utf-8")
        program, _ = parse_text(text)

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)
        new_documents = {name: builder(text) for name, builder in builders.items()}

        with monkeypatch.context() as patch:
            patch.setattr(Checker, "_condition", legacy_condition)
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


# D. Public compatibility


def test_public_type_surface_is_unchanged():
    text = with_main(
        f"{PERCENT}\n{SMALL}\n{ACCEPTED}",
        "let p: Percent = 40\nlet s: Small = 5\nlet ok: Accepted = true\nif ok {\n    print(s)\n}",
    )
    analysis = analyze(Source("test.nex", text))
    assert analysis.diagnostics == ()
    assert analysis.checked is not None

    symbols = {symbol.name: symbol for symbol in analysis.checked.symbols}
    assert (symbols["p"].type, symbols["s"].type, symbols["ok"].type) == ("Percent", "Small", "Accepted")

    # `Analysis.types` and `CheckedProgram.types` stay the public string maps, key by key.
    assert analysis.types == analysis.checked.types

    documents = {
        "check": tooling.check_source(text),
        "inspect": tooling.inspect_source(text),
        "symbols": tooling.get_symbols(text),
        "context": tooling.get_context(text),
    }
    for document in documents.values():
        json.dumps(document)

    builtins = {entry["name"]: entry for entry in documents["symbols"]["builtins"]}
    assert builtins["print"]["signature"] == "fn print(value: Int | Float | Bool | Text) -> Void"

    types = {entry["name"]: entry for entry in documents["context"]["types"]}
    assert (types["Percent"]["base"], types["Percent"]["root"]) == ("Int", "Int")
    assert (types["Small"]["base"], types["Small"]["root"]) == ("Percent", "Int")
    assert (types["Accepted"]["base"], types["Accepted"]["root"]) == ("Bool", "Bool")

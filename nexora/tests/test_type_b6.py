"""D01/B6: the unary-operator type decision is made with the type model, keeping observable semantics.

Before B6 `Checker._unary` compared the already-rooted operand string with `Int`/`Float`/`Bool`.
Now it resolves that operand with `_current_type_model` and decides with `equal`/`display`, keeping
the legacy result for a name outside the model. The legacy decision is kept here as an independent
reference (`legacy_unary`) that never calls the new method nor `_current_type_model`.

Rooting is preserved: `operand = self._root(found)` runs first, so a refined operand is treated as
its base type. The decision is identity, never `assignable`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexora import ast_nodes as ast
from nexora import tooling
from nexora import types as type_model
from nexora.checker import ANY_VALUE, Checker, _Scope
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

UNARY_OPERATORS = ("-", "not")
REPRESENTABLE = (INT, FLOAT, BOOL, TEXT, VOID)
OUTSIDE = ("Missing", ANY_VALUE, "Range[Int]")
ALL_OPERANDS = (*REPRESENTABLE, *OUTSIDE)


def shadow(text: str, *, require_main: bool = True) -> tuple[Checker, object, list]:
    """Check a source and return the checker, the checked program and its diagnostics."""
    program, _ = parse_text(text)
    checker = Checker()
    checker.require_main = require_main
    checked, diagnostics = checker.check(program)
    return checker, checked, diagnostics


def legacy_unary(self: Checker, node: ast.Unary, scope: _Scope) -> str | None:
    """The reference `_unary` from before B6, with the old rooted-string decision.

    It never calls the new method nor `_current_type_model`: only `_root` and name membership.
    """
    found = self._expression(node.operand, scope)
    if found is None:
        return None
    operand = self._root(found)
    if node.operator == "-":
        if operand in (INT, FLOAT):
            return operand
        self._report("E2011", f"Cannot apply '-' to {operand}", node.span, hint="'-' negates an Int or a Float.")
        return None
    if operand == BOOL:
        return BOOL
    hint = "'not' negates a Bool."
    if operand in (INT, FLOAT):
        hint += " To negate a comparison, put it in parentheses: not (a == b)"
    self._report("E2011", f"Cannot apply 'not' to {operand}", node.span, hint=hint)
    return None


def unary_node(operator: str) -> ast.Unary:
    return ast.Unary(span=SPAN, operator=operator, operand=ast.BoolLiteral(span=SPAN, value=True))


def unary_case(text: str, operator: str, found: str | None):
    """Run the new `_unary` and the legacy reference with `_expression` pinned to `found`.

    Independent checkers over the same source, so the only difference is the unary decision.
    Returns `(new_result, old_result, new_diagnostics, old_diagnostics)`.
    """
    new_checker, _, new_diagnostics = shadow(text)
    old_checker, _, old_diagnostics = shadow(text)
    assert new_diagnostics == old_diagnostics
    new_checker._expression = lambda operand, scope: found
    old_checker._expression = lambda operand, scope: found
    new_start, old_start = len(new_checker._diagnostics), len(old_checker._diagnostics)
    new_result = new_checker._unary(unary_node(operator), _Scope())
    old_result = legacy_unary(old_checker, unary_node(operator), _Scope())
    return new_result, old_result, new_checker._diagnostics[new_start:], old_checker._diagnostics[old_start:]


def check_pair(monkeypatch, text: str, *, require_main: bool = True):
    """Check `text` with the new and the legacy `_unary`, on independent checkers."""
    program, _ = parse_text(text)
    new_checker = Checker()
    new_checker.require_main = require_main
    new_checked, new_diagnostics = new_checker.check(program)

    with monkeypatch.context() as patch:
        patch.setattr(Checker, "_unary", legacy_unary)
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


# A. Full operator/operand table


def test_unary_matches_legacy_for_every_operator_and_operand():
    text = in_main("let n = 1")
    for operator in UNARY_OPERATORS:
        for found in ALL_OPERANDS:
            new_result, old_result, new_diags, old_diags = unary_case(text, operator, found)
            assert new_result == old_result, (operator, found)
            assert new_diags == old_diags, (operator, found)


def test_unary_exact_results():
    text = in_main("let n = 1")
    cases = (
        ("-", INT, INT),
        ("-", FLOAT, FLOAT),
        ("-", BOOL, None),
        ("-", TEXT, None),
        ("-", VOID, None),
        ("not", BOOL, BOOL),
        ("not", INT, None),
        ("not", FLOAT, None),
        ("not", TEXT, None),
        ("not", VOID, None),
    )
    for operator, found, expected in cases:
        new_result, old_result, new_diags, old_diags = unary_case(text, operator, found)
        assert new_result == old_result == expected, (operator, found)
        assert new_diags == old_diags, (operator, found)


def test_unary_returns_none_for_names_outside_the_model():
    text = in_main("let n = 1")
    for operator in UNARY_OPERATORS:
        for found in OUTSIDE:
            new_result, old_result, new_diags, old_diags = unary_case(text, operator, found)
            assert new_result == old_result is None
            assert new_diags == old_diags
            assert [diagnostic.code for diagnostic in new_diags] == ["E2011"]


# B. Exact diagnostics


def test_minus_on_a_bool_has_a_complete_diagnostic():
    new_result, old_result, new_diags, old_diags = unary_case(in_main("let n = 1"), "-", BOOL)
    assert new_result == old_result is None
    assert new_diags == old_diags
    (error,) = new_diags
    assert error.code == "E2011"
    assert error.label == "Cannot apply '-' to Bool"
    assert error.hint == "'-' negates an Int or a Float."
    assert error.span == SPAN
    assert error.notes == ()


def test_not_on_a_number_has_the_extended_hint():
    for found in (INT, FLOAT):
        _, _, new_diags, old_diags = unary_case(in_main("let n = 1"), "not", found)
        assert new_diags == old_diags
        (error,) = new_diags
        assert error.code == "E2011"
        assert error.label == f"Cannot apply 'not' to {found}"
        assert error.hint == (
            "'not' negates a Bool. To negate a comparison, put it in parentheses: not (a == b)"
        )
        assert error.span == SPAN


def test_not_outside_bool_has_the_base_hint():
    for found in (TEXT, VOID, "Missing", ANY_VALUE, "Range[Int]"):
        _, _, new_diags, old_diags = unary_case(in_main("let n = 1"), "not", found)
        assert new_diags == old_diags
        (error,) = new_diags
        assert error.label == f"Cannot apply 'not' to {found}"
        assert error.hint == "'not' negates a Bool."


# C. Refined types and their roots


def test_unary_keeps_the_root_of_a_refined_operand():
    text = with_main(f"{PERCENT}\n{SMALL}\n{ACCEPTED}", "let n = 1")
    checker, _, diagnostics = shadow(text)
    assert diagnostics == []
    assert checker._root("Percent") == checker._root("Small") == "Int"
    assert checker._root("Accepted") == "Bool"

    new_result, old_result, new_diags, old_diags = unary_case(text, "-", "Percent")
    assert new_result == old_result == "Int"
    assert new_diags == old_diags == []

    new_result, old_result, new_diags, old_diags = unary_case(text, "-", "Small")
    assert new_result == old_result == "Int"
    assert new_diags == old_diags == []

    new_result, old_result, new_diags, old_diags = unary_case(text, "not", "Accepted")
    assert new_result == old_result == "Bool"
    assert new_diags == old_diags == []


def test_refined_operands_in_real_programs(monkeypatch):
    text = with_main(
        f"{PERCENT}\n{ACCEPTED}",
        "let p: Percent = 40\nlet ok: Accepted = true\nlet a = -p\nlet b = not ok\nprint(a)\nprint(b)\n",
    )
    new_checked, diagnostics, old_checked, _ = check_pair(monkeypatch, text)
    assert diagnostics == []
    new_symbols = {symbol.name: symbol.type for symbol in new_checked.symbols}
    old_symbols = {symbol.name: symbol.type for symbol in old_checked.symbols}
    assert new_symbols["a"] == old_symbols["a"] == "Int"
    assert new_symbols["b"] == old_symbols["b"] == "Bool"


def test_unary_rejects_a_dropped_refinement():
    text = with_main(DROPPED, "let n = 1")
    checker, _, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert checker._root("Parent") == "Parent"
    for operator in UNARY_OPERATORS:
        new_result, old_result, new_diags, old_diags = unary_case(text, operator, "Parent")
        assert new_result == old_result is None
        assert new_diags == old_diags
        assert [diagnostic.code for diagnostic in new_diags] == ["E2011"]
    # The historical snapshot still names Parent; the decision must not consult it.
    historical = {type_model.display(kind) for kind in checker._type_adapter.resolved_types.values()}
    assert "Parent" in historical


# D. None and real language contexts


def test_unary_returns_none_for_an_unresolved_operand():
    for operator in UNARY_OPERATORS:
        new_checker, _, new_diagnostics = shadow(in_main("let n = 1"))
        old_checker, _, old_diagnostics = shadow(in_main("let n = 1"))
        assert new_diagnostics == old_diagnostics
        new_checker._expression = lambda operand, scope: None
        old_checker._expression = lambda operand, scope: None
        new_start, old_start = len(new_checker._diagnostics), len(old_checker._diagnostics)
        assert new_checker._unary(unary_node(operator), _Scope()) is None
        assert legacy_unary(old_checker, unary_node(operator), _Scope()) is None
        assert new_checker._diagnostics[new_start:] == old_checker._diagnostics[old_start:] == []


def test_valid_unary_programs_are_differentially_equivalent(monkeypatch):
    text = in_main(
        "let a = -1\n"
        "let b = -1.5\n"
        "let c = not true\n"
        "let d = - -1\n"
        "let e = not not true\n"
        "let f = -1 + 2\n"
        'let g = not true and false\n'
        "print(a)\nprint(b)\nprint(c)\nprint(d)\nprint(e)\nprint(f)\nprint(g)\n"
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert diagnostics == []


def test_invalid_unary_programs_report_e2011(monkeypatch):
    text = in_main(
        "let a = -true\n"
        'let b = -"x"\n'
        "let c = not 1\n"
        'let d = not "x"\n'
        "let e = -print(1)\n"
        "print(a)\nprint(b)\nprint(c)\nprint(d)\nprint(e)\n"
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"] * 5


def test_nested_unary_and_prior_errors_preserve_order(monkeypatch):
    text = in_main(
        "let a = - -1\n"
        "let b = not not true\n"
        "let c = -true\n"
        "let d = not 1\n"
        "let e = - missing\n"
    )
    new_checked, diagnostics, old_checked, old_diagnostics = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011", "E2005"]
    assert diagnostics == old_diagnostics
    new_symbols = {symbol.name: symbol.type for symbol in new_checked.symbols}
    assert (new_symbols["a"], new_symbols["b"]) == ("Int", "Bool")


# E. The model bridge


def test_unary_current_type_model_does_not_hide_a_missing_primitive_model(monkeypatch):
    # `_root` is pinned to isolate `_unary`'s own `_current_type_model` path.
    checker = Checker()
    monkeypatch.setattr(checker, "_root", lambda kind: INT)
    monkeypatch.setattr(checker._type_adapter, "resolve", lambda name: None)
    checker._expression = lambda operand, scope: INT
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._unary(unary_node("-"), _Scope())


def test_unary_does_not_hide_a_missing_refined_model(monkeypatch):
    checker, _, diagnostics = shadow(with_main(PERCENT, "let n = 1"))
    assert diagnostics == []
    monkeypatch.setattr(checker, "_root", lambda kind: "Percent")
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    checker._expression = lambda operand, scope: "Percent"
    with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
        checker._unary(unary_node("-"), _Scope())


def test_unary_does_not_hide_a_missing_model_through_root(monkeypatch):
    checker, _, diagnostics = shadow(in_main("let n = 1"))
    assert diagnostics == []
    monkeypatch.setattr(checker._type_adapter, "resolve", lambda name: None)
    checker._expression = lambda operand, scope: INT
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._unary(unary_node("-"), _Scope())


def test_no_new_operator_operation_in_the_model_or_adapter():
    for name in ("unary_result", "unary_type", "negate", "logical_not", "binary_result"):
        assert not hasattr(type_model, name)
        assert not hasattr(TypeAdapter(), name)


def test_the_legacy_reference_reproduces_the_pre_b6_behaviour():
    checker, _, _ = shadow(in_main("let n = 1"))
    checker._expression = lambda operand, scope: INT
    assert legacy_unary(checker, unary_node("-"), _Scope()) == INT
    checker._diagnostics.clear()
    checker._expression = lambda operand, scope: BOOL
    assert legacy_unary(checker, unary_node("not"), _Scope()) == BOOL
    checker._diagnostics.clear()
    checker._expression = lambda operand, scope: TEXT
    assert legacy_unary(checker, unary_node("-"), _Scope()) is None
    assert [diagnostic.code for diagnostic in checker._diagnostics] == ["E2011"]


# F. Differential over the examples


def test_unary_is_differentially_equivalent_on_examples(monkeypatch):
    """The model-backed `_unary` must produce the same analysis, and the same documents."""
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
            patch.setattr(Checker, "_unary", legacy_unary)
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


# G. Public contracts


def test_public_type_surface_is_unchanged():
    text = with_main(
        f"{PERCENT}\n{ACCEPTED}",
        "let p: Percent = 40\nlet ok: Accepted = true\n"
        "let a = -p\nlet b = not ok\nlet c = -1\nlet d = not true\n"
        "print(a)\nprint(b)\nprint(c)\nprint(d)\n",
    )
    analysis = analyze(Source("test.nex", text))
    assert analysis.diagnostics == ()
    assert analysis.checked is not None

    symbols = {symbol.name: symbol for symbol in analysis.checked.symbols}
    assert (symbols["a"].type, symbols["b"].type, symbols["c"].type, symbols["d"].type) == (
        "Int",
        "Bool",
        "Int",
        "Bool",
    )

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
    assert builtins["print"]["signature"] == "fn print(value: Int | Float | Bool | Text)"

    types = {entry["name"]: entry for entry in documents["context"]["types"]}
    assert (types["Percent"]["root"], types["Accepted"]["root"]) == ("Int", "Bool")

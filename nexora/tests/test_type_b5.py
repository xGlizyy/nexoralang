"""D01/B5: the binary-operator result is decided with the type model, keeping observable semantics.

Before B5 `_infer` called the module function `binary_result(operator, left, right)`, which compared
the already-rooted operand strings. Now `Checker._binary_result` decides a representable operand with
`equal`/`is_value_type` on the D01 model and keeps the legacy string result for a name outside the
model (`ANY_VALUE`, unknown names, unenabled generics, dropped refinements). The legacy module
function is kept unchanged and used here as the differential reference.

Both operands arrive rooted from `_infer`, so a representable operand is always a primitive. The
decision is identity, never `assignable`: no implicit promotion is introduced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexora import tooling
from nexora import types as type_model
from nexora.checker import ANY_VALUE, Checker, binary_result
from nexora.diagnostics import Source
from nexora.pipeline import analyze
from nexora.type_adapter import TypeAdapter
from nexora.values import BOOL, FLOAT, INT, TEXT, VOID

from helpers import diagnostics_of, in_main, parse_text, with_main

PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "percent"'
SMALL = 'type Small = Percent where value < 10, "small"'
ACCEPTED = "type Accepted = Bool where value"
DROPPED = "type Child = Parent where value > 0\ntype Parent = Int where value + 1"
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples"

ALL_OPERATORS = ("+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or")
PRIMITIVES = (INT, FLOAT, BOOL, TEXT, VOID)
OUTSIDE = ("Missing", ANY_VALUE, "Range[Int]")
ALL_OPERANDS = (*PRIMITIVES, *OUTSIDE)

MODEL_ONLY_NAMES = ("binary_result", "operator_result", "operator_type", "binary_type")


def shadow(text: str, *, require_main: bool = True) -> tuple[Checker, object, list]:
    """Check a source and return the checker, the checked program and its diagnostics."""
    program, _ = parse_text(text)
    checker = Checker()
    checker.require_main = require_main
    checked, diagnostics = checker.check(program)
    return checker, checked, diagnostics


def legacy_binary_result(self: Checker, operator: str, left: str, right: str) -> str | None:
    """The reference `_binary_result` from before B5: the pre-D01 module function.

    `_infer` rooted both operands before calling, so this wrapper receives exactly what the
    module function used to receive.
    """
    return binary_result(operator, left, right)


def direct_pair(text: str, operator: str, left: str, right: str) -> tuple[str | None, str | None]:
    """Run the new `_binary_result` and the legacy module function on independent checkers."""
    new_checker, _, new_diagnostics = shadow(text)
    old_checker, _, old_diagnostics = shadow(text)
    assert new_diagnostics == old_diagnostics
    return new_checker._binary_result(operator, left, right), binary_result(operator, left, right)


def check_pair(monkeypatch, text: str, *, require_main: bool = True):
    """Check `text` with the new and the legacy `_binary_result`, on independent checkers."""
    program, _ = parse_text(text)
    new_checker = Checker()
    new_checker.require_main = require_main
    new_checked, new_diagnostics = new_checker.check(program)

    with monkeypatch.context() as patch:
        patch.setattr(Checker, "_binary_result", legacy_binary_result)
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


# A. Full operator table


def test_binary_result_matches_legacy_for_every_operator_and_operand():
    # The decision is pure, so one checker suffices for the whole cross product.
    new_checker = Checker()
    for operator in ALL_OPERATORS:
        for left in ALL_OPERANDS:
            for right in ALL_OPERANDS:
                new = new_checker._binary_result(operator, left, right)
                old = binary_result(operator, left, right)
                assert new == old, (operator, left, right)


def test_binary_result_exact_table_for_representable_operands():
    cases = (
        # Arithmetic: the same type in, the same type out.
        ("+", INT, INT, INT),
        ("-", FLOAT, FLOAT, FLOAT),
        ("*", INT, INT, INT),
        ("/", INT, INT, INT),
        ("+", TEXT, TEXT, TEXT),
        # Equality and ordering: always Bool for the supported types.
        ("==", INT, INT, BOOL),
        ("!=", TEXT, TEXT, BOOL),
        ("==", BOOL, BOOL, BOOL),
        ("<", INT, INT, BOOL),
        ("<=", FLOAT, FLOAT, BOOL),
        (">", TEXT, TEXT, BOOL),
        (">=", INT, INT, BOOL),
        # Logical operators: Bool in, Bool out.
        ("and", BOOL, BOOL, BOOL),
        ("or", BOOL, BOOL, BOOL),
        # Invalid combinations, exactly as before.
        ("+", INT, FLOAT, None),
        ("+", TEXT, INT, None),
        ("-", TEXT, TEXT, None),
        ("*", BOOL, BOOL, None),
        ("/", TEXT, TEXT, None),
        ("<", BOOL, BOOL, None),
        ("<", INT, BOOL, None),
        ("and", INT, INT, None),
        ("or", BOOL, INT, None),
        ("==", INT, FLOAT, None),
        ("==", VOID, VOID, None),
        ("+", VOID, INT, None),
        ("<", VOID, VOID, None),
    )
    new_checker = Checker()
    for operator, left, right, expected in cases:
        assert new_checker._binary_result(operator, left, right) == expected, (operator, left, right)
        assert binary_result(operator, left, right) == expected, (operator, left, right)


def test_binary_result_returns_none_for_names_outside_the_model():
    new_checker = Checker()
    for operator in ALL_OPERATORS:
        for name in OUTSIDE:
            assert new_checker._binary_result(operator, name, name) is None
            assert new_checker._binary_result(operator, name, INT) is None
            assert new_checker._binary_result(operator, INT, name) is None
            assert binary_result(operator, name, name) is None


# B. Refined types and their roots


def test_binary_result_keeps_the_root_of_a_refined_operand():
    text = with_main(f"{PERCENT}\n{SMALL}\n{ACCEPTED}", "let n = 1")
    checker, _, diagnostics = shadow(text)
    assert diagnostics == []
    # The previous rooting of `_infer` is what `_binary_result` relies on.
    assert checker._root("Percent") == checker._root("Small") == "Int"
    assert checker._root("Accepted") == "Bool"

    int_root = checker._root("Percent")
    other_int_root = checker._root("Small")
    bool_root = checker._root("Accepted")
    for operator, expected in (("+", INT), ("-", INT), ("<", BOOL), ("==", BOOL), ("!=", BOOL)):
        new, old = direct_pair(text, operator, int_root, other_int_root)
        assert new == old == expected, operator
    assert checker._binary_result("and", bool_root, bool_root) == BOOL
    assert binary_result("and", bool_root, bool_root) == BOOL


def test_refined_arithmetic_language_result_is_the_root(monkeypatch):
    text = with_main(
        f"{PERCENT}\n{SMALL}",
        'let p: Percent = 40\nlet s: Small = 5\nlet total = p + s\nlet ok = p < s\n'
        "print(total)\nprint(ok)\n",
    )
    new_checked, diagnostics, old_checked, _ = check_pair(monkeypatch, text)
    assert diagnostics == []
    new_symbols = {symbol.name: symbol.type for symbol in new_checked.symbols}
    old_symbols = {symbol.name: symbol.type for symbol in old_checked.symbols}
    assert new_symbols["total"] == old_symbols["total"] == "Int"
    assert new_symbols["ok"] == old_symbols["ok"] == "Bool"


def test_refined_bool_is_a_logical_operand(monkeypatch):
    text = with_main(ACCEPTED, "let a: Accepted = true\nlet b = a and a\nlet c = a or a\nprint(b)\nprint(c)\n")
    new_checked, diagnostics, old_checked, _ = check_pair(monkeypatch, text)
    assert diagnostics == []
    new_symbols = {symbol.name: symbol.type for symbol in new_checked.symbols}
    assert new_symbols["b"] == new_symbols["c"] == "Bool"


def test_binary_result_does_not_revalidate_a_dropped_refinement():
    text = with_main(DROPPED, "let n = 1")
    checker, _, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert checker._root("Parent") == "Parent"
    for operator in ("+", "-", "==", "<", "and"):
        assert checker._binary_result(operator, "Parent", "Parent") is None
        assert binary_result(operator, "Parent", "Parent") is None
    # The historical snapshot still names Parent; the decision must not consult it.
    historical = {type_model.display(kind) for kind in checker._type_adapter.resolved_types.values()}
    assert "Parent" in historical


# C. Real language contexts


def test_valid_arithmetic_comparison_and_logic_is_differentially_equivalent(monkeypatch):
    text = in_main(
        "let a = 2 + 3 * 4\n"
        "let b = 10 - 5\n"
        "let c = 7 / 2\n"
        "let d = 1.5 * 2.0\n"
        'let e = "a" + "b"\n'
        "let f = a < b\n"
        'let g = "x" <= "y"\n'
        "let h = d == 3.0\n"
        "let i = true != false\n"
        "let j = true and false\n"
        "let k = true or false\n"
        "print(a)\nprint(b)\nprint(c)\nprint(d)\nprint(e)\n"
        "print(f)\nprint(g)\nprint(h)\nprint(i)\nprint(j)\nprint(k)\n"
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert diagnostics == []


def test_invalid_operator_combinations_report_e2011(monkeypatch):
    text = in_main(
        "let a = 1 + 1.5\n"
        'let b = "x" - "y"\n'
        "let c = true and 1\n"
        'let d = "x" < 1\n'
        "let e = 1 == 1.5\n"
        "let f = true or 1\n"
        "print(a)\nprint(b)\nprint(c)\nprint(d)\nprint(e)\nprint(f)\n"
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"] * 6


def test_diagnostic_order_is_preserved_on_a_mixed_program(monkeypatch):
    text = in_main(
        "let a = 1 + 1.5\n"
        'let b = (2 * 3) + "x"\n'
        "let c = true or 1\n"
        "let d = missing + 1\n"
    )
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011", "E2011", "E2005"]
    assert diagnostics == old_diagnostics


def test_a_void_operand_is_not_a_value(monkeypatch):
    text = in_main(
        "let a = print(1) + 1\n"
        "let b = 2 + print(1)\n"
        "let c = print(1) < print(1)\n"
    )
    _, diagnostics, _, _ = check_pair(monkeypatch, text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011", "E2011"]
    assert diagnostics[0].hint == "A call to a Void function does not produce a value."


def test_binary_result_is_not_called_for_unresolved_operands(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("_binary_result must not run when an operand is unresolved")

    monkeypatch.setattr(Checker, "_binary_result", fail)
    diagnostics = diagnostics_of(in_main("let a = missing + 1\nlet b = missing + missing\n"))
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2005", "E2005", "E2005"]


def test_binary_result_does_not_hide_a_missing_primitive_model(monkeypatch):
    checker = Checker()
    real_resolve = checker._type_adapter.resolve
    monkeypatch.setattr(
        checker._type_adapter,
        "resolve",
        lambda name, real=real_resolve: None if name == INT else real(name),
    )
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._binary_result("+", INT, INT)


def test_binary_result_does_not_hide_a_missing_refined_model(monkeypatch):
    checker, _, diagnostics = shadow(with_main(PERCENT, "let n = 1"))
    assert diagnostics == []
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
        checker._binary_result("+", "Percent", "Percent")


# D. Differential over the examples


def test_binary_result_is_differentially_equivalent_on_examples(monkeypatch):
    """The model-backed `_binary_result` must produce the same analysis, and the same documents."""
    builders = {
        "check": tooling.check_source,
        "inspect": tooling.inspect_source,
        "symbols": tooling.get_symbols,
        "context": tooling.get_context,
    }
    paths = sorted(EXAMPLE_DIR.rglob("*.nex"))
    assert len(paths) == 26
    skipped: list[Path] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        program, _ = parse_text(text)

        if program.records or "Option[" in text or "Result[" in text:
            # A record, an Option or a Result is a type the legacy rule does not know:
            # comparing the two would compare a rule that can express it with one that
            # cannot (decision 0014, decision 0016).
            skipped.append(path)
            continue

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)
        new_documents = {name: builder(text) for name, builder in builders.items()}

        with monkeypatch.context() as patch:
            patch.setattr(Checker, "_binary_result", legacy_binary_result)
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
    assert [path.name for path in skipped] == ["models.nex", "option_result.nex", "records.nex"]


# E. Public contracts and the model bridge


def test_public_type_surface_is_unchanged():
    text = with_main(
        f"{PERCENT}\n{SMALL}\n{ACCEPTED}",
        'let p: Percent = 40\nlet s: Small = 5\nlet ok: Accepted = true\n'
        'let total = p + s\nlet sum = 1 + 2\nlet joined = "a" + "b"\nlet flag = ok and true\n'
        "print(total)\nprint(sum)\nprint(joined)\nprint(flag)\n",
    )
    analysis = analyze(Source("test.nex", text))
    assert analysis.diagnostics == ()
    assert analysis.checked is not None

    symbols = {symbol.name: symbol for symbol in analysis.checked.symbols}
    assert (symbols["total"].type, symbols["sum"].type, symbols["joined"].type, symbols["flag"].type) == (
        "Int",
        "Int",
        "Text",
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
    assert (types["Percent"]["root"], types["Small"]["root"], types["Accepted"]["root"]) == (
        "Int",
        "Int",
        "Bool",
    )


def test_no_operator_operation_was_added_to_the_model_or_adapter():
    for name in MODEL_ONLY_NAMES:
        assert not hasattr(type_model, name)
    adapter = TypeAdapter()
    for name in MODEL_ONLY_NAMES:
        assert not hasattr(adapter, name)


def test_the_legacy_module_function_is_still_available_and_unchanged():
    # The differential reference must keep its exact pre-D01 behaviour.
    assert binary_result("+", INT, INT) == INT
    assert binary_result("+", TEXT, TEXT) == TEXT
    assert binary_result("and", BOOL, BOOL) == BOOL
    assert binary_result("<", TEXT, TEXT) == BOOL
    assert binary_result("and", INT, INT) is None
    assert binary_result("+", INT, FLOAT) is None
    assert binary_result("-", TEXT, TEXT) is None
    assert binary_result("<", VOID, VOID) is None

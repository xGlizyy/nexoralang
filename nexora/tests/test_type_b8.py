"""D01/B8: the root decision of `Percent(x)` uses the type model, keeping observable semantics.

Before B8 `Checker._refinement_check` rejected an argument when `_root(found) != refined.root`, a
string comparison of the rooted argument type with the root of the refined type. Now both roots are
resolved with `_current_type_model` and decided with `equal`. A name outside the model (`ANY_VALUE`,
unknown names, unenabled generics, dropped refinements) is not a matching root and keeps the same
`E2011`. The legacy decision is kept here as an independent reference (`legacy_refinement_check`)
that never uses the model to decide whether the roots match.

Only the root decision changes: the `found is None` early exit, the `Void` short-circuit, the arity
check, `E2018`, the message, hint, span and notes of `E2011`, and the `_check_constant` call (which
still happens only when the roots match) are untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexora import ast_nodes as ast
from nexora import tooling
from nexora import types as type_model
from nexora.checker import ANY_VALUE, Checker, _conversion_hint
from nexora.diagnostics import Source
from nexora.pipeline import analyze
from nexora.type_adapter import TypeAdapter
from nexora.values import BOOL, FLOAT, INT, TEXT, VOID

from helpers import in_main, parse_text, with_main

PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"'
SMALL = 'type Small = Percent where value < 10, "A small percentage"'
ACCEPTED = "type Accepted = Bool where value"
SHORT = 'type Short = Text where value != "", "A short text"'
RATIO = "type Ratio = Float where value > 0.0"
GRADE = "type Grade = Int where value >= 0"
DROPPED = "type Child = Parent where value > 0\ntype Parent = Int where value + 1"

REGISTRY = "\n".join((PERCENT, SMALL, ACCEPTED, SHORT, RATIO))
REGISTRY_WITH_DROPPED = f"{REGISTRY}\n{DROPPED}"
TARGETS = ("Percent", "Small", "Accepted", "Short", "Ratio")
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples"


def checker_with_types(text: str) -> Checker:
    """A checker whose refined-type registry comes from `text` (declarations only)."""
    program, _ = parse_text(text)
    checker = Checker()
    checker.require_main = False
    checker.check(program)
    return checker


def legacy_refinement_check(self: Checker, node: ast.Call, argument_types: list[str | None]) -> str | None:
    """The reference `_refinement_check` from before B8, with the old root-string decision.

    Its decision uses `_root` and a string comparison with `refined.root`; it never calls
    `_current_type_model` nor the model's `equal` to decide whether the roots match.
    """
    name = node.callee
    if self._refining is not None:
        self._report(
            "E2018",
            f"The condition of '{self._refining}' cannot check a value against '{name}'",
            node.callee_span,
            hint=f"To build on '{name}', refine it: type {self._refining} = {name} where ...",
        )
        return None
    refined = self._refined.get(name)
    count = len(node.arguments)
    if count != 1:
        self._report(
            "E2009",
            f"'{name}' takes 1 argument, but {count} {'was' if count == 1 else 'were'} given",
            node.span,
            notes=(f"{name}(x) checks that x satisfies the condition of {name}.",),
        )
        return name if refined is not None else None
    if refined is None:
        return None
    found, argument = argument_types[0], node.arguments[0]
    if found is None:
        return name
    if found == VOID:
        self._report("E2011", "This call does not produce a value to check", argument.span)
    elif self._root(found) != refined.root:
        self._report(
            "E2011",
            f"Expected {refined.root}, found {found}",
            argument.span,
            hint=_conversion_hint(self._root(found), refined.root),
            notes=(f"'{name}' refines {refined.base}, so it checks values of type {refined.root}.",),
        )
    else:
        self._check_constant(argument, name)
    return name


def check_pair(monkeypatch, text: str, *, require_main: bool = True):
    """Check `text` with the new and the legacy `_refinement_check`, on independent checkers."""
    program, _ = parse_text(text)
    new_checker = Checker()
    new_checker.require_main = require_main
    new_checked, new_diagnostics = new_checker.check(program)

    with monkeypatch.context() as patch:
        patch.setattr(Checker, "_refinement_check", legacy_refinement_check)
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


def call_node(target: str = "Percent", args: str = "m") -> ast.Call:
    """A parsed `let x = target(args)`, returning the call node."""
    program, _ = parse_text(in_main(f"let x = {target}({args})"))
    statement = program.functions[0].body.statements[0]
    assert isinstance(statement, ast.Let)
    assert isinstance(statement.value, ast.Call)
    return statement.value


def refinement_case(target: str, found: str | None, registry: str):
    """Run the new `_refinement_check` and the legacy reference over the same call and type.

    Returns `(new_result, old_result, new_diagnostics, old_diagnostics)`, each sliced from the
    checker's previous state so the declaration diagnostics of `registry` do not interfere.
    """
    node = call_node(target)
    new_checker = checker_with_types(registry)
    old_checker = checker_with_types(registry)
    new_start, old_start = len(new_checker._diagnostics), len(old_checker._diagnostics)
    new_result = new_checker._refinement_check(node, [found])
    old_result = legacy_refinement_check(old_checker, node, [found])
    return new_result, old_result, new_checker._diagnostics[new_start:], old_checker._diagnostics[old_start:]


# A. The decision table


def test_the_root_decision_matches_legacy_for_every_type():
    founds = (
        INT,
        FLOAT,
        BOOL,
        TEXT,
        VOID,
        "Percent",
        "Small",
        "Accepted",
        "Short",
        "Ratio",
        ANY_VALUE,
        "Range[Int]",
        "Missing",
        "Parent",
        None,
    )
    for target in TARGETS:
        for found in founds:
            registry = REGISTRY_WITH_DROPPED if found == "Parent" else REGISTRY
            new_result, old_result, new_diagnostics, old_diagnostics = refinement_case(target, found, registry)
            assert new_result == old_result, (target, found)
            assert new_diagnostics == old_diagnostics, (target, found)


def test_only_a_matching_root_is_accepted():
    matching = (
        (INT, "Percent"),
        (INT, "Small"),
        ("Percent", "Percent"),
        ("Small", "Small"),
        (FLOAT, "Ratio"),
        ("Ratio", "Ratio"),
        (BOOL, "Accepted"),
        ("Accepted", "Accepted"),
        (TEXT, "Short"),
        ("Short", "Short"),
    )
    for found, target in matching:
        assert refinement_case(target, found, REGISTRY) == (target, target, [], []), (target, found)

    mismatched = (
        (FLOAT, "Percent"),
        (BOOL, "Percent"),
        (TEXT, "Percent"),
        ("Accepted", "Percent"),
        (INT, "Ratio"),
        (INT, "Accepted"),
        ("Short", "Percent"),
        (ANY_VALUE, "Percent"),
        ("Range[Int]", "Percent"),
        ("Missing", "Percent"),
    )
    for found, target in mismatched:
        new_result, old_result, new_diagnostics, old_diagnostics = refinement_case(target, found, REGISTRY)
        assert new_result == old_result == target, (target, found)
        assert new_diagnostics == old_diagnostics, (target, found)
        assert [diagnostic.code for diagnostic in new_diagnostics] == ["E2011"], (target, found)


def test_the_void_argument_keeps_its_own_rejection():
    for target in TARGETS:
        new_result, old_result, new_diagnostics, old_diagnostics = refinement_case(target, VOID, REGISTRY)
        assert new_result == old_result == target
        assert new_diagnostics == old_diagnostics
        (error,) = new_diagnostics
        assert error.code == "E2011"
        assert error.label == "This call does not produce a value to check"
        assert error.hint is None
        assert error.notes == ()


def test_an_unresolved_argument_adds_no_diagnostic_at_the_unit_level():
    for target in TARGETS:
        assert refinement_case(target, None, REGISTRY) == (target, target, [], [])


# B. Exact diagnostics


def test_a_primitive_mismatch_keeps_its_complete_diagnostic(monkeypatch):
    text = with_main(PERCENT, 'print(Percent(1.5))\nprint(Percent("ten"))\nprint(Percent(true))')
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011", "E2011", "E2011"]
    assert [diagnostic.label for diagnostic in diagnostics] == [
        "Expected Int, found Float",
        "Expected Int, found Text",
        "Expected Int, found Bool",
    ]
    assert diagnostics[0].hint == "Convert the Float explicitly with to_int(...), which drops the fractional part."
    assert diagnostics[1].hint is None
    assert diagnostics[2].hint is None
    for error in diagnostics:
        assert error.notes == ("'Percent' refines Int, so it checks values of type Int.",)
    assert [error.span.line for error in diagnostics] == [4, 5, 6]


def test_the_conversion_hints_of_the_other_roots_are_preserved(monkeypatch):
    text = with_main(f"{SHORT}\n{RATIO}", "print(Short(1))\nprint(Ratio(1))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.label for diagnostic in diagnostics] == [
        "Expected Text, found Int",
        "Expected Float, found Int",
    ]
    assert diagnostics[0].hint == "Convert the value explicitly with to_text(...)."
    assert diagnostics[1].hint == "Convert the Int explicitly with to_float(...)."
    assert diagnostics[0].notes == ("'Short' refines Text, so it checks values of type Text.",)
    assert diagnostics[1].notes == ("'Ratio' refines Float, so it checks values of type Float.",)


def test_the_message_uses_the_found_refined_name_not_its_root(monkeypatch):
    text = with_main(f"{PERCENT}\n{ACCEPTED}", "let ok: Accepted = true\nprint(Percent(ok))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    (error,) = diagnostics
    assert error.label == "Expected Int, found Accepted"
    assert "Bool" not in error.label
    assert error.notes == ("'Percent' refines Int, so it checks values of type Int.",)


def test_a_chained_refinement_names_its_base_in_the_note(monkeypatch):
    text = with_main(f"{PERCENT}\n{SMALL}\n{ACCEPTED}", "let ok: Accepted = true\nprint(Small(ok))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    (error,) = diagnostics
    assert error.label == "Expected Int, found Accepted"
    assert error.notes == ("'Small' refines Percent, so it checks values of type Int.",)


def test_a_void_argument_in_a_real_program_keeps_its_diagnostic(monkeypatch):
    text = with_main(PERCENT, "print(Percent(print(1)))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    (error,) = diagnostics
    assert error.code == "E2011"
    assert error.label == "This call does not produce a value to check"
    assert error.hint is None
    assert error.notes == ()
    assert (error.span.line, error.span.column, error.span.end_column) == (4, 19, 27)


# C. Valid constructions


def test_refined_arguments_with_the_same_root_are_accepted(monkeypatch):
    text = with_main(
        f"{PERCENT}\n{SMALL}\n{GRADE}",
        "let p: Percent = 40\nlet g: Grade = 50\nprint(Percent(p))\nprint(Percent(g))\nprint(Small(5))\n",
    )
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics == []


def test_the_other_roots_accept_their_own_values(monkeypatch):
    text = with_main(
        f"{ACCEPTED}\n{SHORT}\n{RATIO}",
        'print(Accepted(true))\nprint(Short("x"))\nprint(Ratio(1.5))',
    )
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics == []


def test_a_computed_argument_is_not_checked_statically(monkeypatch):
    text = with_main(PERCENT, "let n = 99\nprint(Percent(n + 2))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics == []


# D. Arity and E2018


def test_arity_diagnostics_keep_their_labels_notes_and_spans(monkeypatch):
    text = with_main(PERCENT, "print(Percent())\nprint(Percent(1, 2))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2009", "E2009"]
    assert [diagnostic.label for diagnostic in diagnostics] == [
        "'Percent' takes 1 argument, but 0 were given",
        "'Percent' takes 1 argument, but 2 were given",
    ]
    for error in diagnostics:
        assert error.hint is None
        assert error.notes == ("Percent(x) checks that x satisfies the condition of Percent.",)
    assert (diagnostics[0].span.line, diagnostics[0].span.column, diagnostics[0].span.end_column) == (4, 11, 20)
    assert (diagnostics[1].span.line, diagnostics[1].span.column, diagnostics[1].span.end_column) == (5, 11, 24)


def test_building_a_refinement_inside_a_condition_is_still_prohibited(monkeypatch):
    text = with_main(f"{PERCENT}\ntype Half = Int where Percent(value) == value", "print(1)")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    (error,) = diagnostics
    assert error.code == "E2018"
    assert error.label == "The condition of 'Half' cannot check a value against 'Percent'"
    assert error.hint == "To build on 'Percent', refine it: type Half = Percent where ..."

    program, _ = parse_text(text)
    half = next(declaration for declaration in program.types if declaration.name == "Half")
    condition = half.condition
    assert isinstance(condition, ast.Binary)
    assert isinstance(condition.left, ast.Call)
    assert error.span == condition.left.callee_span


# E. Prior errors and ordering


def test_an_unresolved_argument_does_not_produce_a_root_error(monkeypatch):
    text = with_main(PERCENT, "print(Percent(missing))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2005"]


def test_prior_argument_errors_keep_their_order(monkeypatch):
    text = with_main(PERCENT, "print(Percent(missing))\nprint(Percent(1.5, missing))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2005", "E2005", "E2009"]
    assert all("Expected Int" not in diagnostic.label for diagnostic in diagnostics)


# F. Constant validation


def test_a_valid_constant_is_still_accepted(monkeypatch):
    text = with_main(PERCENT, "print(Percent(40))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics == []


def test_an_invalid_constant_still_reports_e2017(monkeypatch):
    text = with_main(PERCENT, "print(Percent(300))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    (error,) = diagnostics
    assert error.code == "E2017"
    assert error.label == "300 is not a valid Percent"
    assert error.hint is None
    assert error.notes == (
        "The condition of 'Percent' is false: where value >= 0 and value <= 100",
        "The value: 300",
        "Reason: A percentage goes from 0 to 100",
    )
    assert (error.span.line, error.span.column, error.span.end_column) == (4, 19, 22)


def test_a_root_mismatch_does_not_also_report_e2017(monkeypatch):
    text = with_main(PERCENT, "print(Percent(1.5))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]


def test_the_constant_budget_still_reports_e2019(monkeypatch):
    monkeypatch.setattr("nexora.checker.MAX_REFINEMENT_STEPS", 0)
    text = with_main(PERCENT, "print(Percent(40))")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    (error,) = diagnostics
    assert error.code == "E2019"
    assert error.label == "Checking constants against refined types needs more than 0 steps"
    assert "E2011" not in [diagnostic.code for diagnostic in diagnostics]


# G. Dropped refinements


def test_a_dropped_target_does_not_add_a_diagnostic(monkeypatch):
    text = with_main(f"{DROPPED}\n{PERCENT}", "print(Parent(1))\nprint(1)")
    _, diagnostics, _, old_diagnostics = check_pair(monkeypatch, text)
    assert diagnostics == old_diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    (error,) = diagnostics
    assert error.label == "The condition of 'where' in 'Parent' must be Bool, found Int"
    assert error.span.line == 2


def test_a_dropped_target_is_ignored_at_the_unit_level():
    new_result, old_result, new_diagnostics, old_diagnostics = refinement_case(
        "Parent", INT, f"{DROPPED}\n{PERCENT}"
    )
    assert new_result == old_result is None
    assert new_diagnostics == old_diagnostics == []


def test_a_historical_refinement_is_not_accepted_again():
    registry = f"{DROPPED}\n{PERCENT}"
    checker = checker_with_types(registry)
    assert "Parent" not in checker._refined
    historical = {type_model.display(kind) for kind in checker._type_adapter.resolved_types.values()}
    assert "Parent" in historical

    new_result, old_result, new_diagnostics, old_diagnostics = refinement_case("Percent", "Parent", registry)
    assert new_result == old_result == "Percent"
    assert new_diagnostics == old_diagnostics
    (error,) = new_diagnostics
    assert error.code == "E2011"
    assert error.label == "Expected Int, found Parent"


# H. The model bridge


def test_a_missing_found_root_model_raises(monkeypatch):
    checker = checker_with_types(PERCENT)
    real = checker._type_adapter.resolve
    monkeypatch.setattr(
        checker._type_adapter, "resolve", lambda name, real=real: None if name == INT else real(name)
    )
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._refinement_check(call_node("Percent"), [INT])


def test_a_missing_expected_root_model_raises(monkeypatch):
    checker = checker_with_types(SHORT)
    real = checker._type_adapter.resolve
    monkeypatch.setattr(
        checker._type_adapter, "resolve", lambda name, real=real: None if name == TEXT else real(name)
    )
    with pytest.raises(RuntimeError, match="primitive type 'Text' is missing"):
        checker._refinement_check(call_node("Short"), [INT])


def test_the_found_bridge_does_not_hide_a_missing_primitive(monkeypatch):
    # `_root` is pinned so the failure comes from `_refinement_check`'s own model lookup, and the
    # expected root is a different primitive that is still available.
    checker = checker_with_types(SHORT)
    real = checker._type_adapter.resolve
    monkeypatch.setattr(checker, "_root", lambda kind: INT)
    monkeypatch.setattr(
        checker._type_adapter, "resolve", lambda name, real=real: None if name == INT else real(name)
    )
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._refinement_check(call_node("Short"), [INT])


def test_a_missing_expected_root_raises_even_when_the_found_root_is_outside_the_model(monkeypatch):
    # A short-circuit that skipped `refined.root` when the found root is outside the model would
    # hide this failure; the expected root must be resolved before deciding.
    checker = checker_with_types(SHORT)
    real = checker._type_adapter.resolve
    monkeypatch.setattr(
        checker._type_adapter, "resolve", lambda name, real=real: None if name == TEXT else real(name)
    )
    with pytest.raises(RuntimeError, match="primitive type 'Text' is missing"):
        checker._refinement_check(call_node("Short"), ["Missing"])


def test_the_void_branch_does_not_consult_the_model(monkeypatch):
    checker = checker_with_types(PERCENT)

    def explode(kind):
        raise AssertionError("_root must not be called for a Void argument")

    monkeypatch.setattr(checker, "_root", explode)
    assert checker._refinement_check(call_node("Percent"), [VOID]) == "Percent"
    (error,) = checker._diagnostics
    assert error.label == "This call does not produce a value to check"


def test_an_unresolved_argument_does_not_consult_the_model(monkeypatch):
    checker = checker_with_types(PERCENT)

    def explode(kind):
        raise AssertionError("_root must not be called for an unresolved argument")

    monkeypatch.setattr(checker, "_root", explode)
    assert checker._refinement_check(call_node("Percent"), [None]) == "Percent"
    assert checker._diagnostics == []


def test_no_root_operation_was_added_to_the_model_or_adapter():
    for name in ("root_decision", "refinement_root", "matches_root", "same_root", "root_assignable"):
        assert not hasattr(type_model, name)
        assert not hasattr(TypeAdapter(), name)


def test_the_legacy_reference_reproduces_the_pre_b8_behaviour():
    node = call_node("Percent")

    accepted = checker_with_types(PERCENT)
    assert legacy_refinement_check(accepted, node, [INT]) == "Percent"
    assert accepted._diagnostics == []

    rejected = checker_with_types(PERCENT)
    assert legacy_refinement_check(rejected, node, [FLOAT]) == "Percent"
    (error,) = rejected._diagnostics
    assert error.code == "E2011"
    assert error.label == "Expected Int, found Float"

    void = checker_with_types(PERCENT)
    assert legacy_refinement_check(void, node, [VOID]) == "Percent"
    (error,) = void._diagnostics
    assert error.label == "This call does not produce a value to check"


# I. Differential over the examples


def test_the_root_decision_is_differentially_equivalent_on_examples(monkeypatch):
    """The model-backed root decision must produce the same analysis and the same documents."""
    builders = {
        "check": tooling.check_source,
        "inspect": tooling.inspect_source,
        "symbols": tooling.get_symbols,
        "context": tooling.get_context,
    }
    paths = sorted(EXAMPLE_DIR.rglob("*.nex"))
    assert len(paths) == 21
    for path in paths:
        text = path.read_text(encoding="utf-8")
        program, _ = parse_text(text)

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)
        new_documents = {name: builder(text) for name, builder in builders.items()}

        with monkeypatch.context() as patch:
            patch.setattr(Checker, "_refinement_check", legacy_refinement_check)
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


# J. Public contracts


def test_public_type_surface_is_unchanged():
    text = with_main(PERCENT, "let p: Percent = 40\nprint(Percent(p))")
    analysis = analyze(Source("test.nex", text))
    assert analysis.diagnostics == ()
    assert analysis.checked is not None

    assert analysis.types == analysis.checked.types
    assert all(isinstance(kind, str) for kind in analysis.checked.types.values())

    symbols = {symbol.name: symbol for symbol in analysis.checked.symbols}
    assert symbols["p"].type == "Percent"
    assert isinstance(symbols["p"].type, str)

    documents = {
        "check": tooling.check_source(text),
        "inspect": tooling.inspect_source(text),
        "symbols": tooling.get_symbols(text),
        "context": tooling.get_context(text),
    }
    for document in documents.values():
        json.dumps(document)

    types = {entry["name"]: entry for entry in documents["context"]["types"]}
    assert types["Percent"]["root"] == "Int"

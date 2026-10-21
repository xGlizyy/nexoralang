"""D01: the type adapter and the model-backed `_root` and `_accepts`, without changing type rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexora import ast_nodes as ast
from nexora import tooling
from nexora import types as type_model
from nexora.checker import ANY_VALUE, KNOWN_TYPES, Checker, _conversion_hint
from nexora.diagnostics import Span
from nexora.type_adapter import PRIMITIVE_TYPES, TypeAdapter
from nexora.values import VALUE_TYPES, VOID

from helpers import diagnostics_of, in_main, parse_text, with_main

PERCENT = 'type Percent = Int where value >= 0 and value <= 100, "percent"'
SMALL = 'type Small = Percent where value < 10, "small"'
GRADE = "type Grade = Int where value >= 0 and value <= 10"
SPAN = Span(1, 1, 1, 3)
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples"


def shadow(text: str) -> tuple[Checker, object, list]:
    """Check a source and return the checker, the checked program and its diagnostics."""
    program, _ = parse_text(text)
    checker = Checker()
    checked, diagnostics = checker.check(program)
    return checker, checked, diagnostics


def legacy_root(checker: Checker, kind: str) -> str:
    """The reference `_root` from before B1: refined root or the same name."""
    refined = checker._refined.get(kind)
    return refined.root if refined is not None else kind


def legacy_accepts(checker: Checker, expected: str, found: str) -> bool:
    """The reference `_accepts` from before B2: a name chain in the current registry."""
    kind: str | None = found
    while kind is not None:
        if kind == expected:
            return True
        refined = checker._refined.get(kind)
        kind = refined.base if refined is not None else None
    return False


def legacy_expect_type(
    checker: Checker, expected: str, found: str, node: ast.Expr, notes: tuple[str, ...]
) -> None:
    """The reference `_expect_type` from before B3, with the old string decision."""
    if checker._accepts(expected, found):
        return
    if expected in checker._refined and checker._root(found) == checker._root(expected):
        if checker._constant(node) is not None and found not in checker._refined:
            checker._check_constant(node, expected)
            return
        checker._report(
            "E2011",
            f"Expected {expected}, found {found}",
            node.span,
            hint=f"Check the value explicitly with {expected}(...). "
                 f"The program stops there if the value does not satisfy the condition of {expected}.",
            notes=notes,
        )
        return
    checker._report(
        "E2011",
        f"Expected {expected}, found {found}",
        node.span,
        hint=_conversion_hint(checker._root(found), checker._root(expected)),
        notes=notes,
    )


def expect_pair(
    text: str, expected: str, found: str, node: ast.Expr, notes: tuple[str, ...] = ()
) -> tuple[list, list]:
    """Run the current and legacy `_expect_type` on independent checkers over the same source."""
    new_checker, _, new_diagnostics = shadow(text)
    old_checker, _, old_diagnostics = shadow(text)
    assert new_diagnostics == old_diagnostics
    new_start = len(new_checker._diagnostics)
    old_start = len(old_checker._diagnostics)
    new_checker._expect_type(expected, found, node, notes)
    legacy_expect_type(old_checker, expected, found, node, notes)
    return new_checker._diagnostics[new_start:], old_checker._diagnostics[old_start:]


# The five public primitives


def test_every_public_primitive_has_a_model_object():
    adapter = TypeAdapter()
    assert set(PRIMITIVE_TYPES) == set(KNOWN_TYPES)
    assert set(adapter.primitive_names) == set(KNOWN_TYPES)
    for name in KNOWN_TYPES:
        kind = adapter.resolve(name)
        assert isinstance(kind, type_model.Primitive)
        assert type_model.display(kind) == name
        assert adapter.try_resolve(name) is kind


def test_void_is_a_type_but_not_a_value():
    adapter = TypeAdapter()
    kind = adapter.resolve(VOID)
    assert type_model.is_void(kind)
    assert not type_model.is_value_type(kind)
    for name in VALUE_TYPES:
        assert type_model.is_value_type(adapter.resolve(name))


def test_none_is_not_a_type_at_the_adapter_boundary():
    adapter = TypeAdapter()
    with pytest.raises(TypeError, match="None"):
        adapter.resolve(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="None"):
        adapter.require_type(None)
    with pytest.raises(TypeError):
        adapter.resolve(1)  # type: ignore[arg-type]

    assert adapter.try_resolve(None) is None
    assert adapter.record_expression(1, None) is None
    assert adapter.resolved_types == {}


def test_require_type_accepts_only_concrete_model_variants():
    adapter = TypeAdapter()
    kinds = (
        type_model.INT,
        type_model.list_of(type_model.INT),
        type_model.Refined("Percent", type_model.INT, object()),
        type_model.TypeVariable(0),
    )
    for kind in kinds:
        assert adapter.require_type(kind) is kind

    with pytest.raises(TypeError, match="not a resolved type"):
        adapter.require_type(type_model.Type())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not a resolved type"):
        adapter.require_type(object())  # type: ignore[arg-type]


def test_record_expression_is_explicit_about_unknown_names():
    adapter = TypeAdapter()
    assert adapter.record_expression(2, "Int") is type_model.INT
    assert adapter.resolved_types == {2: type_model.INT}

    with pytest.raises(ValueError, match="Missing"):
        adapter.record_expression(3, "Missing")
    assert adapter.resolved_types == {2: type_model.INT}


# Refined types and the current nominal identity


def test_refined_types_are_adapted_with_their_real_chain():
    checker, checked, diagnostics = shadow(with_main(f"{PERCENT}\n{SMALL}", "let p: Percent = 40\nlet s: Small = 5"))
    assert diagnostics == []
    adapter = checker._type_adapter

    percent = adapter.refined("Percent")
    small = adapter.refined("Small")
    assert percent is not None and small is not None
    assert type_model.display(percent) == "Percent"
    assert percent.base is type_model.INT
    assert isinstance(small.base, type_model.Refined)
    assert small.base is percent
    assert type_model.display(type_model.root(small)) == "Int"

    # The old metadata is untouched and remains the source of the chain and cost.
    assert checked.refined["Small"].base == "Percent"
    assert checked.refined["Small"].root == "Int"
    assert [step.name for step in checked.refined["Small"].chain] == ["Percent", "Small"]
    assert checked.refined["Small"].cost > 0


def test_refined_identity_is_still_the_declared_name():
    checker, _, diagnostics = shadow(with_main(f"{PERCENT}\n{SMALL}", "let p: Percent = 40"))
    assert diagnostics == []
    adapter = checker._type_adapter
    percent = adapter.refined("Percent")
    same_name = type_model.Refined("Percent", type_model.FLOAT, object())

    assert type_model.equal(percent, same_name)
    assert not type_model.equal(percent, adapter.refined("Small"))
    assert adapter.refined("Missing") is None


def test_refined_model_keeps_the_exact_declaration_reference():
    checker, checked, diagnostics = shadow(with_main(f"{PERCENT}\n{SMALL}", "let p: Percent = 40"))
    assert diagnostics == []
    adapter = checker._type_adapter

    for name in ("Percent", "Small"):
        model = adapter.refined(name)
        metadata = checked.refined[name]
        assert model is not None
        assert model.declaration is metadata.declaration


def test_resolved_types_is_historical_after_a_parent_is_dropped():
    text = with_main(
        "type Child = Parent where value > 0\n"
        "type Parent = Int where value + 1",
        "let n = 1",
    )
    checker, checked, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert checked.refined == {}

    adapter = checker._type_adapter
    assert adapter.refined("Child") is None
    assert adapter.refined("Parent") is None
    assert adapter.resolve("Child") is None
    assert adapter.resolve("Parent") is None

    # Historical snapshot, not the current set of valid types: `Parent` was
    # recorded while Child's condition was checked, before Parent was dropped.
    assert "Parent" in {type_model.display(kind) for kind in adapter.resolved_types.values()}

    # The current decision paths still use `_refined`, not the historical map.
    assert checker._root("Parent") == "Parent"
    assert not checker._accepts("Int", "Parent")


def test_an_invalid_condition_prunes_the_whole_refined_chain():
    text = with_main(
        "type Base = Int where value >= 0\n"
        "type Middle = Base where value + 1\n"
        "type Leaf = Middle where value < 10",
        "let n = 1",
    )
    checker, checked, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert set(checked.refined) == {"Base"}

    adapter = checker._type_adapter
    assert adapter.refined("Base") is not None
    assert adapter.refined("Middle") is None
    assert adapter.refined("Leaf") is None
    assert adapter.resolve("Middle") is None
    assert adapter.resolve("Leaf") is None


# B1: `_root` goes through the model for representable types


@pytest.mark.parametrize("name", KNOWN_TYPES)
def test_root_matches_legacy_for_every_known_primitive(name: str):
    checker = Checker()
    assert checker._root(name) == legacy_root(checker, name) == name


def test_root_matches_legacy_for_a_valid_refined_chain():
    checker, _, diagnostics = shadow(with_main(f"{PERCENT}\n{SMALL}", "let p: Small = 5"))
    assert diagnostics == []
    assert checker._root("Small") == legacy_root(checker, "Small") == "Int"
    assert checker._root("Percent") == legacy_root(checker, "Percent") == "Int"


def test_root_matches_legacy_for_a_dropped_refined_type():
    text = with_main(
        "type Child = Parent where value > 0\n"
        "type Parent = Int where value + 1",
        "let n = 1",
    )
    checker, _, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert "Child" not in checker._refined
    assert "Parent" not in checker._refined

    assert checker._root("Child") == legacy_root(checker, "Child") == "Child"
    assert checker._root("Parent") == legacy_root(checker, "Parent") == "Parent"

    # The historical expression map still contains Parent; `_root` must not use it.
    historical = {type_model.display(kind) for kind in checker._type_adapter.resolved_types.values()}
    assert "Parent" in historical


@pytest.mark.parametrize("name", ["Missing", "Text.length", ANY_VALUE])
def test_root_matches_legacy_for_names_outside_the_model(name: str):
    checker = Checker()
    assert checker._root(name) == legacy_root(checker, name) == name


def test_root_matches_legacy_for_a_generic_name_not_enabled():
    # NEXORA has no syntax for this kind of name today. This is a direct unit
    # test of the fallback that keeps the model out of unsupported constructs.
    checker = Checker()
    assert checker._root("List[Int]") == legacy_root(checker, "List[Int]") == "List[Int]"


def test_root_does_not_hide_a_missing_primitive_model(monkeypatch):
    # Fault injection for an internal invariant: production resolves every
    # KNOWN_TYPES name, but a broken bridge must never become a silent fallback.
    checker = Checker()
    monkeypatch.setattr(checker._type_adapter, "resolve", lambda name: None)
    with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
        checker._root("Int")


def test_root_does_not_hide_a_missing_refined_model(monkeypatch):
    checker, _, diagnostics = shadow(with_main(PERCENT, "let p: Percent = 50"))
    assert diagnostics == []
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
        checker._root("Percent")


def test_accepts_keeps_its_legacy_refined_chain():
    checker, _, diagnostics = shadow(with_main(f"{PERCENT}\n{SMALL}", "let p: Small = 5"))
    assert diagnostics == []
    assert checker._accepts("Int", "Small")
    assert checker._accepts("Percent", "Small")
    assert not checker._accepts("Small", "Percent")
    assert not checker._accepts("Int", "Missing")


def test_root_is_differentially_equivalent_on_examples(monkeypatch):
    """The new model-backed `_root` must produce the same analysis as the old one."""
    for path in sorted(EXAMPLE_DIR.rglob("*.nex")):
        program, _ = parse_text(path.read_text(encoding="utf-8"))

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)

        with monkeypatch.context() as patch:
            patch.setattr(Checker, "_root", lambda self, kind: legacy_root(self, kind))
            old_checker = Checker()
            old_checked, old_diagnostics = old_checker.check(program)

        # The same AST is used for both runs, so the id-keyed maps are comparable.
        assert new_diagnostics == old_diagnostics
        assert new_checked.types == old_checked.types
        assert new_checked.symbols == old_checked.symbols
        assert new_checked.calls == old_checked.calls
        assert new_checked.refined == old_checked.refined


# B2: `_accepts` goes through `assignable` for representable types


def test_accepts_matches_legacy_for_representable_types():
    checker, _, diagnostics = shadow(with_main(f"{PERCENT}\n{SMALL}", "let p: Small = 5"))
    assert diagnostics == []
    cases = (
        ("Int", "Int", True),
        ("Int", "Float", False),
        ("Float", "Float", True),
        ("Text", "Int", False),
        ("Bool", "Bool", True),
        ("Int", "Percent", True),
        ("Int", "Small", True),
        ("Percent", "Percent", True),
        ("Percent", "Small", True),
        ("Small", "Percent", False),
        ("Percent", "Int", False),
        ("Small", "Int", False),
    )
    for expected, found, accepted in cases:
        assert checker._accepts(expected, found) == accepted
        assert legacy_accepts(checker, expected, found) == accepted


def test_accepts_uses_the_chain_but_not_only_the_root():
    grade = "type Grade = Int where value >= 0 and value <= 10"
    checker, _, diagnostics = shadow(
        with_main(f"{PERCENT}\n{grade}", "let p: Percent = 5\nlet g: Grade = 5")
    )
    assert diagnostics == []
    cases = (
        ("Int", "Percent", True),
        ("Int", "Grade", True),
        ("Percent", "Grade", False),
        ("Grade", "Percent", False),
        ("Text", "Grade", False),
    )
    for expected, found, accepted in cases:
        assert checker._accepts(expected, found) == accepted
        assert legacy_accepts(checker, expected, found) == accepted


def test_accepts_does_not_use_pruned_refined_types():
    text = with_main(
        "type Base = Int where value >= 0\n"
        "type Middle = Base where value + 1\n"
        "type Leaf = Middle where value < 10",
        "let n = 1\nlet b: Base = 1",
    )
    checker, checked, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert set(checked.refined) == {"Base"}
    cases = (
        ("Int", "Middle"),
        ("Int", "Leaf"),
        ("Base", "Middle"),
        ("Base", "Leaf"),
        ("Middle", "Base"),
        ("Middle", "Leaf"),
        ("Leaf", "Base"),
    )
    for expected, found in cases:
        assert not checker._accepts(expected, found)
        assert not legacy_accepts(checker, expected, found)


def test_accepts_does_not_restore_a_dropped_parent_from_resolved_types():
    text = with_main(
        "type Child = Parent where value > 0\n"
        "type Parent = Int where value + 1",
        "let n = 1",
    )
    checker, checked, diagnostics = shadow(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2011"]
    assert checked.refined == {}

    historical = {type_model.display(kind) for kind in checker._type_adapter.resolved_types.values()}
    assert "Parent" in historical
    for expected, found in (("Int", "Parent"), ("Int", "Child")):
        assert not checker._accepts(expected, found)
        assert not legacy_accepts(checker, expected, found)


@pytest.mark.parametrize(("expected", "found", "accepted"), [
    ("Missing", "Missing", True),
    ("Missing", "Int", False),
    ("Int", "Missing", False),
    ("Text.length", "Text.length", True),
    ("Text.length", "Int", False),
    ("Int", "Text.length", False),
])
def test_accepts_keeps_the_legacy_rule_for_names_outside_the_model(expected, found, accepted):
    checker = Checker()
    assert checker._accepts(expected, found) == accepted
    assert legacy_accepts(checker, expected, found) == accepted


@pytest.mark.parametrize(("expected", "found", "accepted"), [
    (ANY_VALUE, ANY_VALUE, True),
    (ANY_VALUE, "Int", False),
    ("Int", ANY_VALUE, False),
])
def test_accepts_keeps_any_value_outside_the_model(expected, found, accepted):
    checker = Checker()
    assert checker._accepts(expected, found) == accepted
    assert legacy_accepts(checker, expected, found) == accepted


@pytest.mark.parametrize(("expected", "found", "accepted"), [
    ("Void", "Void", True),
    ("Void", "Int", False),
    ("Int", "Void", False),
    ("List[Int]", "List[Int]", True),
    ("List[Int]", "List[Text]", False),
    ("List[Int]", "Int", False),
    ("Int", "List[Int]", False),
])
def test_accepts_does_not_widen_void_or_unenabled_generics(expected, found, accepted):
    # Exact names outside the model still compare by name, as before; they never
    # gain the structural compatibility of the model's composite types.
    checker = Checker()
    assert checker._accepts(expected, found) == accepted
    assert legacy_accepts(checker, expected, found) == accepted


def test_accepts_does_not_hide_a_missing_primitive_model(monkeypatch):
    checker = Checker()
    monkeypatch.setattr(checker._type_adapter, "resolve", lambda name: None)
    for expected, found in (("Int", "Int"), ("Int", "Missing"), ("Missing", "Int")):
        with pytest.raises(RuntimeError, match="primitive type 'Int' is missing"):
            checker._accepts(expected, found)


def test_accepts_does_not_hide_a_missing_refined_model(monkeypatch):
    checker, _, diagnostics = shadow(with_main(PERCENT, "let p: Percent = 50"))
    assert diagnostics == []
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    for expected, found in (
        ("Percent", "Percent"),
        ("Percent", "Int"),
        ("Int", "Percent"),
        ("Percent", "Missing"),
        ("Missing", "Percent"),
    ):
        with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
            checker._accepts(expected, found)


def test_accepts_is_differentially_equivalent_on_examples(monkeypatch):
    """The new model-backed `_accepts` must produce the same analysis as the old one."""
    for path in sorted(EXAMPLE_DIR.rglob("*.nex")):
        program, _ = parse_text(path.read_text(encoding="utf-8"))

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)

        with monkeypatch.context() as patch:
            patch.setattr(
                Checker, "_accepts", lambda self, expected, found: legacy_accepts(self, expected, found)
            )
            old_checker = Checker()
            old_checked, old_diagnostics = old_checker.check(program)

        # The same AST is used for both runs, so the id-keyed maps are comparable.
        assert new_diagnostics == old_diagnostics
        assert new_checked.types == old_checked.types
        assert new_checked.symbols == old_checked.symbols
        assert new_checked.calls == old_checked.calls
        assert new_checked.refined == old_checked.refined


# B3: `_expect_type` goes through the model for representable types


def literal(value: int) -> ast.IntLiteral:
    return ast.IntLiteral(span=SPAN, value=value)


def name_node() -> ast.Name:
    return ast.Name(span=SPAN, name="n")


def test_expect_type_matches_legacy_for_representable_types():
    text = with_main(f"{PERCENT}\n{SMALL}\n{GRADE}", "let n = 1")
    node = name_node()
    cases = (
        ("Int", "Int", []),
        ("Int", "Float", ["E2011"]),
        ("Text", "Int", ["E2011"]),
        ("Int", "Percent", []),
        ("Int", "Small", []),
        ("Int", "Grade", []),
        ("Percent", "Int", ["E2011"]),
        ("Small", "Int", ["E2011"]),
        ("Percent", "Small", []),
        ("Small", "Percent", ["E2011"]),
        ("Percent", "Grade", ["E2011"]),
        ("Grade", "Percent", ["E2011"]),
        ("Text", "Grade", ["E2011"]),
    )
    for expected, found, expected_codes in cases:
        new, old = expect_pair(text, expected, found, node)
        assert [diag.code for diag in new] == expected_codes, (expected, found)
        assert new == old, (expected, found)


def test_expect_type_matches_legacy_for_constants():
    text = with_main(f"{PERCENT}\n{SMALL}", "let n = 1")
    cases = (
        ("Percent", literal(50), []),
        ("Percent", literal(150), ["E2017"]),
        ("Small", literal(5), []),
        ("Small", literal(15), ["E2017"]),
        ("Percent", ast.Group(span=SPAN, expression=literal(50)), []),
        ("Percent", ast.Unary(span=SPAN, operator="-", operand=literal(5)), ["E2017"]),
        ("Percent", ast.Unary(span=SPAN, operator="-", operand=literal(150)), ["E2017"]),
        ("Percent", name_node(), ["E2011"]),
    )
    for expected, node, expected_codes in cases:
        new, old = expect_pair(text, expected, "Int", node)
        assert [diag.code for diag in new] == expected_codes, (expected, node)
        assert new == old, (expected, node)


def test_expect_type_matches_legacy_for_names_outside_the_model():
    text = in_main("let n = 1")
    node = name_node()
    cases = (
        ("Missing", "Missing", []),
        ("Missing", "Int", ["E2011"]),
        ("Int", "Missing", ["E2011"]),
        (ANY_VALUE, ANY_VALUE, []),
        (ANY_VALUE, "Int", ["E2011"]),
        ("Int", ANY_VALUE, ["E2011"]),
        ("Void", "Void", []),
        ("Void", "Int", ["E2011"]),
        ("Int", "Void", ["E2011"]),
        ("List[Int]", "List[Int]", []),
        ("List[Int]", "Int", ["E2011"]),
        ("Int", "List[Int]", ["E2011"]),
    )
    for expected, found, expected_codes in cases:
        new, old = expect_pair(text, expected, found, node)
        assert [diag.code for diag in new] == expected_codes, (expected, found)
        assert new == old, (expected, found)


def test_expect_type_matches_legacy_for_dropped_refinements():
    text = with_main(
        "type Child = Parent where value > 0\ntype Parent = Int where value + 1",
        "let n = 1",
    )
    node = name_node()
    cases = (
        ("Int", "Parent", ["E2011"]),
        ("Int", "Child", ["E2011"]),
        ("Parent", "Int", ["E2011"]),
        ("Child", "Int", ["E2011"]),
        ("Parent", "Parent", []),
        ("Child", "Child", []),
        ("Parent", "Child", ["E2011"]),
    )
    for expected, found, expected_codes in cases:
        new, old = expect_pair(text, expected, found, node)
        assert [diag.code for diag in new] == expected_codes, (expected, found)
        assert new == old, (expected, found)


def test_expect_type_does_not_hide_a_missing_refined_model(monkeypatch):
    checker, _, diagnostics = shadow(with_main(PERCENT, "let p: Percent = 50"))
    assert diagnostics == []
    monkeypatch.setattr(checker._type_adapter, "refined", lambda name: None)
    node = name_node()
    for expected, found in (
        ("Percent", "Percent"),
        ("Percent", "Int"),
        ("Int", "Percent"),
        ("Percent", "Missing"),
        ("Missing", "Percent"),
    ):
        with pytest.raises(RuntimeError, match="refined type 'Percent' is missing"):
            checker._expect_type(expected, found, node, ())


def test_expect_type_is_not_called_for_unresolved_or_void_values(monkeypatch):
    text = with_main(
        "fn f() -> Int {\n    return print(1)\n}",
        'let x: Missing = 1\nlet y = print(1)\nlet z: Int = print(1)',
    )

    def fail(*args, **kwargs):
        raise AssertionError("_expect_type must not run for unresolved or Void values")

    monkeypatch.setattr(Checker, "_expect_type", fail)
    diagnostics = diagnostics_of(text)
    assert [diag.code for diag in diagnostics] == ["E2011", "E2012", "E2011", "E2011"]


def test_expect_type_preserves_diagnostic_order_on_a_mixed_program(monkeypatch):
    text = with_main(
        PERCENT,
        'let a: Percent = 150\nlet b: Int = "x"\nlet c: Int = 1.0\nlet n = 1\nlet d: Percent = n',
    )
    program, _ = parse_text(text)

    new_checker = Checker()
    new_checked, new_diagnostics = new_checker.check(program)

    with monkeypatch.context() as patch:
        patch.setattr(Checker, "_expect_type", legacy_expect_type)
        old_checker = Checker()
        old_checked, old_diagnostics = old_checker.check(program)

    assert [diag.code for diag in new_diagnostics] == ["E2017", "E2011", "E2011", "E2011"]
    assert new_diagnostics == old_diagnostics
    assert new_checked.types == old_checked.types
    assert new_checked.symbols == old_checked.symbols


def test_expect_type_is_differentially_equivalent_on_examples(monkeypatch):
    """The model-backed `_expect_type` must produce the same analysis, and the same documents."""
    builders = {
        "check": tooling.check_source,
        "inspect": tooling.inspect_source,
        "symbols": tooling.get_symbols,
        "context": tooling.get_context,
    }
    for path in sorted(EXAMPLE_DIR.rglob("*.nex")):
        text = path.read_text(encoding="utf-8")
        program, _ = parse_text(text)

        new_checker = Checker()
        new_checked, new_diagnostics = new_checker.check(program)
        new_documents = {name: builder(text) for name, builder in builders.items()}

        with monkeypatch.context() as patch:
            patch.setattr(Checker, "_expect_type", legacy_expect_type)
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


# Shadow parity


def test_resolved_expression_types_match_the_public_strings():
    text = with_main(
        f"{PERCENT}\n{SMALL}",
        'let p: Percent = 40\nlet s: Small = 5\nlet n = 1\nlet f = 1.5\nlet b = true\nlet t = "x"\n'
        "let total = p + 1\nif total > 0 {\n    print(s)\n}\n",
    )
    checker, checked, diagnostics = shadow(text)
    assert diagnostics == []
    resolved = checker._type_adapter.resolved_types
    assert set(resolved) == set(checked.types)
    for node_id, text_type in checked.types.items():
        assert type_model.display(resolved[node_id]) == text_type


def test_shadow_parity_also_holds_for_programs_with_errors():
    text = in_main('let x: Int = "no"\nlet y = print(1)\nlet z = missing')
    checker, checked, diagnostics = shadow(text)
    assert diagnostics
    resolved = checker._type_adapter.resolved_types
    assert set(resolved) == set(checked.types)
    for node_id, text_type in checked.types.items():
        assert type_model.display(resolved[node_id]) == text_type


@pytest.mark.parametrize("path", sorted(EXAMPLE_DIR.rglob("*.nex")))
def test_shadow_matches_every_example(path: Path):
    checker, checked, _ = shadow(path.read_text(encoding="utf-8"))
    resolved = checker._type_adapter.resolved_types
    assert set(resolved) == set(checked.types)
    for node_id, text_type in checked.types.items():
        assert type_model.display(resolved[node_id]) == text_type


# The language has no composite types in its resolver yet


@pytest.mark.parametrize("name", ["List", "Option", "Result", "list", "option", "result"])
def test_composite_names_are_not_resolved(name: str):
    assert TypeAdapter().resolve(name) is None


@pytest.mark.parametrize("name", ["List", "Option", "Result"])
def test_composite_names_still_fail_as_written_types(name: str):
    (error,) = diagnostics_of(in_main(f"let x: {name} = 1"))
    assert (error.code, error.label) == ("E2012", f"'{name}' is not a type")


# Public documents and signatures keep their exact string shape


def test_public_documents_keep_strings_and_existing_values():
    text = with_main(f"{PERCENT}\n{SMALL}", "let p: Percent = 40\nlet s: Small = 5\nprint(s)")
    documents = {
        "check": tooling.check_source(text),
        "inspect": tooling.inspect_source(text),
        "symbols": tooling.get_symbols(text),
        "context": tooling.get_context(text),
    }
    for document in documents.values():
        json.dumps(document)

    assert documents["check"]["diagnostics"] == []
    symbols = {entry["name"]: entry for entry in documents["symbols"]["symbols"]}
    assert (symbols["p"]["type"], symbols["s"]["type"]) == ("Percent", "Small")
    print_builtin = next(entry for entry in documents["symbols"]["builtins"] if entry["name"] == "print")
    assert print_builtin["params"] == [{"name": "value", "type": "Int | Float | Bool | Text"}]
    assert print_builtin["return_type"] == "Void"
    assert print_builtin["signature"] == "fn print(value: Int | Float | Bool | Text) -> Void"

    types = {entry["name"]: entry for entry in documents["context"]["types"]}
    assert (types["Percent"]["base"], types["Percent"]["root"]) == ("Int", "Int")
    assert (types["Small"]["base"], types["Small"]["root"]) == ("Percent", "Int")

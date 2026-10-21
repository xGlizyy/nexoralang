"""The internal type model: identity, compatibility, substitution, unification and display.

These tests exercise `nexora.types` in isolation. The checker now builds these objects in
shadow mode through `type_adapter` (Phase A of D01); the parser and the JSON documents still do
not use them, so a failure here means a bug in the model itself.
"""

import dataclasses

import pytest

from nexora import types as t


def make_refined(name: str = "Percent", base: t.Type | None = None) -> t.Refined:
    """A refined type with a throwaway declaration reference."""
    return t.Refined(name, t.INT if base is None else base, object())


# Primitives and Void

@pytest.mark.parametrize("name", ["Int", "Float", "Bool", "Text", "Void"])
def test_primitives_can_be_named(name):
    assert t.Primitive(name).name == name


def test_an_unknown_primitive_is_rejected():
    with pytest.raises(ValueError):
        t.Primitive("Integer")


def test_void_is_a_type_but_not_a_value_type():
    assert t.is_void(t.VOID)
    assert not t.is_value_type(t.VOID)
    for kind in (t.INT, t.FLOAT, t.BOOL, t.TEXT):
        assert t.is_value_type(kind)
        assert not t.is_void(kind)


def test_void_cannot_be_an_argument_of_a_constructor():
    with pytest.raises(ValueError):
        t.list_of(t.VOID)
    with pytest.raises(ValueError):
        t.application(t.RESULT, t.TEXT, t.VOID)


def test_void_cannot_be_the_base_of_a_refined_type():
    with pytest.raises(ValueError):
        make_refined("Nothing", t.VOID)


def test_a_refined_type_needs_a_name():
    with pytest.raises(ValueError):
        t.Refined("", t.INT, object())


# Constructors, arity and nesting

def test_a_constructor_has_a_fixed_arity():
    assert (t.LIST.name, t.LIST.arity) == ("List", 1)
    assert (t.OPTION.name, t.OPTION.arity) == ("Option", 1)
    assert (t.RESULT.name, t.RESULT.arity) == ("Result", 2)


def test_a_wrong_arity_is_rejected():
    with pytest.raises(ValueError):
        t.application(t.LIST, t.INT, t.TEXT)
    with pytest.raises(ValueError):
        t.application(t.RESULT, t.TEXT)


def test_constructors_are_validated():
    with pytest.raises(ValueError):
        t.Constructor("", 0, "x")
    with pytest.raises(ValueError):
        t.Constructor("X", -1, "x")
    with pytest.raises(ValueError):
        t.Constructor("X", 0, "")


def test_nested_types_keep_their_structure():
    kind = t.list_of(t.option_of(t.INT))
    assert t.equal(kind.arguments[0].arguments[0], t.INT)
    assert t.equal(kind, t.application(t.LIST, t.application(t.OPTION, t.INT)))


def test_a_nullary_constructor_displays_without_brackets():
    unit = t.Constructor("Unit", 0, "Unit")
    assert t.display(t.application(unit)) == "Unit"


# Identity: structural and nominal

def test_primitives_are_equal_by_name():
    assert t.equal(t.INT, t.Primitive("Int"))
    assert not t.equal(t.INT, t.TEXT)


def test_applications_are_structural():
    assert t.equal(t.list_of(t.INT), t.application(t.LIST, t.INT))
    assert not t.equal(t.list_of(t.INT), t.list_of(t.TEXT))
    assert not t.equal(t.result_of(t.TEXT, t.INT), t.result_of(t.TEXT, t.BOOL))


def test_refined_types_are_nominal():
    one = make_refined("Percent")
    two = make_refined("Percent")
    other = make_refined("Cantidad")
    assert t.equal(one, two)
    assert not t.equal(one, other)
    assert not t.equal(one, t.INT)


def test_refined_identity_does_not_depend_on_the_base():
    assert t.equal(make_refined("Percent", t.INT), make_refined("Percent", t.FLOAT))


def test_type_variables_are_equal_by_identifier():
    assert t.equal(t.TypeVariable(0, "T"), t.TypeVariable(0, "U"))
    assert not t.equal(t.TypeVariable(0), t.TypeVariable(1))
    assert not t.equal(t.TypeVariable(0), t.INT)


# Invariance, assignability and widening

def test_generic_arguments_are_invariant():
    assert t.equal(t.list_of(t.INT), t.list_of(t.INT))
    assert not t.assignable(t.list_of(t.INT), t.list_of(t.TEXT))
    assert not t.assignable(t.option_of(t.INT), t.option_of(t.TEXT))
    assert t.assignable(t.list_of(t.INT), t.list_of(t.INT))


def test_generic_arguments_are_invariant_even_for_refined_types():
    percent = make_refined("Percent", t.INT)
    assert not t.assignable(t.list_of(t.INT), t.list_of(percent))


def test_a_refined_type_is_assignable_to_its_base():
    percent = make_refined("Percent", t.INT)
    assert t.assignable(t.INT, percent)
    assert t.assignable(t.INT, t.INT)


def test_the_reverse_conversion_is_not_assignable():
    percent = make_refined("Percent", t.INT)
    assert not t.assignable(percent, t.INT)
    assert not t.assignable(percent, t.TEXT)


def test_a_chain_of_refinements_widens_to_the_whole_chain():
    positive = make_refined("Positive", t.INT)
    percent = make_refined("Percent", positive)
    assert t.assignable(t.INT, percent)
    assert t.assignable(positive, percent)
    assert not t.assignable(percent, positive)
    assert t.equal(t.widen(percent), positive)
    assert t.equal(t.root(percent), t.INT)
    assert t.widen(t.INT) is None


def test_root_stops_at_a_composite_base():
    kind = make_refined("NonEmpty", t.list_of(t.INT))
    assert t.equal(t.widen(kind), t.list_of(t.INT))
    assert t.equal(t.root(kind), t.list_of(t.INT))


def test_assignable_and_equal_are_separate_operations():
    percent = make_refined("Percent", t.INT)
    assert not t.equal(t.INT, percent)
    assert t.assignable(t.INT, percent)


# Substitution

def test_substitution_replaces_variables():
    var = t.TypeVariable(0, "T")
    assert t.equal(t.substitute(t.list_of(var), {0: t.INT}), t.list_of(t.INT))


def test_substitution_is_recursive():
    result = t.substitute(t.result_of(t.TypeVariable(0), t.TypeVariable(1)), {0: t.TEXT, 1: make_refined("Error")})
    assert t.equal(result, t.result_of(t.TEXT, make_refined("Error")))


def test_substitution_leaves_unbound_variables():
    var = t.TypeVariable(0, "T")
    assert t.equal(t.substitute(t.list_of(var), {}), t.list_of(var))


def test_substitution_does_not_change_the_original():
    original = t.list_of(t.TypeVariable(0, "T"))
    t.substitute(original, {0: t.INT})
    assert t.equal(original, t.list_of(t.TypeVariable(0, "T")))


def test_substitution_rejects_void_in_a_constructor():
    with pytest.raises(ValueError):
        t.substitute(t.list_of(t.TypeVariable(0)), {0: t.VOID})


def test_substitution_rejects_a_cyclic_mapping():
    var = t.TypeVariable(0, "T")
    with pytest.raises(ValueError):
        t.substitute(var, {0: var})
    with pytest.raises(ValueError):
        t.substitute(var, {0: t.list_of(var)})


# Unification

def test_unification_binds_a_variable():
    assert t.unify(t.list_of(t.TypeVariable(0, "T")), t.list_of(t.INT)) == {0: t.INT}


def test_unification_binds_several_variables():
    left = t.result_of(t.TypeVariable(0), t.TypeVariable(1))
    right = t.result_of(t.TEXT, make_refined("Error"))
    assert t.unify(left, right) == {0: t.TEXT, 1: make_refined("Error")}


def test_unification_of_two_variables():
    assert t.unify(t.TypeVariable(0), t.TypeVariable(1)) == {0: t.TypeVariable(1)}


def test_unification_binds_a_variable_on_the_right():
    assert t.unify(t.INT, t.TypeVariable(0, "T")) == {0: t.INT}


def test_unification_rejects_a_cycle_on_the_right():
    var = t.TypeVariable(0, "T")
    assert t.unify(t.list_of(var), var) is None


def test_unification_does_not_loop_on_a_cyclic_mapping():
    var = t.TypeVariable(0, "T")
    assert t.unify(var, t.INT, {0: var}) == {0: t.INT}


def test_unification_rejects_different_primitives():
    assert t.unify(t.INT, t.TEXT) is None


def test_unification_rejects_different_constructors():
    assert t.unify(t.list_of(t.INT), t.option_of(t.INT)) is None


def test_unification_rejects_incompatible_arguments():
    assert t.unify(t.list_of(t.INT), t.list_of(t.TEXT)) is None


def test_unification_rejects_a_cycle():
    var = t.TypeVariable(0, "T")
    assert t.unify(var, t.list_of(var)) is None


def test_unification_detects_an_indirect_cycle():
    zero, one = t.TypeVariable(0), t.TypeVariable(1)
    mapping = t.unify(zero, one)
    assert mapping is not None
    assert t.unify(one, t.list_of(zero), mapping) is None


def test_unification_does_not_change_the_caller_mapping():
    mapping: dict[int, t.Type] = {}
    t.unify(t.TypeVariable(0), t.INT, mapping)
    assert mapping == {}


def test_unification_uses_an_existing_mapping():
    mapping = {0: t.INT}
    assert t.unify(t.list_of(t.TypeVariable(0)), t.list_of(t.INT), mapping) == {0: t.INT}


# Presentation

def test_display_is_canonical():
    assert t.display(t.INT) == "Int"
    assert t.display(t.VOID) == "Void"
    assert t.display(t.list_of(t.option_of(t.INT))) == "List[Option[Int]]"
    assert t.display(t.result_of(t.TEXT, make_refined("Error"))) == "Result[Text, Error]"
    assert t.display(t.option_of(t.result_of(t.INT, make_refined("Error")))) == "Option[Result[Int, Error]]"


def test_display_of_a_refined_type_is_its_name():
    assert t.display(make_refined("Percent", t.INT)) == "Percent"


def test_display_of_a_type_variable_uses_its_name_or_identifier():
    assert t.display(t.TypeVariable(0, "T")) == "T"
    assert t.display(t.TypeVariable(2)) == "T2"


# Immutability and invalid structures

def test_the_model_is_immutable():
    kind = t.list_of(t.INT)
    with pytest.raises(dataclasses.FrozenInstanceError):
        kind.constructor = t.OPTION
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.INT.name = "Text"


def test_arguments_are_a_tuple():
    assert isinstance(t.list_of(t.INT).arguments, tuple)


def test_invalid_structures_are_rejected_before_use():
    with pytest.raises(ValueError):
        t.Primitive("Integer")
    with pytest.raises(ValueError):
        t.application(t.LIST, t.INT, t.TEXT)
    with pytest.raises(ValueError):
        t.list_of(t.VOID)
    with pytest.raises(ValueError):
        make_refined("Int", t.INT)
    with pytest.raises(ValueError):
        t.TypeVariable(-1)


def test_to_data_is_a_plain_tree_for_tests_only():
    data = t.to_data(t.result_of(t.TypeVariable(0, "T"), make_refined("Error")))
    assert data["kind"] == "application"
    assert data["constructor"] == "Result"
    assert data["identity"] == "Result"
    assert data["arguments"][0] == {"kind": "type_variable", "identifier": 0, "name": "T"}
    assert data["arguments"][1]["kind"] == "refined"
    assert data["arguments"][1]["base"] == {"kind": "primitive", "name": "Int"}

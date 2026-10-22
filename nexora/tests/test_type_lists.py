"""D01/I1: the adapter resolves the canonical `List[T]` form into the type model.

I1 extends the boundary between the checker's type names and the model. I3 then
lets `Checker._current_type_model` resolve `List[T]`; the checks that stay outside
the model (B4-B8) use `Range[Int]` as their sentinel.
"""

from __future__ import annotations

import pytest

from nexora import types as type_model
from nexora.checker import Checker
from nexora.type_adapter import TypeAdapter


def adapter_with_percent() -> tuple[TypeAdapter, type_model.Refined]:
    """An adapter with one registered refined type usable as an element."""
    adapter = TypeAdapter()
    return adapter, adapter.register_refined("Percent", "Int", object())


def nested_list_text(depth: int, item: str = "Int") -> str:
    return "List[" * depth + item + "]" * depth


@pytest.mark.parametrize("item", ["Int", "Float", "Bool", "Text"])
def test_a_list_of_a_primitive_resolves(item: str) -> None:
    adapter = TypeAdapter()

    kind = adapter.resolve(f"List[{item}]")

    assert isinstance(kind, type_model.Application)
    assert kind.constructor is type_model.LIST
    assert type_model.equal(kind, type_model.list_of(adapter.resolve(item)))
    assert type_model.display(kind) == f"List[{item}]"


def test_list_of_void_is_not_a_type() -> None:
    assert TypeAdapter().resolve("List[Void]") is None


def test_nested_lists_resolve() -> None:
    adapter = TypeAdapter()

    kind = adapter.resolve("List[List[Int]]")

    assert kind is not None
    assert type_model.equal(kind, type_model.list_of(type_model.list_of(type_model.INT)))
    assert type_model.display(kind) == "List[List[Int]]"

    deep = adapter.resolve("List[List[List[Text]]]")
    assert deep is not None
    assert type_model.display(deep) == "List[List[List[Text]]]"


def test_a_registered_refined_type_is_a_valid_element() -> None:
    adapter, percent = adapter_with_percent()

    kind = adapter.resolve("List[Percent]")

    assert kind is not None
    assert type_model.equal(kind, type_model.list_of(percent))
    assert type_model.display(kind) == "List[Percent]"

    nested = adapter.resolve("List[List[Percent]]")
    assert nested is not None
    assert type_model.display(nested) == "List[List[Percent]]"


def test_an_unregistered_refined_type_is_not_an_element() -> None:
    adapter = TypeAdapter()

    assert adapter.resolve("List[Percent]") is None
    assert adapter.resolve("List[List[Percent]]") is None


@pytest.mark.parametrize(
    "name",
    [
        "List[Missing]",
        "List[missing]",
        "List[List[Missing]]",
        "List[Map[Int]]",
        "List[Map[Int, Text]]",
        "Map[Int]",
        "Map[Int, Text]",
        "List",
        "Option",
        "Result",
    ],
)
def test_unknown_names_and_unsupported_constructors_do_not_resolve(name: str) -> None:
    assert TypeAdapter().resolve(name) is None


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        "[]",
        "List[]",
        "List[",
        "List]",
        "List[Int",
        "List[Int]]",
        "List[Int][Text]",
        "List[Int,]",
        "List[,Int]",
        "List[Int,,Text]",
        "List[Int Text]",
        "List[Int, Text]",
        "List[Int,Text]",
        "List[ Int]",
        "List[Int ]",
        "List[Int] ",
        " List[Int]",
        "List[\tInt]",
        "List[Int\n]",
        "List[Int];",
        "list[Int]",
        "LIST[Int]",
        "List[Int_ ]",
    ],
)
def test_malformed_or_non_canonical_forms_do_not_resolve(name: str) -> None:
    assert TypeAdapter().resolve(name) is None


def test_commas_inside_a_nested_argument_are_not_argument_separators() -> None:
    # A naive split on commas would read two arguments here; the recursive parser
    # reads one argument (an unsupported `Map`), so the name is not a type.
    assert TypeAdapter().resolve("List[Map[Int, Text]]") is None
    assert TypeAdapter().resolve("List[List[Int], List[Text]]") is None
    # The same shape with an admitted inner constructor is one valid argument.
    kind = TypeAdapter().resolve("List[List[Int]]")
    assert kind is not None
    assert type_model.display(kind) == "List[List[Int]]"


def test_nesting_up_to_the_limit_resolves() -> None:
    name = nested_list_text(64)

    kind = TypeAdapter().resolve(name)

    assert kind is not None
    assert type_model.display(kind) == name


def test_nesting_past_the_limit_is_rejected() -> None:
    assert TypeAdapter().resolve(nested_list_text(65)) is None


def test_a_refined_type_named_list_still_resolves_without_brackets() -> None:
    # `List` is not a reserved type name: the checker may declare a refined type
    # with that name. The bare name keeps resolving the refined type; only
    # `List[...]` is the built-in constructor.
    adapter = TypeAdapter()
    refined = adapter.register_refined("List", "Int", object())

    assert adapter.resolve("List") is refined

    kind = adapter.resolve("List[Int]")
    assert kind is not None
    assert type_model.equal(kind, type_model.list_of(type_model.INT))


def test_record_expression_accepts_a_list_type() -> None:
    adapter = TypeAdapter()

    kind = adapter.record_expression(1, "List[Int]")

    assert kind is not None
    assert type_model.equal(kind, type_model.list_of(type_model.INT))
    assert set(adapter.resolved_types) == {1}
    assert type_model.display(adapter.resolved_types[1]) == "List[Int]"


def test_record_expression_keeps_rejecting_unknown_types() -> None:
    adapter = TypeAdapter()
    adapter.record_expression(1, "Int")

    with pytest.raises(ValueError, match="Missing"):
        adapter.record_expression(2, "List[Missing]")

    assert set(adapter.resolved_types) == {1}


def test_record_expression_still_ignores_none() -> None:
    adapter = TypeAdapter()

    assert adapter.record_expression(1, None) is None
    assert adapter.resolved_types == {}


def test_try_resolve_matches_resolve_for_lists() -> None:
    adapter = TypeAdapter()

    assert type_model.equal(adapter.try_resolve("List[Int]"), adapter.resolve("List[Int]"))
    assert adapter.try_resolve("List[Missing]") is None
    assert adapter.try_resolve(None) is None


@pytest.mark.parametrize(
    "model",
    [
        type_model.INT,
        type_model.list_of(type_model.INT),
        type_model.list_of(type_model.list_of(type_model.TEXT)),
    ],
)
def test_display_and_resolve_are_inverses(model: type_model.Type) -> None:
    adapter = TypeAdapter()

    kind = adapter.resolve(type_model.display(model))

    assert kind is not None
    assert type_model.equal(kind, model)


def test_display_and_resolve_are_inverses_for_a_refined_element() -> None:
    adapter, percent = adapter_with_percent()
    model = type_model.list_of(percent)

    kind = adapter.resolve(type_model.display(model))

    assert kind is not None
    assert type_model.equal(kind, model)


def test_the_boundary_still_rejects_none_and_non_strings() -> None:
    adapter = TypeAdapter()

    with pytest.raises(TypeError, match="None"):
        adapter.resolve(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="string"):
        adapter.resolve(1)  # type: ignore[arg-type]


def test_current_type_model_resolves_lists() -> None:
    checker = Checker()

    assert checker._current_type_model("Int") is type_model.INT
    assert checker._current_type_model("List[Int]") == type_model.list_of(type_model.INT)
    assert checker._current_type_model("List[List[Int]]") == type_model.list_of(
        type_model.list_of(type_model.INT)
    )
    assert checker._current_type_model("List[Missing]") is None


def test_accepts_and_root_handle_lists() -> None:
    checker = Checker()

    assert checker._root("List[Int]") == "List[Int]"
    assert checker._accepts("List[Int]", "List[Int]") is True
    assert checker._accepts("List[Int]", "List[Text]") is False
    assert checker._accepts("Int", "List[Int]") is False

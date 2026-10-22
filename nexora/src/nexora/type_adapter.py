"""Explicit bridge between the checker's type names and the internal type model.

This is the adapter described by D01: it *accompanies* the existing string-based
checker without deciding any type rule. The checker keeps using its current
strings and `RefinedType` metadata; this module builds, for each valid type it
already resolved, the corresponding object from `types.py`. The checker uses
those objects for the rules already migrated to the model, including list
identity and invariance.

Two boundaries are deliberately strict:

* `resolve` takes a name and never accepts `None`; `try_resolve` is the explicit
  spelling for "a missing type stays missing".
* `require_type` refuses `None`, the bare `Type` base and foreign objects, so a
  failed resolution cannot silently become a valid type.

`resolved_types` is a historical snapshot of the types expressions had when
they were checked. Refined types that a later invalid condition removes stay in
that snapshot; it is not the set of types that are valid now. The current
authority is `resolve`/`refined`, which are pruned by `drop_refined`.

`ANY_VALUE` is a private checker sentinel and is not represented here. A composite
type enters only through the canonical textual form of the built-in constructors
this version admits: today `List[T]`, `Option[T]` and `Result[T, E]`, nested as
needed. A record type is not composite: the checker registers it with
`register_record`, with the identity of its declaration.
"""

from __future__ import annotations

from . import types as type_model
from .values import BOOL, FLOAT, INT, TEXT, VOID

# The public names still come from values.py. This is only their adaptation to
# the model, not a second source of language names.
PRIMITIVE_TYPES: dict[str, type_model.Primitive] = {
    INT: type_model.INT,
    FLOAT: type_model.FLOAT,
    BOOL: type_model.BOOL,
    TEXT: type_model.TEXT,
    VOID: type_model.VOID,
}

# The concrete variants of the model. `Type` is only their base class, not a
# resolved type by itself.
_MODEL_TYPE_VARIANTS = (
    type_model.Primitive,
    type_model.Application,
    type_model.Refined,
    type_model.Nominal,
    type_model.TypeVariable,
)

# The parser's MAX_NESTING is 64; a canonical name deeper than this cannot come
# from a program the parser accepts, so it is not a type this adapter admits.
_MAX_TYPE_NESTING = 64

# The characters of a NEXORA name, as in docs/language-spec.md section 2.3.
_NAME_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_NAME_PART = _NAME_START | frozenset("0123456789")


class TypeAdapter:
    """The resolved types the checker has seen, kept beside its strings.

    The adapter is per analysis. It must never be shared between two checkers:
    the current refined-type identity is the unqualified name of one file, and
    D13 has not decided how to qualify it across modules.
    """

    def __init__(self) -> None:
        self._primitives = dict(PRIMITIVE_TYPES)
        self._refined: dict[str, type_model.Refined] = {}
        self._records: dict[str, type_model.Nominal] = {}
        self._resolved_types: dict[int, type_model.Type] = {}

    @property
    def primitive_names(self) -> tuple[str, ...]:
        """The public primitive names this adapter can resolve."""
        return tuple(self._primitives)

    @property
    def resolved_types(self) -> dict[int, type_model.Type]:
        """A historical copy of expression types, by `id(node)`.

        This snapshot can contain a refined type that a later invalid condition
        removed. It must not be used to decide whether a type is currently
        valid: use `resolve` or `refined`, which are pruned by `drop_refined`.
        """
        return dict(self._resolved_types)

    def resolve(self, name: str) -> type_model.Type | None:
        """The resolved type named `name`, or None if that name is not a type.

        `name` must really be a string. In particular, `None` is not a type name:
        callers that may have a missing type use `try_resolve` instead.

        A composite type is accepted only in the canonical form `display` produces,
        today `List[T]`, `Option[T]` and `Result[T, E]` (nested as needed). The text is
        parsed, not split on commas, so a comma inside a nested argument is never read
        as two arguments. A malformed, non-canonical or unsupported name is not a type:
        it returns None.
        """
        if name is None:
            raise TypeError("None is not a type name")
        if not isinstance(name, str):
            raise TypeError(f"a type name must be a string, not {type(name).__name__}")
        return self._resolve_canonical(name)

    def _resolve_canonical(self, text: str) -> type_model.Type | None:
        """The model for a canonical type name, or None if the whole text is not one."""
        if not text:
            return None
        kind, end = self._parse_type(text, 0)
        if kind is None or end != len(text):
            return None
        return kind

    def _parse_type(self, text: str, index: int, depth: int = 0) -> tuple[type_model.Type | None, int]:
        """Parse `Name` or `Name[Type, ...]` at `index`.

        The returned index is meaningful only when the model is not None: it is
        then the position just after the type. The caller must check that the whole
        text was consumed. An unknown name, an unsupported constructor and every
        malformed form give `(None, index)` instead of raising.
        """
        if depth > _MAX_TYPE_NESTING:
            return None, index
        name, index = self._parse_name(text, index)
        if name is None:
            return None, index
        if index >= len(text) or text[index] != "[":
            return self._resolve_name(name), index
        arguments: list[type_model.Type] = []
        index += 1
        while True:
            argument, index = self._parse_type(text, index, depth + 1)
            if argument is None or index >= len(text):
                return None, index
            arguments.append(argument)
            separator = text[index]
            index += 1
            if separator == "]":
                break
            if separator != ",":
                return None, index
            # The canonical text separates the arguments with a comma and a space, as
            # `display` writes it: `Result[Int, Text]`.
            index = self._skip_spaces(text, index)
        if name != "List" and name != "Option" and name != "Result":
            return None, index
        expected = {"List": 1, "Option": 1, "Result": 2}[name]
        if len(arguments) != expected:
            return None, index
        try:
            if name == "List":
                return type_model.list_of(arguments[0]), index
            if name == "Option":
                return type_model.option_of(arguments[0]), index
            return type_model.result_of(arguments[0], arguments[1]), index
        except ValueError:
            # `List[Void]` is not a type: the model rejects Void as an argument.
            return None, index

    @staticmethod
    def _skip_spaces(text: str, index: int) -> int:
        """The first position at or after `index` that is not a space.

        The canonical text of a type separates the arguments with a comma and a space, as
        `display` writes it, so the spaces are part of the form that is accepted.
        """
        while index < len(text) and text[index] == " ":
            index += 1
        return index

    @staticmethod
    def _parse_name(text: str, index: int) -> tuple[str | None, int]:
        """Read a NEXORA name at `index`, or return `(None, index)`.

        A name of another module is written with its module in front, as `models.Point`
        (decision 0018, 5): one dot, and the model resolves the qualified name exactly as
        the analysis returns it, which is also qualified.
        """
        if index >= len(text) or text[index] not in _NAME_START:
            return None, index
        end = index + 1
        while end < len(text) and text[end] in _NAME_PART:
            end += 1
        if end + 1 < len(text) and text[end] == "." and text[end + 1] in _NAME_START:
            end += 2
            while end < len(text) and text[end] in _NAME_PART:
                end += 1
        return text[index:end], end

    def _resolve_name(self, name: str) -> type_model.Type | None:
        """Resolve a bare name, without interpreting brackets."""
        primitive = self._primitives.get(name)
        if primitive is not None:
            return primitive
        refined = self._refined.get(name)
        if refined is not None:
            return refined
        return self._records.get(name)

    def try_resolve(self, name: str | None) -> type_model.Type | None:
        """Resolve a name that may be missing, preserving `None` as "not resolved"."""
        if name is None:
            return None
        return self.resolve(name)

    def require_type(self, kind: type_model.Type | None) -> type_model.Type:
        """Return `kind` only if it is a concrete model type.

        `None`, the bare `Type` base and foreign objects are rejected.
        """
        if kind is None:
            raise TypeError("None is not a resolved type")
        if not isinstance(kind, _MODEL_TYPE_VARIANTS):
            raise TypeError(f"not a resolved type: {kind!r}")
        return kind

    def register_refined(self, name: str, base: str, declaration: object) -> type_model.Refined:
        """Build the model object for a refined type the checker has already accepted.

        The checker calls this only after `_resolve` has accepted the declaration,
        so an unresolved base here is an internal inconsistency, not a user error.
        """
        existing = self._refined.get(name)
        if existing is not None:
            return existing
        base_type = self.resolve(base)
        if base_type is None:
            raise ValueError(f"the base {base!r} of {name!r} was not resolved")
        refined = type_model.Refined(name, base_type, declaration)
        self._refined[name] = refined
        return refined

    def refined(self, name: str | None) -> type_model.Refined | None:
        """The model for a valid refined type, or None if it is absent or not refined."""
        if name is None:
            return None
        kind = self._refined.get(name)
        return kind

    def register_record(self, name: str, fields: tuple[tuple[str, type_model.Type], ...],
                        identity: type_model.RecordIdentity) -> type_model.Nominal:
        """Build the model object for a record type the checker has already accepted.

        The fields are given as model types, so the checker calls this only when every
        field type is already resolved: a record that depends on another one is
        registered after the ones it depends on.
        """
        existing = self._records.get(name)
        if existing is not None:
            return existing
        nominal = type_model.Nominal(name, fields, identity)
        self._records[name] = nominal
        return nominal

    def record(self, name: str | None) -> type_model.Nominal | None:
        """The model for a valid record type, or None if it is absent."""
        if name is None:
            return None
        return self._records.get(name)

    def drop_refined(self, name: str) -> None:
        """Forget a refined type that the checker has made unusable.

        This deliberately leaves `resolved_types` untouched: that property is a
        historical snapshot, not the current set of valid types.
        """
        self._refined.pop(name, None)

    def record_expression(self, node_id: int, name: str | None) -> type_model.Type | None:
        """Record the resolved type of an expression when the checker had one.

        `None` means the checker could not resolve a type; it is not stored and
        the method returns `None`. A non-None name that does not resolve is an
        internal inconsistency, never a missing type, so it raises `ValueError`.
        """
        if name is None:
            return None
        kind = self.resolve(name)
        if kind is None:
            raise ValueError(f"the type {name!r} of expression {node_id!r} was not resolved")
        self._resolved_types[node_id] = kind
        return kind


__all__ = ["PRIMITIVE_TYPES", "TypeAdapter"]

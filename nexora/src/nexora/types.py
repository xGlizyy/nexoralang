"""Internal type model: the structured representation of NEXORA types.

This module is an internal building block, not a public contract. The checker
builds these objects through `type_adapter`; the parser and the JSON documents
still use the canonical text. The language has syntax for `List[T]`; `Option`,
`Result` and the rest of the model are not enabled yet. The names here and the
shape of `to_data` are internal and may change; decision 0013 accepts this
model only for the scope it documents, not the whole D01 proposal.

The model separates what the source syntax says (`ast_nodes.TypeRef`) from the
resolved type the analysis reasons about. Its pieces are:

* `Primitive`: the built-in type names. `Void` is one of them, but it is not a
  value type: it cannot be a variable's type and it is rejected as an argument
  of a data constructor.
* `Constructor` and `Application`: a constructor with a fixed arity and its
  positional arguments. `List`, `Option` and `Result` are the built-in ones; a
  future declared type uses the same shape with its own identity.
* `Refined`: a nominal refined type. Two refined types with the same name are
  the same type even if they share a base and a condition; the declaration is
  kept as a stable reference for diagnostics and for the interpreter.
* `TypeVariable`: a first-order type variable, identified by an integer. It
  exists for substitution and unification; the language cannot write one yet.

Two operations that must not be confused:

* `equal` is type identity: structural for primitives and applications, nominal
  for refined types, by identifier for type variables.
* `assignable` is compatibility: a refined type is accepted where its base is
  expected (widening), never the other way round. Generic arguments are
  invariant.

`ANY_VALUE`, the sentinel the checker uses for the parameters of `print` and
`to_text`, is deliberately not represented here: turning it into a type would
add an `Any` the language does not have. How the checker maps it belongs to the
integration increment.

A function type is also left out for now: NEXORA has no function values. The
reserved shape (parameters and result) will be added when D01 needs it, without
changing the classes above.

Nothing here reads, executes or opens anything: it is pure data and pure
functions. A resolved type and `None` stay different: these functions take and
return `Type` objects, and it is the caller who keeps using `None` for the
errors it cannot resolve.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# The built-in type names. `Void` is a type, but it is not a value type.
VOID_NAME = "Void"
VALUE_PRIMITIVE_NAMES = frozenset({"Int", "Float", "Bool", "Text"})
PRIMITIVE_NAMES = VALUE_PRIMITIVE_NAMES | {VOID_NAME}


class Type:
    """Base class of every resolved type. The variants below are immutable."""

    __slots__ = ()


@dataclass(frozen=True)
class Primitive(Type):
    """A built-in type: `Int`, `Float`, `Bool`, `Text` or `Void`."""

    name: str

    def __post_init__(self) -> None:
        if self.name not in PRIMITIVE_NAMES:
            raise ValueError(f"unknown primitive type: {self.name!r}")


@dataclass(frozen=True)
class Constructor:
    """The name and the arity of a type constructor.

    `identity` is what makes two constructors the same type constructor. A
    built-in one uses its own name; a future declared type will use a stable
    identity that does not depend on the position in the file.
    """

    name: str
    arity: int
    identity: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a constructor needs a name")
        if not self.identity:
            raise ValueError("a constructor needs an identity")
        if self.arity < 0:
            raise ValueError("a constructor cannot have a negative arity")


@dataclass(frozen=True)
class Application(Type):
    """A constructor applied to positional arguments: `List[Int]`, `Result[Text, Error]`."""

    constructor: Constructor
    arguments: tuple[Type, ...]

    def __post_init__(self) -> None:
        if len(self.arguments) != self.constructor.arity:
            raise ValueError(
                f"{self.constructor.name} takes {self.constructor.arity} argument(s), "
                f"but {len(self.arguments)} were given"
            )
        for argument in self.arguments:
            if is_void(argument):
                raise ValueError(f"Void cannot be an argument of {self.constructor.name}")


@dataclass(frozen=True)
class Refined(Type):
    """A nominal refined type.

    Equality is by `name` only: `Percent` and `Cantidad` are different types
    even when they share a base and a condition. `declaration` is an opaque,
    stable reference to the declaration (today an `ast_nodes.TypeDecl`); it
    takes no part in equality and does not have to be hashable.
    """

    name: str
    base: Type = field(compare=False)
    declaration: object = field(compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a refined type needs a name")
        if self.name in PRIMITIVE_NAMES:
            raise ValueError(f"{self.name!r} is a built-in type name")
        if is_void(self.base):
            raise ValueError(f"the base of {self.name!r} cannot be Void")


@dataclass(frozen=True)
class TypeVariable(Type):
    """A first-order type variable, identified by an integer."""

    identifier: int
    name: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if self.identifier < 0:
            raise ValueError("a type variable identifier cannot be negative")


def is_void(kind: Type) -> bool:
    """Whether `kind` is `Void`, the type that has no value."""
    return isinstance(kind, Primitive) and kind.name == VOID_NAME


def is_value_type(kind: Type) -> bool:
    """Whether a value can have `kind`. Every type except `Void` is a value type."""
    return not is_void(kind)


# The built-in types and constructors.
INT = Primitive("Int")
FLOAT = Primitive("Float")
BOOL = Primitive("Bool")
TEXT = Primitive("Text")
VOID = Primitive(VOID_NAME)

LIST = Constructor("List", 1, "List")
OPTION = Constructor("Option", 1, "Option")
RESULT = Constructor("Result", 2, "Result")
BUILTIN_CONSTRUCTORS: dict[str, Constructor] = {constructor.name: constructor for constructor in (LIST, OPTION, RESULT)}


def application(constructor: Constructor, *arguments: Type) -> Application:
    """The constructor applied to `arguments`. Rejects a wrong arity and `Void`."""
    return Application(constructor, tuple(arguments))


def list_of(item: Type) -> Application:
    """`List[item]`."""
    return Application(LIST, (item,))


def option_of(item: Type) -> Application:
    """`Option[item]`."""
    return Application(OPTION, (item,))


def result_of(ok: Type, error: Type) -> Application:
    """`Result[ok, error]`."""
    return Application(RESULT, (ok, error))


# Identity

def equal(left: Type, right: Type) -> bool:
    """Type identity.

    Structural for primitives and constructor applications, nominal for refined
    types (the same declared name) and by identifier for type variables. It is
    not compatibility: see `assignable`.
    """
    if left is right:
        return True
    if isinstance(left, Primitive) and isinstance(right, Primitive):
        return left.name == right.name
    if isinstance(left, Application) and isinstance(right, Application):
        if left.constructor.identity != right.constructor.identity:
            return False
        if left.constructor.arity != right.constructor.arity:
            return False
        return len(left.arguments) == len(right.arguments) and all(
            equal(argument, other) for argument, other in zip(left.arguments, right.arguments, strict=True)
        )
    if isinstance(left, Refined) and isinstance(right, Refined):
        return left.name == right.name
    if isinstance(left, TypeVariable) and isinstance(right, TypeVariable):
        return left.identifier == right.identifier
    return False


# Compatibility and widening

def widen(kind: Type) -> Type | None:
    """The immediate base a refined type widens to, or None when there is none."""
    return kind.base if isinstance(kind, Refined) else None


def root(kind: Type) -> Type:
    """The type at the end of a chain of refinements, or `kind` itself if it is not refined."""
    current = kind
    while isinstance(current, Refined):
        current = current.base
    return current


def assignable(expected: Type, found: Type) -> bool:
    """Whether a value of type `found` is accepted where `expected` is needed.

    Only the same type, or a refined type widening through its chain of bases,
    is accepted. A base is never accepted where a refined type is expected: that
    needs building the refined value explicitly, a check this model does not
    perform. Constructor arguments are invariant.
    """
    current: Type | None = found
    while current is not None:
        if equal(current, expected):
            return True
        current = widen(current)
    return False


# Substitution and unification

def substitute(kind: Type, mapping: Mapping[int, Type]) -> Type:
    """Every type variable bound in `mapping` replaced by the type it is bound to.

    `mapping` is expected to be acyclic, as `unify` returns it. The result is a
    new type; the input and the mapping are never changed. A cyclic mapping is
    rejected instead of recursing forever.
    """
    return _substitute(kind, mapping, frozenset())


def _substitute(kind: Type, mapping: Mapping[int, Type], seen: frozenset[int]) -> Type:
    if isinstance(kind, TypeVariable):
        if kind.identifier in seen:
            raise ValueError("cyclic substitution")
        replacement = mapping.get(kind.identifier)
        if replacement is None:
            return kind
        return _substitute(replacement, mapping, seen | {kind.identifier})
    if isinstance(kind, Application):
        return Application(
            kind.constructor, tuple(_substitute(argument, mapping, seen) for argument in kind.arguments)
        )
    if isinstance(kind, Refined):
        return Refined(kind.name, _substitute(kind.base, mapping, seen), kind.declaration)
    return kind


def _walk(kind: Type, mapping: Mapping[int, Type]) -> Type:
    """The type at the end of the chain of variables `kind` is bound to."""
    current = kind
    seen: set[int] = set()
    while isinstance(current, TypeVariable) and current.identifier in mapping:
        if current.identifier in seen:
            break
        seen.add(current.identifier)
        current = mapping[current.identifier]
    return current


def _occurs(identifier: int, kind: Type, mapping: Mapping[int, Type]) -> bool:
    """Whether the variable `identifier` appears in `kind`, following `mapping`."""
    kind = _walk(kind, mapping)
    if isinstance(kind, TypeVariable):
        return kind.identifier == identifier
    if isinstance(kind, Application):
        return any(_occurs(identifier, argument, mapping) for argument in kind.arguments)
    if isinstance(kind, Refined):
        return _occurs(identifier, kind.base, mapping)
    return False


def unify(left: Type, right: Type, mapping: Mapping[int, Type] | None = None) -> dict[int, Type] | None:
    """First-order unification of two types.

    Returns a fresh substitution that makes them equal, or None if they cannot
    be unified: different primitives, different constructors or arities, an
    incompatible argument, or a bind that would make a type contain itself.
    `mapping` is existing knowledge; it is never changed.
    """
    return _unify(left, right, dict(mapping or {}))


def _unify(left: Type, right: Type, mapping: dict[int, Type]) -> dict[int, Type] | None:
    left = _walk(left, mapping)
    right = _walk(right, mapping)
    if equal(left, right):
        return mapping
    if isinstance(left, TypeVariable):
        if _occurs(left.identifier, right, mapping):
            return None
        mapping[left.identifier] = right
        return mapping
    if isinstance(right, TypeVariable):
        if _occurs(right.identifier, left, mapping):
            return None
        mapping[right.identifier] = left
        return mapping
    if isinstance(left, Application) and isinstance(right, Application):
        if left.constructor.identity != right.constructor.identity:
            return None
        if left.constructor.arity != right.constructor.arity or len(left.arguments) != len(right.arguments):
            return None
        for argument, other in zip(left.arguments, right.arguments, strict=True):
            if _unify(argument, other, mapping) is None:
                return None
        return mapping
    return None


# Presentation

def display(kind: Type) -> str:
    """The canonical text of a type. It is presentation only: no rule reads it."""
    if isinstance(kind, Primitive):
        return kind.name
    if isinstance(kind, Refined):
        return kind.name
    if isinstance(kind, TypeVariable):
        return kind.name or f"T{kind.identifier}"
    if isinstance(kind, Application):
        if not kind.arguments:
            return kind.constructor.name
        arguments = ", ".join(display(argument) for argument in kind.arguments)
        return f"{kind.constructor.name}[{arguments}]"
    raise TypeError(f"not a type: {kind!r}")


def to_data(kind: Type) -> dict:
    """A plain dictionary for tests and tracing.

    This is NOT a public contract: it appears in no JSON document, it has no
    schema and it may change at any time. `display` is the stable text; this is
    only an internal shape.
    """
    if isinstance(kind, Primitive):
        return {"kind": "primitive", "name": kind.name}
    if isinstance(kind, Refined):
        return {"kind": "refined", "name": kind.name, "base": to_data(kind.base)}
    if isinstance(kind, TypeVariable):
        return {"kind": "type_variable", "identifier": kind.identifier, "name": kind.name}
    if isinstance(kind, Application):
        return {
            "kind": "application",
            "constructor": kind.constructor.name,
            "identity": kind.constructor.identity,
            "arguments": [to_data(argument) for argument in kind.arguments],
        }
    raise TypeError(f"not a type: {kind!r}")


__all__ = [
    "Application",
    "BUILTIN_CONSTRUCTORS",
    "BOOL",
    "Constructor",
    "FLOAT",
    "INT",
    "LIST",
    "OPTION",
    "PRIMITIVE_NAMES",
    "Primitive",
    "RESULT",
    "Refined",
    "TEXT",
    "Type",
    "TypeVariable",
    "VALUE_PRIMITIVE_NAMES",
    "VOID",
    "VOID_NAME",
    "application",
    "assignable",
    "display",
    "equal",
    "is_value_type",
    "is_void",
    "list_of",
    "option_of",
    "result_of",
    "root",
    "substitute",
    "to_data",
    "unify",
    "widen",
]

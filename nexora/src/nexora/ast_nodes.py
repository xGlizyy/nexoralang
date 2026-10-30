"""Abstract syntax tree of a NEXORA program.

Nodes are immutable and carry the span of the source text they came from, so later
stages (and external tools, through `to_dict`) can point back at the code.

The field names of these classes are the field names of the `nex inspect` JSON output,
documented in docs/inspect-schema.md. Renaming or removing one changes that schema.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from .diagnostics import Span


@dataclass(frozen=True)
class Node:
    span: Span


# Expressions

@dataclass(frozen=True)
class IntLiteral(Node):
    value: int


@dataclass(frozen=True)
class FloatLiteral(Node):
    value: float


@dataclass(frozen=True)
class TextLiteral(Node):
    value: str


@dataclass(frozen=True)
class BoolLiteral(Node):
    value: bool


@dataclass(frozen=True)
class ListLiteral(Node):
    """`[a, b]` or `[]`: a list value written in the source."""
    elements: tuple[Expr, ...]


@dataclass(frozen=True)
class Name(Node):
    """A reference to a variable or a parameter (or to `result` inside `promises`, or to `value`
    inside the condition of a refined type)."""
    name: str


@dataclass(frozen=True)
class Unary(Node):
    """`-operand` or `not operand`."""
    operator: str
    operand: Expr


@dataclass(frozen=True)
class Binary(Node):
    """Arithmetic (`+ - * /`), comparison (`== != < <= > >=`) or logic (`and`, `or`)."""
    operator: str
    operator_span: Span
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Group(Node):
    """A parenthesised expression."""
    expression: Expr


@dataclass(frozen=True)
class Call(Node):
    """A call to a function, or `Percent(x)`: the check that turns a value into a refined type.

    In a qualified call such as `Text.length(s)`, `callee` is the whole name ("Text.length"),
    `callee_span` covers it, and `qualifier` is the name before the '.' ("Text"). Otherwise
    `qualifier` is None (decision 0011, 7.4)."""
    callee: str
    callee_span: Span
    arguments: tuple[Expr, ...]
    qualifier: str | None = None


@dataclass(frozen=True)
class FieldInitializer(Node):
    """`x: 1`: the value given to one field of a record."""
    name: str
    name_span: Span
    value: Expr


@dataclass(frozen=True)
class RecordConstruction(Node):
    """`Point(x: 1, y: 2)`: building a record value.

    The fields are in the order they were written, which is not necessarily the order of
    the declaration (decision 0014, 2). A record of another module is written with its
    module in front: `models.Point(x: 1)` (decision 0018, 5)."""
    name: str
    name_span: Span
    fields: tuple[FieldInitializer, ...]
    # Last, so the order of the existing fields stays the same in the inspect schema.
    qualifier: str | None = None


@dataclass(frozen=True)
class FieldAccess(Node):
    """`p.x`: reading a field of a record value.

    `target` is the value the field is read from: a name, or another field access
    (decision 0014, 2)."""
    target: Expr
    name: str
    name_span: Span


@dataclass(frozen=True)
class WildcardPattern(Node):
    """The `_` pattern: matches a value without binding it."""


@dataclass(frozen=True)
class BindingPattern(Node):
    """A lower-case name pattern that binds the matched value."""
    name: str
    name_span: Span


@dataclass(frozen=True)
class VariantPattern(Node):
    """A variant pattern such as `Some(value)` or `Shape.Circle(radius)`."""
    name: str
    name_span: Span
    arguments: tuple[Pattern, ...] = ()
    qualifier: str | None = None


@dataclass(frozen=True)
class LiteralPattern(Node):
    """A literal pattern. Literal coverage is finite only for Bool."""
    value: int | float | str | bool


Pattern = WildcardPattern | BindingPattern | VariantPattern | LiteralPattern


Expr = (IntLiteral | FloatLiteral | TextLiteral | BoolLiteral | ListLiteral | Name | Unary | Binary | Group | Call
        | RecordConstruction | FieldAccess)
EXPRESSION_NODES = (IntLiteral, FloatLiteral, TextLiteral, BoolLiteral, ListLiteral, Name, Unary, Binary, Group,
                    Call, RecordConstruction, FieldAccess)


# Types

@dataclass(frozen=True)
class TypeRef(Node):
    """A type written in the source: `Int`, `Text`, `Percent` or `List[Int]`.

    `arguments` holds the type arguments, in order. It is empty for a name written
    without brackets: `Int` has no arguments and `List[Int]` has one, which is itself
    a `TypeRef`. `qualifier` holds the module a type of another module comes from
    (`models.Point`), or None when the type is written without one.
    """
    name: str
    arguments: tuple[TypeRef, ...] = ()
    qualifier: str | None = None


@dataclass(frozen=True)
class TypeDecl(Node):
    """`type Percent = Int where value >= 0 and value <= 100, "explanation"`: a refined type.

    Its values are the values of `base` for which `condition` is true. Inside the condition,
    `value` names the value being checked.
    """
    name: str
    name_span: Span
    base: TypeRef
    condition: Expr
    # The explanation written after the condition, or None.
    message: str | None
    # True when the declaration is marked with `pub` and can be used from another
    # module (decision 0018, 3). Last, so the order of the existing fields stays.
    public: bool = False


@dataclass(frozen=True)
class FieldDecl(Node):
    """`x: Int`: one field of a record declaration."""
    name: str
    name_span: Span
    type: TypeRef


@dataclass(frozen=True)
class RecordDecl(Node):
    """`type Point = { x: Int, y: Int }`: a record type declared by the user.

    Its values are built with `RecordConstruction` and cannot be changed afterwards
    (decision 0014, 1).
    """
    name: str
    name_span: Span
    fields: tuple[FieldDecl, ...]
    # True when the declaration is marked with `pub` and can be used from another
    # module (decision 0018, 3). Last, so the order of the existing fields stays.
    public: bool = False


@dataclass(frozen=True)
class EnumVariantDecl(Node):
    """One constructor of a closed enum, with named payload fields."""
    name: str
    name_span: Span
    fields: tuple[FieldDecl, ...] = ()


@dataclass(frozen=True)
class EnumDecl(Node):
    """`type Shape = enum { Circle(radius: Float), Square }`."""
    name: str
    name_span: Span
    variants: tuple[EnumVariantDecl, ...]
    public: bool = False


@dataclass(frozen=True)
class UsesDecl(Node):
    """`uses read "ruta"`: the capability a program declares that it needs.

    Declaring a capability does not grant it: the user has to allow it too, and the
    environment has to permit it (decision 0015, 2 and 3).
    """
    capability: str
    path: str
    path_span: Span


@dataclass(frozen=True)
class ImportDecl(Node):
    """`import "ruta/fichero.nex"`: the module the program imports (decision 0018).

    The path is relative to the file that imports it. The module is bound to a
    namespace named after the file, without its extension.
    """
    path: str
    path_span: Span


# Statements

@dataclass(frozen=True)
class Let(Node):
    name: str
    name_span: Span
    declared_type: TypeRef | None
    value: Expr


@dataclass(frozen=True)
class Var(Node):
    """`var name = value`: a variable whose value can be changed later with an assignment."""
    name: str
    name_span: Span
    declared_type: TypeRef | None
    value: Expr


@dataclass(frozen=True)
class Assign(Node):
    """`name = value`: gives a new value to a variable declared with `var`."""
    name: str
    name_span: Span
    value: Expr


@dataclass(frozen=True)
class FieldAssign(Node):
    """`p.x = value`: gives a new value to a field of a record.

    A record is immutable, so this is always an error (decision 0014, 2). `target` is
    the value the field belongs to, and `name` the field that would change."""
    target: Expr
    name: str
    name_span: Span
    value: Expr


@dataclass(frozen=True)
class Return(Node):
    value: Expr | None


@dataclass(frozen=True)
class If(Node):
    condition: Expr
    then_block: Block
    # A Block for `else { ... }`, another If for `else if ...`, or None.
    else_branch: Block | If | IfLet | None


@dataclass(frozen=True)
class IfLet(Node):
    """`if let pattern = value { ... } else { ... }`."""
    pattern: Pattern
    value: Expr
    then_block: Block
    else_branch: Block | If | IfLet | None


@dataclass(frozen=True)
class ExprStatement(Node):
    expression: Expr


@dataclass(frozen=True)
class Block(Node):
    """`{ ... }`. A block opens a new scope; it is also a statement."""
    statements: tuple[Statement, ...]


@dataclass(frozen=True)
class LoopClause(Node):
    """A `keeps` or `shrinks` clause in the header of a loop, between its head and its body
    (decisions 0010 and 0019)."""
    # "keeps" or "shrinks". Not called 'kind': that is the name of the node type in the JSON form.
    clause: str
    # The name written before ':', or None. It is not a variable: no expression can use it.
    name: str | None
    # A Bool for 'keeps'; the Int measure for 'shrinks'.
    condition: Expr
    # The explanation written after the condition, or None.
    message: str | None


@dataclass(frozen=True)
class While(Node):
    """`while condition clauses { statements }`. Every loop declares one `shrinks` measure, checked
    on every turn, and any number of `keeps` (decisions 0010 and 0019)."""
    condition: Expr
    clauses: tuple[LoopClause, ...]
    body: Block


@dataclass(frozen=True)
class For(Node):
    """`for name in iterable clauses { statements }`. Iterates over a `List[T]`; the iterator is a
    new immutable name in every turn, and the loop may declare `keeps` but not `shrinks`
    (decisions 0012 and 0019)."""
    name: str
    name_span: Span
    iterable: Expr
    clauses: tuple[LoopClause, ...]
    body: Block


Statement = Let | Var | Assign | FieldAssign | Return | If | IfLet | While | For | ExprStatement | Block


@dataclass(frozen=True)
class MatchArm(Node):
    pattern: Pattern
    body: Expr | Block


@dataclass(frozen=True)
class MatchExpr(Node):
    """An exhaustive value match over a closed enum or Bool."""
    value: Expr
    arms: tuple[MatchArm, ...]


Expr = Expr | MatchExpr
EXPRESSION_NODES = (*EXPRESSION_NODES, MatchExpr)


# Declarations

@dataclass(frozen=True)
class Param(Node):
    name: str
    name_span: Span
    type: TypeRef


@dataclass(frozen=True)
class Contract(Node):
    """A `needs`, `promises` or `trust` clause in the header of a function (decision 0019)."""
    # "needs", "promises" or "trust". Not called 'kind': that is the name of the node type in the
    # JSON form.
    clause: str
    # The name written before ':', or None. It is not a variable: no expression can use it.
    name: str | None
    condition: Expr
    # The explanation written after the condition, or None. A 'trust' always has one.
    message: str | None


@dataclass(frozen=True)
class Example(Node):
    """An `example` clause in the header of a function: a Bool expression that calls the function
    with concrete inputs. Only `nex test` evaluates it; the analysis never does."""
    condition: Expr
    # The explanation written after the condition, or None.
    message: str | None


@dataclass(frozen=True)
class Function(Node):
    name: str
    name_span: Span
    params: tuple[Param, ...]
    # The type after 'gives', or None for a function that gives nothing (decision 0019).
    return_type: TypeRef | None
    # The clauses between the signature and the body, in the order they are written: the order
    # is part of the program (decision 0019, 8.4.1).
    header: tuple[Contract | Example, ...]
    body: Block
    # True when the function is marked with `pub` and can be called from another
    # module (decision 0018, 3).
    public: bool = False

    @property
    def contracts(self) -> tuple[Contract, ...]:
        """The `needs`, `promises` and `trust` of the header, in order."""
        return tuple(item for item in self.header if isinstance(item, Contract))

    @property
    def examples(self) -> tuple[Example, ...]:
        """The `example` clauses of the header, in order."""
        return tuple(item for item in self.header if isinstance(item, Example))


@dataclass(frozen=True)
class Program(Node):
    types: tuple[TypeDecl, ...]
    functions: tuple[Function, ...]
    # The record types the program declares, after the functions: a new field goes at
    # the end, so the order of the existing ones does not change (docs/inspect-schema.md).
    records: tuple[RecordDecl, ...] = ()
    # The capabilities the program declares it needs, after the records (decision 0015).
    uses: tuple[UsesDecl, ...] = ()
    # The modules the program imports, after the capabilities (decision 0018).
    imports: tuple[ImportDecl, ...] = ()
    # User-defined closed enums. Appended to preserve the positional form of earlier fields.
    enums: tuple[EnumDecl, ...] = ()


def to_dict(node, types: dict[int, str] | None = None):
    """Plain dictionaries and lists for a node, ready for `json.dumps`.

    `types` maps `id(expression node)` to the type the checker computed for it. When given,
    every expression gets a "type" field (null if the checker could not determine it).
    """
    if isinstance(node, Span):
        return {
            "line": node.line,
            "column": node.column,
            "end_line": node.end_line,
            "end_column": node.end_column,
        }
    if isinstance(node, Node):
        result = {"kind": type(node).__name__}
        for field in fields(node):
            result[field.name] = to_dict(getattr(node, field.name), types)
        if types is not None and isinstance(node, EXPRESSION_NODES):
            result["type"] = types.get(id(node))
        return result
    if isinstance(node, tuple):
        return [to_dict(item, types) for item in node]
    return node

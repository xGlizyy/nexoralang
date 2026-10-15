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
class Name(Node):
    """A reference to a variable or a parameter (or to `result` inside `ensures`, or to `value`
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


Expr = IntLiteral | FloatLiteral | TextLiteral | BoolLiteral | Name | Unary | Binary | Group | Call
EXPRESSION_NODES = (IntLiteral, FloatLiteral, TextLiteral, BoolLiteral, Name, Unary, Binary, Group, Call)


# Types

@dataclass(frozen=True)
class TypeRef(Node):
    """A type written in the source: `Int`, `Text`, `Percent`..."""
    name: str


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
class Return(Node):
    value: Expr | None


@dataclass(frozen=True)
class If(Node):
    condition: Expr
    then_block: Block
    # A Block for `else { ... }`, another If for `else if ...`, or None.
    else_branch: Block | If | None


@dataclass(frozen=True)
class ExprStatement(Node):
    expression: Expr


@dataclass(frozen=True)
class Block(Node):
    """`{ ... }`. A block opens a new scope; it is also a statement."""
    statements: tuple[Statement, ...]


@dataclass(frozen=True)
class LoopClause(Node):
    """An `invariant` or `decreases` clause at the start of the body of a `while` (decision 0010)."""
    # "invariant" or "decreases". Not called 'kind': that is the name of the node type in the JSON form.
    clause: str
    # A Bool for 'invariant'; the Int measure for 'decreases'.
    condition: Expr
    # The explanation written after the condition, or None.
    message: str | None


@dataclass(frozen=True)
class While(Node):
    """`while condition { clauses statements }`. Every loop declares one `decreases` measure, checked
    on every turn, and any number of invariants (decision 0010)."""
    condition: Expr
    clauses: tuple[LoopClause, ...]
    body: Block


Statement = Let | Var | Assign | Return | If | While | ExprStatement | Block


# Declarations

@dataclass(frozen=True)
class Param(Node):
    name: str
    name_span: Span
    type: TypeRef


@dataclass(frozen=True)
class Contract(Node):
    """A `requires` or `ensures` clause at the start of a function body."""
    # "requires" or "ensures". Not called 'kind': that is the name of the node type in the JSON form.
    clause: str
    condition: Expr
    # The explanation written after the condition, or None.
    message: str | None


@dataclass(frozen=True)
class Example(Node):
    """An `example` clause at the start of a function body: a Bool expression that calls the
    function with concrete inputs. Only `nex test` evaluates it; the analysis never does."""
    condition: Expr
    # The explanation written after the condition, or None.
    message: str | None


@dataclass(frozen=True)
class Function(Node):
    name: str
    name_span: Span
    params: tuple[Param, ...]
    return_type: TypeRef
    contracts: tuple[Contract, ...]
    body: Block
    # Last, after body: in the `nex inspect` JSON a new field is only ever added at the end, so the
    # order of the existing fields stays the same (docs/inspect-schema.md).
    examples: tuple[Example, ...] = ()


@dataclass(frozen=True)
class Program(Node):
    types: tuple[TypeDecl, ...]
    functions: tuple[Function, ...]


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

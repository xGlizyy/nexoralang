"""Static analysis: names, scopes and types, checked without running the program.

This module is the single place where the typing rules of NEXORA live. The interpreter
does not repeat them: it only runs programs that passed this stage (a `CheckedProgram`).
`nex check` stops after this stage.

Every expression has a type that follows from literals, annotations and signatures, so
nothing about types is left to run time. What cannot be known statically (division by
zero, overflow, the truth of a contract) is listed in docs/language-spec.md, section 10.

Refined types (`type Percent = Int where ...`) keep one guarantee: every value whose static
type is a refined type satisfies its condition. A value only gets such a type in two ways:
a constant that this module checks while analysing (E2017), or the explicit check `Percent(x)`,
which the interpreter performs when it runs (E4003). Widening is free: a Percent can be used
wherever an Int is expected.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field, fields

from . import ast_nodes as ast
from . import types as type_model
from .capabilities import NETWORK, PROCESS, READ, WRITE, Capabilities
from .diagnostics import ERROR, MAX_DIAGNOSTICS, WARNING, Diagnostic, NexoraRuntimeError, Span
from .type_adapter import TypeAdapter
from .values import BOOL, FLOAT, INT, NONE, TEXT, VALUE_TYPES, VOID

KNOWN_TYPES = (VOID, *VALUE_TYPES)

# Parameter "type" of the built-in functions that accept a value of any type.
ANY_VALUE = "Int | Float | Bool | Text"

# The most work the analysis may spend checking constants against refined types, counted as the
# nodes of the conditions it evaluates. Checking one constant costs the size of every condition in
# its type's chain, so without a bound the work would grow with types x conditions x constants.
# Ordinary programs stay far below it; a program above it is rejected (E2019), never half-checked.
MAX_REFINEMENT_STEPS = 100_000

# Built-ins that need a declared host capability.
CAPABILITY_FUNCTIONS = {
    "read_file": READ,
    "write_file": WRITE,
    "Net.get": NETWORK,
    "Process.run": PROCESS,
}

ARITHMETIC = ("+", "-", "*", "/")
EQUALITY = ("==", "!=")
ORDERING = ("<", "<=", ">", ">=")
LOGICAL = ("and", "or")

# How many type arguments each built-in type with arguments takes.
_TYPE_ARGUMENT_COUNTS = {"List": 1, "Option": 1, "Result": 2}

# The naming convention of every value name: variables, parameters, iterators and the
# functions that are not part of a public interface. Types keep their own convention
# (PascalCase), and the names of the standard library are not checked.
_SNAKE_CASE = re.compile(r"^_?[a-z][a-z0-9_]*$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_NOT_A_NAME_CHARACTER = re.compile(r"[^A-Za-z0-9]+")

# The identity of every record declaration of the process: nothing but this counter
# tells two declarations apart, not their name nor their fields (decision 0014, 3).
_IDENTITY = 0


def _next_identity() -> int:
    """A number that no other record declaration of this process has."""
    global _IDENTITY
    _IDENTITY += 1
    return _IDENTITY


def _snake_case(name: str) -> str:
    """The snake_case spelling suggested for `name` (which is not snake_case)."""
    prefix = "_" if name.startswith("_") else ""
    body = name[1:] if prefix else name
    body = _CAMEL_BOUNDARY.sub("_", body)
    body = _ACRONYM_BOUNDARY.sub("_", body)
    body = _NOT_A_NAME_CHARACTER.sub("_", body)
    body = re.sub(r"_+", "_", body).strip("_").lower()
    return prefix + (body or "value")


@dataclass(frozen=True)
class ParametricSignature:
    """The internal type of a built-in whose parameters or result mention a type variable.

    The language cannot write generic functions yet (D03); this is only how the
    built-ins of `List` state that every element has the same type. Each call
    instantiates the variables with the types of its arguments through `unify`
    (D01.5), and the signature object itself is never changed.
    """

    params: tuple[tuple[str, type_model.Type], ...]
    return_type: type_model.Type


@dataclass(frozen=True)
class Signature:
    """What a call needs to know about a function. A type is None when it was written wrong
    in the declaration; calls then skip the checks that depend on it."""

    name: str
    params: tuple[tuple[str, str | None], ...]
    return_type: str | None
    builtin: bool = False
    # Present only for a built-in whose types contain type variables, such as List.length.
    parametric: ParametricSignature | None = None

    def describe(self) -> str:
        params = ", ".join(f"{name}: {kind or '?'}" for name, kind in self.params)
        if self.return_type == VOID:
            return f"fn {self.name}({params})"
        return f"fn {self.name}({params}) gives {self.return_type or '?'}"


# The item variable shared by the signatures of the functions of List. `unify` returns a
# fresh mapping for each call, so the same variable can be reused without keeping state.
_LIST_ITEM = type_model.TypeVariable(0, "T")

# The type variables of the constructors of Option and Result. Each call gets a fresh
# unification mapping, so the same identifier can be reused in several signatures.
_OPTION_ITEM = type_model.TypeVariable(0, "T")
_RESULT_ITEM = type_model.TypeVariable(0, "T")
_RESULT_ERROR = type_model.TypeVariable(1, "E")

# What a call cannot infer by itself, and how to say it. A type the context expects can always
# give the answer; without one, the program has to write the type down.
_UNINFERABLE = {
    "Ok": ("Cannot infer the error type of this Result",
           "Write the type of the result explicitly, for example: let r: Result[Int, Text] = Ok(1)."),
    "Err": ("Cannot infer the item type of this Result",
            "Write the type of the result explicitly, for example: let r: Result[Int, Text] = Err(\"boom\")."),
}


def _parametric_signature(name: str, params: tuple[tuple[str, type_model.Type], ...],
                          return_type: type_model.Type) -> Signature:
    """A built-in signature that also carries its structured parametric type."""
    parametric = ParametricSignature(params, return_type)
    shown = tuple((param_name, type_model.display(kind)) for param_name, kind in params)
    return Signature(name, shown, type_model.display(return_type), builtin=True, parametric=parametric)


# The built-in functions. These are the only conversions between types: nothing converts implicitly.
# Those whose name has a '.' belong to a type and are called with its name, as in Text.length(s)
# (decision 0011). Their contracts and implementations are in prelude.py.
BUILTINS: dict[str, Signature] = {
    signature.name: signature
    for signature in (
        Signature("print", (("value", ANY_VALUE),), VOID, builtin=True),
        Signature("to_text", (("value", ANY_VALUE),), TEXT, builtin=True),
        Signature("to_float", (("value", INT),), FLOAT, builtin=True),
        Signature("to_int", (("value", FLOAT),), INT, builtin=True),
        # The input and the files (decision 0015). The arguments and the standard
        # input need no declaration; the files do.
        Signature("args", (), "List[Text]", builtin=True),
        Signature("input", (), TEXT, builtin=True),
        Signature("read_file", (("path", TEXT),), TEXT, builtin=True),
        Signature("write_file", (("path", TEXT), ("text", TEXT)), VOID, builtin=True),
        Signature("Net.get", (("url", TEXT),), TEXT, builtin=True),
        _parametric_signature(
            "Process.run", (("command", type_model.TEXT), ("arguments", type_model.list_of(type_model.TEXT))),
            type_model.TEXT,
        ),
        Signature("Text.length", (("text", TEXT),), INT, builtin=True),
        Signature("Text.slice", (("text", TEXT), ("start", INT), ("end", INT)), TEXT, builtin=True),
        Signature("Text.contains", (("text", TEXT), ("part", TEXT)), BOOL, builtin=True),
        Signature("Text.starts_with", (("text", TEXT), ("part", TEXT)), BOOL, builtin=True),
        Signature("Text.ends_with", (("text", TEXT), ("part", TEXT)), BOOL, builtin=True),
        Signature("Int.can_parse", (("text", TEXT),), BOOL, builtin=True),
        Signature("Int.parse", (("text", TEXT),), INT, builtin=True),
        Signature("Float.can_parse", (("text", TEXT),), BOOL, builtin=True),
        Signature("Float.parse", (("text", TEXT),), FLOAT, builtin=True),
        # The essential functions of List (D08/D.2.1). `List.get` is partial and declares
        # its precondition in prelude.py; the rest are total.
        _parametric_signature(
            "List.length", (("xs", type_model.list_of(_LIST_ITEM)),), type_model.INT,
        ),
        _parametric_signature(
            "List.get", (("xs", type_model.list_of(_LIST_ITEM)), ("i", type_model.INT)), _LIST_ITEM,
        ),
        _parametric_signature(
            "List.append", (("xs", type_model.list_of(_LIST_ITEM)), ("x", _LIST_ITEM)),
            type_model.list_of(_LIST_ITEM),
        ),
        _parametric_signature(
            "List.concat",
            (("xs", type_model.list_of(_LIST_ITEM)), ("ys", type_model.list_of(_LIST_ITEM))),
            type_model.list_of(_LIST_ITEM),
        ),
        _parametric_signature(
            "List.contains", (("xs", type_model.list_of(_LIST_ITEM)), ("x", _LIST_ITEM)), type_model.BOOL,
        ),
        # The constructors of Option and Result. The type of the payload comes from the
        # argument; the other one comes from the type the context expects: the error type of
        # an Ok, the item type of an Err.
        _parametric_signature(
            "Some", (("value", _OPTION_ITEM),), type_model.option_of(_OPTION_ITEM),
        ),
        _parametric_signature(
            "Ok", (("value", _RESULT_ITEM),), type_model.result_of(_RESULT_ITEM, _RESULT_ERROR),
        ),
        _parametric_signature(
            "Err", (("error", _RESULT_ERROR),), type_model.result_of(_RESULT_ITEM, _RESULT_ERROR),
        ),
        # The inspection of an Option and a Result. The variants are told apart without
        # exceptions, and the payload is only read when there is one.
        _parametric_signature(
            "Option.is_some", (("value", type_model.option_of(_OPTION_ITEM)),), type_model.BOOL,
        ),
        _parametric_signature(
            "Option.is_none", (("value", type_model.option_of(_OPTION_ITEM)),), type_model.BOOL,
        ),
        _parametric_signature(
            "Option.value_or",
            (("value", type_model.option_of(_OPTION_ITEM)), ("fallback", _OPTION_ITEM)),
            _OPTION_ITEM,
        ),
        _parametric_signature(
            "Option.value", (("value", type_model.option_of(_OPTION_ITEM)),), _OPTION_ITEM,
        ),
        _parametric_signature(
            "Result.is_ok", (("value", type_model.result_of(_RESULT_ITEM, _RESULT_ERROR)),), type_model.BOOL,
        ),
        _parametric_signature(
            "Result.is_err", (("value", type_model.result_of(_RESULT_ITEM, _RESULT_ERROR)),), type_model.BOOL,
        ),
        _parametric_signature(
            "Result.value_or",
            (("value", type_model.result_of(_RESULT_ITEM, _RESULT_ERROR)), ("fallback", _RESULT_ITEM)),
            _RESULT_ITEM,
        ),
        _parametric_signature(
            "Result.value", (("value", type_model.result_of(_RESULT_ITEM, _RESULT_ERROR)),), _RESULT_ITEM,
        ),
        _parametric_signature(
            "Result.error", (("value", type_model.result_of(_RESULT_ITEM, _RESULT_ERROR)),), _RESULT_ERROR,
        ),
    )
}

# The functions of each built-in type, by type: {"Text": ["contains", ...], ...}.
TYPE_FUNCTIONS: dict[str, list[str]] = {}
for _name in sorted(BUILTINS):
    if "." in _name and _name not in CAPABILITY_FUNCTIONS:
        _type, _function = _name.split(".")
        TYPE_FUNCTIONS.setdefault(_type, []).append(_function)


@dataclass
class Symbol:
    """A name the program declares, and every place where the checker resolved a use of it."""

    name: str
    category: str                 # "function", "parameter" or "variable"
    type: str | None              # its type; for a function, its return type. None if written wrong
    span: Span                    # where the name is declared
    function: str | None          # the function it belongs to (None for a function itself)
    scope: Span | None            # the block where it is visible (None for a function: the whole file)
    references: list[Span] = field(default_factory=list)
    # The module where each reference is written, parallel to `references`. A symbol may
    # be declared in one module and referenced from several importing modules.
    reference_modules: list[str | None] = field(default_factory=list)
    # The references that read the value. A reference that gives it a new value is in
    # `references` and in `assignments`, but not here.
    reads: list[Span] = field(default_factory=list)
    # True only for a variable declared with 'var'.
    mutable: bool = False
    # True for the iterator a 'for' loop declares: it is immutable for its own reason.
    loop_variable: bool = False
    # Where the variable is given a new value. Each of these is also in `references`.
    assignments: list[Span] = field(default_factory=list)
    # The module that declares the name, or None for the file that runs: a name of a
    # module belongs to that file, and only its position says where it is (decision 0018).
    module: str | None = None


@dataclass(frozen=True)
class RefinedType:
    """A declared refined type, once its base has been resolved."""

    name: str
    declaration: ast.TypeDecl
    base: str      # the type it refines: a built-in type or another refined type
    root: str      # the built-in type at the end of the chain of bases
    # The declarations whose conditions a value must satisfy, from the root outwards: for
    # `type Small = Positive where ...` it is (Positive, Small).
    chain: tuple[ast.TypeDecl, ...]

    @property
    def cost(self) -> int:
        """The number of condition nodes evaluated to check one value."""
        return sum(_size(declaration.condition) for declaration in self.chain)


def _size(node: ast.Expr) -> int:
    """The number of nodes of an expression."""
    if isinstance(node, ast.Binary):
        return 1 + _size(node.left) + _size(node.right)
    if isinstance(node, ast.Unary):
        return 1 + _size(node.operand)
    if isinstance(node, ast.Group):
        return 1 + _size(node.expression)
    if isinstance(node, ast.Call):
        return 1 + sum(_size(argument) for argument in node.arguments)
    if isinstance(node, ast.ListLiteral):
        return 1 + sum(_size(element) for element in node.elements)
    return 1


def _contains_type_variable(kind: type_model.Type) -> bool:
    """Whether `kind` still mentions a type variable that a call has not bound."""
    if isinstance(kind, type_model.TypeVariable):
        return True
    if isinstance(kind, type_model.Application):
        return any(_contains_type_variable(argument) for argument in kind.arguments)
    if isinstance(kind, type_model.Refined):
        return _contains_type_variable(kind.base)
    return False


@dataclass(frozen=True)
class CheckedProgram:
    """What the checker learned about a program. It may only be run when it has no diagnostics."""

    program: ast.Program
    functions: dict[str, ast.Function]
    # id(expression node) -> its type.
    types: dict[int, str]
    # Every function, parameter and variable, in order of declaration.
    symbols: tuple[Symbol, ...] = ()
    # (caller, callee) for every call found, in source order. The callee may be a built-in.
    calls: tuple[tuple[str, str], ...] = ()
    # The refined types whose declaration is valid, by name.
    refined: dict[str, RefinedType] = field(default_factory=dict)
    # The record types whose declaration is valid, by name. The interpreter reads the
    # identity from here: it never rebuilds it from the name (decision 0014, 3).
    records: dict[str, RecordType] = field(default_factory=dict)
    # The capabilities the program declares it needs (decision 0015, 2).
    capabilities: Capabilities = field(default_factory=Capabilities)
    # id(node) -> the name the analysis resolved it to, qualified with its module: a call,
    # a refinement check or a construction of a record. Each of them is written inside a
    # module with the bare name, and the module is what tells it apart from the same name
    # in another module (decision 0018, 5): the interpreter looks them up with this,
    # never with the text.
    targets: dict[int, str] = field(default_factory=dict)
    # The closed enum declarations and their resolved variant payloads.
    enums: dict[str, EnumType] = field(default_factory=dict)


@dataclass(frozen=True)
class RecordType:
    """A record type whose declaration is valid.

    `fields` holds the name and the type of every field, in declaration order, and
    `identity` is what tells this declaration from any other one.
    """

    name: str
    declaration: ast.RecordDecl
    fields: tuple[tuple[str, str], ...]
    identity: type_model.RecordIdentity
    nominal: type_model.Nominal

    def field_type(self, name: str) -> str | None:
        """The type of the field `name`, or None if the record has no such field."""
        for field_name, kind in self.fields:
            if field_name == name:
                return kind
        return None


@dataclass(frozen=True)
class EnumVariantType:
    name: str
    fields: tuple[tuple[str, str], ...]
    declaration: ast.EnumVariantDecl


@dataclass(frozen=True)
class EnumType:
    name: str
    declaration: ast.EnumDecl
    variants: tuple[EnumVariantType, ...]
    identity: type_model.RecordIdentity


def binary_result(operator: str, left: str, right: str) -> str | None:
    """The type of `left operator right`, or None if the operation is not defined.

    Both operands always have the same type: nothing is converted implicitly.
    """
    if left != right or left not in VALUE_TYPES:
        return None
    if operator in LOGICAL:
        return BOOL if left == BOOL else None
    if operator in EQUALITY:
        return BOOL
    if operator in ORDERING:
        # Two texts are ordered by code point, character by character (decision 0011, section 2).
        return BOOL if left in (INT, FLOAT, TEXT) else None
    if left in (INT, FLOAT):
        return left
    if left == TEXT and operator == "+":
        return TEXT
    return None


def _binary_hint(operator: str, left: str, right: str) -> str | None:
    if VOID in (left, right):
        return "A call to a Void function does not produce a value."
    if operator in LOGICAL:
        return f"'{operator}' combines two Bool values."
    if {left, right} == {INT, FLOAT}:
        return "Int and Float are never mixed. Convert one side: to_float(x) turns an Int into a Float."
    if operator in EQUALITY:
        return f"Both sides of '{operator}' must have the same type."
    if operator in ORDERING:
        if TEXT in (left, right) and {left, right} <= {TEXT, INT, FLOAT}:
            return (f"'{operator}' compares two values of the same type. Convert one side: to_text(...) "
                    "turns a number into a Text, and Int.parse(...) reads an Int from a Text.")
        return f"'{operator}' compares two Int values, two Float values or two Text values."
    if operator == "+" and TEXT in (left, right):
        return "'+' joins Text with Text. Convert the other side with to_text(...)."
    if left == right == TEXT:
        return "The only arithmetic operator defined for Text is '+', which joins two texts."
    if BOOL in (left, right):
        return "Arithmetic works on numbers. Bool values are combined with 'and', 'or' and 'not'."
    return None


def _conversion_hint(found: str, expected: str) -> str | None:
    """A conversion that would make `found` acceptable where `expected` is needed, if one exists."""
    if found == INT and expected == FLOAT:
        return "Convert the Int explicitly with to_float(...)."
    if found == FLOAT and expected == INT:
        return "Convert the Float explicitly with to_int(...), which drops the fractional part."
    if expected == TEXT and found in VALUE_TYPES:
        return "Convert the value explicitly with to_text(...)."
    return None


def own_calls(example: ast.Example, function: str) -> list[ast.Call]:
    """The calls to `function` written in the expression of `example`, in the order they start in the
    text (decision 0008, 1.4). Calls made while running other functions are not in the expression,
    so they are never counted: this looks at the tree, it does not run anything."""
    found: list[ast.Call] = []

    def walk(node) -> None:
        if isinstance(node, ast.Call) and node.callee == function:
            found.append(node)
        if isinstance(node, ast.Node):
            for field in fields(node):
                walk(getattr(node, field.name))
        elif isinstance(node, tuple):
            for item in node:
                walk(item)

    walk(example.condition)
    return sorted(found, key=lambda call: (call.span.line, call.span.column))


def refinement_notes(kind: str, broken: ast.TypeDecl, written: str) -> tuple[str, ...]:
    """The notes that explain why a value is not a valid `kind`: which condition is false, and why
    it exists. `broken` is the declaration whose condition failed: `kind` itself or one it refines."""
    from .interpreter import unparse   # the interpreter depends on this module

    condition = f"where {unparse(broken.condition)}"
    if broken.name == kind:
        notes = [f"The condition of '{kind}' is false: {condition}"]
    else:
        notes = [f"'{kind}' refines '{broken.name}', and the condition of '{broken.name}' is false: {condition}"]
    notes.append(f"The value: {written}")
    if broken.message is not None:
        notes.append(f"Reason: {broken.message}")
    return tuple(notes)


class _TooManyErrors(Exception):
    """Raised to abandon the analysis when MAX_DIAGNOSTICS errors have been collected."""


class _Scope:
    def __init__(self, parent: _Scope | None = None) -> None:
        self.parent = parent
        self.names: dict[str, Symbol] = {}
        # The block this scope belongs to; set when the block is entered.
        self.span: Span | None = None

    def find(self, name: str) -> Symbol | None:
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None

    def visible(self) -> list[str]:
        names: list[str] = []
        scope: _Scope | None = self
        while scope is not None:
            names.extend(scope.names)
            scope = scope.parent
        return names


class Checker:
    def __init__(self, prefix: str = "", modules: tuple[str, ...] = ()) -> None:
        # The module being checked, with its dot. The names it declares are qualified
        # with it, so two modules can declare the same name without the analysis
        # confusing them (decision 0018, 5). It is set for each module before that
        # module is checked; the module the program runs has no prefix.
        self.prefix = prefix
        self._diagnostics: list[Diagnostic] = []
        self._signatures: dict[str, Signature] = {}
        self._types: dict[int, str] = {}
        self._symbols: list[Symbol] = []
        self._function_symbols: dict[str, Symbol] = {}
        self._calls: list[tuple[str, str]] = []
        # id(node) -> the name the analysis resolved it to, qualified with its module: a
        # call, a refinement check or a construction of a record (decision 0018, 5).
        self._targets: dict[int, str] = {}
        # Every declared type name, including those whose declaration has an error.
        self._type_names: dict[str, ast.TypeDecl] = {}
        self._refined: dict[str, RefinedType] = {}
        # The record types the program declares, and the ones that are valid.
        self._record_names: dict[str, ast.RecordDecl] = {}
        self._records: dict[str, RecordType] = {}
        self._enum_names: dict[str, ast.EnumDecl] = {}
        self._enums: dict[str, EnumType] = {}
        # The capabilities the program declares that it needs (decision 0015, 2).
        self._capabilities = Capabilities()
        # The fields of each record, by name, once their types are resolved.
        self._record_fields: dict[str, tuple[tuple[str, str], ...]] = {}
        # The type each field was written with, to know what it depends on.
        self._record_refs: dict[str, tuple[tuple[str, ast.TypeRef], ...]] = {}
        # The records that cannot contain themselves.
        self._cyclic_records: set[str] = set()
        # The identity of each record declaration, in the order they were declared.
        self._record_identities: dict[str, type_model.RecordIdentity] = {}
        # Phase A of D01: a model object beside every valid string type. `_root`
        # uses it for representable names; the other rules still decide with strings.
        self._type_adapter = TypeAdapter()
        # Every function name the program declares, known before any condition is checked.
        self._function_names: set[str] = set()
        # Work spent so far checking constants (see MAX_REFINEMENT_STEPS); None once over the limit.
        self._refinement_steps: int | None = 0
        # The function being checked.
        self._function_name = ""
        self._return_type: str | None = None
        # The refined type whose condition is being checked, if any.
        self._refining: str | None = None
        # The function whose 'example' clause is being checked, if any.
        self._in_example: str | None = None
        # `nex test` analyses programs without 'main' (decision 0008); every other command needs one.
        self.require_main = True
        # The names a module declares with `pub`, which another module can use
        # (decision 0018, 3). They are qualified with the module that declares them.
        self._public: set[str] = set()
        # The names of the modules the program imports, so an unknown module can be
        # reported with the ones that do exist (decision 0018, 2).
        self._modules: tuple[str, ...] = modules

    def _key(self, name: str) -> str:
        """The key a name has in the tables of the analysis.

        A name written with a dot is already qualified: it names something of
        another module (decision 0018, 2). Any other name belongs to the module
        being checked, and is qualified with it.
        """
        if "." in name:
            return name
        return self.prefix + name

    @property
    def _module(self) -> str | None:
        """The module the names being declared belong to, or None for the file that runs."""
        return self.prefix.removesuffix(".") or None

    def _is_public(self, name: str) -> bool:
        """Whether a name can be used from the code being checked (decision 0018, 3).

        A name of the module being checked is always usable, whether it is marked
        with `pub` or not. A name of another module is only usable when that module
        declares it with `pub`.
        """
        key = self._key(name)
        if "." not in key:
            # A name of the module being checked: `pub` only decides what leaves it.
            return True
        module = key.partition(".")[0]
        if f"{module}." == self.prefix:
            return True
        return key in self._public

    def _type_key(self, reference: ast.TypeRef) -> str:
        """The key a type reference has in the tables, qualified with its module."""
        if reference.qualifier is not None:
            return f"{reference.qualifier}.{reference.name}"
        return self._key(reference.name)

    def _qualified(self, name: str, qualifier: str | None) -> str:
        """The key of a name written with an optional module in front."""
        if qualifier is not None:
            return f"{qualifier}.{name}"
        return self._key(name)

    def _unknown_module(self, qualifier: str, span: Span | None) -> None:
        """Reports the use of a module the program does not import (decision 0018, 2)."""
        if self._modules:
            close = difflib.get_close_matches(qualifier, self._modules, n=1)
            hint = ((f"Did you mean '{close[0]}'? " if close else "")
                    + f"The modules this program imports are: {', '.join(self._modules)}.")
        else:
            hint = ('This program imports no modules. Declare one at the top of the file: '
                    'import "app/models.nex"')
        self._report("E2027", f"There is no module named '{qualifier}'", span, hint=hint)

    def _unknown_record(self, qualifier: str, name: str, span: Span | None) -> None:
        """`models.Record(...)` where that module declares no record with that name."""
        if qualifier not in self._modules:
            self._unknown_module(qualifier, span)
            return
        public = sorted(key.partition(".")[2] for key in self._record_names
                        if key.startswith(f"{qualifier}.") and key in self._public)
        close = difflib.get_close_matches(name, public, n=1)
        notes = (f"The records '{qualifier}' makes public: {', '.join(public)}.",) if public else ()
        self._report(
            "E2023",
            f"The module '{qualifier}' has no record named '{name}'",
            span,
            hint=f"Did you mean '{qualifier}.{close[0]}'?" if close else None,
            notes=notes,
        )

    def _visible(self, table: dict) -> list[str]:
        """The names of `table` as a person sees them: the names of this module without
        its prefix, and the names of the other modules qualified."""
        return [key[len(self.prefix):] if self.prefix and key.startswith(self.prefix) else key
                for key in table]

    def _private(self, name: str, span: Span | None) -> None:
        """Reports the use of a name that another module does not make public."""
        module, _, own = name.partition(".")
        self._report(
            "E2028",
            f"'{name}' is private: the module '{module}' does not declare it with 'pub'",
            span,
            hint=f"Mark it in {module}.nex: pub fn {own}(...) or "
                 f"pub type {own[:1].upper()}{own[1:]} = ...",
        )

    def check(self, program: ast.Program,
              declared: dict[str, ast.Function] | None = None) -> tuple[CheckedProgram, list[Diagnostic]]:
        """Checks a program. The CheckedProgram may only be run when there is no error.

        A project of modules is checked by calling this once per module, in the order
        they are imported, giving the same `declared` to every call: the analysis of the
        last module then holds every function of every module, with its qualified name
        (decision 0018, 2). The diagnostics are the ones of all the modules checked."""
        if declared is None:
            declared = {}
        symbols_before = len(self._symbols)
        errors_before = sum(1 for diagnostic in self._diagnostics if diagnostic.severity == ERROR)
        try:
            self._check_program(program, declared)
        except _TooManyErrors:
            pass
        errors_after = sum(1 for diagnostic in self._diagnostics if diagnostic.severity == ERROR)
        # A warning only helps when the program is otherwise correct: on top of an error it
        # would describe a program that is already going to be rejected. The warnings of a
        # module checked before an error are kept; the ones of the modules after it are not.
        if errors_before == 0 and errors_after == 0:
            self._warnings(program, self._symbols[symbols_before:])
        checked = CheckedProgram(
            program, declared, self._types, tuple(self._symbols), tuple(self._calls), dict(self._refined),
            dict(self._records), self._capabilities, dict(self._targets),
            dict(self._enums),
        )
        return checked, self._diagnostics

    def _check_program(self, program: ast.Program, declared: dict[str, ast.Function]) -> None:
        # Types first: any signature or annotation may name one, wherever it is declared. Their
        # conditions are checked before the signatures, so that a type whose condition is wrong is
        # already unusable when a signature names it: its error is reported once, not at every use.
        self._declare_names(program.types, program.records, program.enums)
        self._declare_types(program.types)
        self._declare_uses(program.uses)
        self._function_names.update(self._key(function.name) for function in program.functions)
        for declaration in program.types:
            self._type_condition(declaration)
        # The records come after the conditions of the refined types, for the same reason:
        # a type whose condition is wrong is already unusable when another type names it.
        self._declare_enums(program.enums)
        self._declare_records(program.records)
        own_signatures: list[tuple[ast.Function, Signature]] = []

        # Signatures first: a function can be called before the line that declares it.
        for function in program.functions:
            signature = self._signature(function)
            own_signatures.append((function, signature))
            key = self._key(function.name)
            if function.name in BUILTINS:
                self._report(
                    "E2002",
                    f"'{function.name}' is a built-in function and cannot be declared again",
                    function.name_span,
                    hint="Choose a different name for this function.",
                )
            elif key in self._type_names or key in self._record_names or key in self._enum_names:
                hint = (f"{function.name}(x) already means: build one: {function.name}(field: value)"
                        if key in self._record_names
                        else f"{function.name}(x) already means: check that x is a valid {function.name}.")
                self._report(
                    "E2006",
                    f"'{function.name}' is the name of a type and cannot be used for a function",
                    function.name_span,
                    hint=hint,
                )
            elif key in declared:
                first = declared[key].name_span
                self._report(
                    "E2002",
                    f"The function '{function.name}' is declared more than once",
                    function.name_span,
                    notes=(f"It was first declared at line {first.line}, column {first.column}.",),
                )
            else:
                declared[key] = function
                self._signatures[key] = signature
                symbol = Symbol(function.name, "function", signature.return_type, function.name_span, None, None,
                                module=self._module)
                self._function_symbols[key] = symbol
                self._symbols.append(symbol)
                if function.public:
                    self._public.add(key)

        if self.require_main or "main" in declared:
            self._main(declared.get(self._key("main")))
        for function, signature in own_signatures:
            self._function(function, signature)

    # Refined types

    def _declare_names(self, refined: tuple[ast.TypeDecl, ...], records: tuple[ast.RecordDecl, ...],
                       enums: tuple[ast.EnumDecl, ...]) -> None:
        """Registers the name of every type the program declares, in the order they appear.

        A name belongs to one type: it cannot be declared twice, whatever the kind of the
        two declarations (decision 0014, 5).
        """
        declarations = [(declaration.span.line, declaration.span.column, declaration) for declaration in refined]
        declarations += [(declaration.span.line, declaration.span.column, declaration)
                         for declaration in records]
        declarations += [(declaration.span.line, declaration.span.column, declaration)
                         for declaration in enums]
        declarations.sort(key=lambda item: (item[0], item[1]))
        for _, _, declaration in declarations:
            name, span = declaration.name, declaration.name_span
            record = isinstance(declaration, ast.RecordDecl)
            enum = isinstance(declaration, ast.EnumDecl)
            key = self._key(name)
            if name in KNOWN_TYPES or (record and name == type_model.LIST.name):
                self._report("E2016", f"'{name}' is a built-in type and cannot be declared again", span,
                             hint="Choose a different name for this type.")
            elif not name[0].isupper():
                self._report("E2016", f"The type name '{name}' must start with a capital letter", span,
                             hint=f"Write it as: {name[0].upper()}{name[1:]}")
            elif key in self._type_names:
                first = self._type_names[key].name_span
                self._report("E2016", f"The type '{name}' is declared more than once", span,
                             notes=(f"It was first declared at line {first.line}, column {first.column}.",))
            elif key in self._record_names:
                first = self._record_names[key].name_span
                self._report("E2016", f"The type '{name}' is declared more than once", span,
                             notes=(f"It was first declared at line {first.line}, column {first.column}.",))
            elif key in self._enum_names:
                first = self._enum_names[key].name_span
                self._report("E2016", f"The type '{name}' is declared more than once", span,
                             notes=(f"It was first declared at line {first.line}, column {first.column}.",))
            elif record:
                self._record_names[key] = declaration
                if declaration.public:
                    self._public.add(key)
            elif enum:
                self._enum_names[key] = declaration
                if declaration.public:
                    self._public.add(key)
            else:
                self._type_names[key] = declaration
                if declaration.public:
                    self._public.add(key)

    def _declare_types(self, declarations: tuple[ast.TypeDecl, ...]) -> None:
        """Resolves what each refined type refines."""
        for name in self._type_names:
            self._resolve(name, [])

    def _resolve(self, name: str, visiting: list[str]) -> RefinedType | None:
        """The refined type `name`, with its chain of bases. None if its declaration has an error."""
        if name in self._refined:
            return self._refined[name]
        declaration = self._type_names[name]
        if name in visiting:
            # Reported once, at the declaration where the chain started.
            return None
        if declaration.base.name == "List" and declaration.base.arguments:
            if not visiting:
                self._report(
                    "E2016",
                    f"The refined type '{name}' cannot refine a list type yet",
                    declaration.base.span,
                    hint="Refining 'List[T]' is not supported yet. Refine a built-in type such as Int or Text.",
                )
            return None
        if self._key(declaration.base.name) in self._record_names:
            if not visiting:
                self._report(
                    "E2016",
                    f"The refined type '{name}' cannot refine a record type",
                    declaration.base.span,
                    hint="Refining a record is not supported yet. Refine a built-in type such as Int or Text.",
                )
            return None
        base_name = self._key(declaration.base.name)
        if base_name in self._type_names:
            base = self._resolve(base_name, [*visiting, name])
            if base is None:
                if not visiting and self._in_cycle(name):
                    self._report(
                        "E2016",
                        f"The type '{name}' refines itself through a chain of types",
                        declaration.base.span,
                        hint="A chain of refined types must end in Int, Float, Bool or Text.",
                    )
                return None
            refined = RefinedType(name, declaration, base_name, base.root, (*base.chain, declaration))
        else:
            base_type = self._value_type(declaration.base, f"The type '{name}'")
            if base_type is None:
                return None
            refined = RefinedType(name, declaration, base_type, base_type, (declaration,))
        self._refined[name] = refined
        # The declaration and its base are already valid. Keep the model beside
        # the metadata; a failure here would be an internal inconsistency.
        self._type_adapter.register_refined(refined.name, refined.base, refined.declaration)
        return refined

    def _in_cycle(self, name: str) -> bool:
        seen: set[str] = set()
        current = self._key(self._type_names[name].base.name)
        while current in self._type_names and current not in seen:
            if current == name:
                return True
            seen.add(current)
            current = self._key(self._type_names[current].base.name)
        return False

    def _type_condition(self, declaration: ast.TypeDecl) -> None:
        """Checks the condition after 'where'. Only `value` is visible in it, and it calls no
        function of the program: a refinement is a fact about one value and nothing else."""
        refined = self._refined.get(self._key(declaration.name))
        if refined is None or self._type_names.get(self._key(declaration.name)) is not declaration:
            return
        scope = _Scope()
        scope.span = declaration.condition.span
        scope.names["value"] = Symbol("value", "value", refined.base, declaration.name_span, None,
                                      declaration.condition.span)
        self._refining = declaration.name
        errors = len(self._diagnostics)
        try:
            self._condition(declaration.condition, scope, f"'where' in '{declaration.name}'")
        finally:
            self._refining = None
        if len(self._diagnostics) > errors:
            # Constants cannot be checked against a condition that is not well formed, and the
            # types that refine this one are left without a valid chain.
            self._drop(declaration.name)

    def _drop(self, name: str) -> None:
        for other in [kind for kind, refined in self._refined.items()
                      if any(step.name == name for step in refined.chain)]:
            del self._refined[other]
            self._type_adapter.drop_refined(other)

    # Record types

    def _declare_uses(self, declarations: tuple[ast.UsesDecl, ...]) -> None:
        """The capabilities the program declares that it needs (decisions 0015 and 0020).

        Declaring is not granting: the user has to allow the capability too, and the
        environment has to permit it. The host checks the three when an operation runs.
        """
        declared: dict[str, list[str]] = {capability: [] for capability in (READ, WRITE, NETWORK, PROCESS)}
        for declaration in declarations:
            values = declared[declaration.capability]
            if declaration.path not in values:
                values.append(declaration.path)
        self._capabilities = Capabilities(
            read=tuple(declared[READ]), write=tuple(declared[WRITE]),
            network=tuple(declared[NETWORK]), process=tuple(declared[PROCESS]),
        )

    def _check_capability(self, node: ast.Call) -> None:
        """A host operation needs a declaration that covers its target.

        This is a help, not the security: the interpreter checks the permissions again
        when the program runs (decision 0015, 5).
        """
        capability = CAPABILITY_FUNCTIONS[node.callee]
        if not node.arguments:
            return
        path = node.arguments[0]
        if not isinstance(path, ast.TextLiteral):
            # The path is computed: only the interpreter can tell whether it is allowed.
            return
        if self._capabilities.covers(capability, path.value):
            return
        if not self._capabilities.comparable(capability, path.value):
            # The declared path and this one cannot be compared (one is relative and the
            # other absolute): only the interpreter can tell, and it has the working
            # directory.
            return
        self._report(
            "E2026",
            f"This program does not declare that it needs to {capability} '{path.value}'",
            path.span,
            hint=f"Declare it at the top level of the file: uses {capability} \"{path.value}\"",
        )

    def _declare_records(self, declarations: tuple[ast.RecordDecl, ...]) -> None:
        """Resolves the record types the program declares, and decides which ones are valid.

        The names are already registered, so that a record can use another one declared
        later (a forward reference). Then the fields are resolved, the cycles are
        found, and the valid declarations get their identity.
        """
        self._cyclic_records = set()
        # The fields: their names and their types. A field repeated, or a type that is
        # not a type, is a declaration that cannot be used; the error is reported once,
        # where it happens.
        field_types: dict[str, tuple[tuple[str, str], ...]] = {}
        field_refs: dict[str, tuple[tuple[str, ast.TypeRef], ...]] = {}
        for name, declaration in self._record_names.items():
            fields: list[tuple[str, str]] = []
            references: list[tuple[str, ast.TypeRef]] = []
            seen: set[str] = set()
            broken = False
            for declared_field in declaration.fields:
                if declared_field.name in seen:
                    self._report("E2016", f"The field '{declared_field.name}' is declared more than once in '{name}'",
                                 declared_field.name_span,
                                 notes=(f"'{name}' is declared at line {declaration.name_span.line}.",))
                    broken = True
                    continue
                seen.add(declared_field.name)
                kind = self._value_type(declared_field.type, f"The field '{declared_field.name}' of '{name}'",
                                        declared_records=True)
                if kind is None:
                    broken = True
                    continue
                fields.append((declared_field.name, kind))
                references.append((declared_field.name, declared_field.type))
            if not broken:
                field_types[name] = tuple(fields)
                field_refs[name] = tuple(references)
        self._record_refs = field_refs

        # The cycles: a record cannot contain itself, directly or through another one.
        self._find_record_cycles(field_refs)

        # A record that uses a record that cannot be used is not usable either. Its own
        # declaration has no error: the error is the one of the record it depends on.
        invalid = set(self._cyclic_records)
        invalid.update(name for name in self._record_names if name not in field_types)
        changed = True
        while changed:
            changed = False
            for name, fields in field_refs.items():
                if name in invalid:
                    continue
                for _, reference in fields:
                    if any(dependency in invalid for dependency in self._record_dependencies(reference)):
                        invalid.add(name)
                        changed = True
                        break

        # What is left is a valid declaration. Each one gets its own identity, and the
        # types that depend on it are built after it, so the model can be filled in.
        self._record_fields = field_types
        for name in field_types:
            if name in invalid:
                continue
            self._record_identities[name] = type_model.RecordIdentity(_next_identity())
        for name in self._build_order([name for name in field_types if name not in invalid]):
            declaration = self._record_names[name]
            identity = self._record_identities[name]
            model_fields = []
            for field_name, kind in field_types[name]:
                model = self._type_adapter.resolve(kind)
                if model is None:
                    raise RuntimeError(f"the type {kind!r} of the field {field_name!r} is missing from the type model")
                model_fields.append((field_name, model))
            nominal = self._type_adapter.register_record(name, tuple(model_fields), identity)
            self._records[name] = RecordType(name, declaration, field_types[name], identity, nominal)

    def _declare_enums(self, declarations: tuple[ast.EnumDecl, ...]) -> None:
        """Resolve every closed enum and its variant payload types."""
        identities: dict[str, type_model.RecordIdentity] = {}
        for declaration in declarations:
            key = self._key(declaration.name)
            if key in self._enum_names:
                identity = type_model.RecordIdentity(_next_identity())
                identities[key] = identity
                self._type_adapter.register_enum(key, identity)
        for declaration in declarations:
            key = self._key(declaration.name)
            if key not in self._enum_names:
                continue
            variants: list[EnumVariantType] = []
            seen_variants: dict[str, Span] = {}
            broken = False
            for variant in declaration.variants:
                if variant.name in seen_variants:
                    first = seen_variants[variant.name]
                    self._report("E2016", f"The variant '{variant.name}' is declared more than once in '{key}'",
                                 variant.name_span,
                                 notes=(f"It was first declared at line {first.line}, column {first.column}.",))
                    broken = True
                    continue
                seen_variants[variant.name] = variant.name_span
                fields: list[tuple[str, str]] = []
                seen_fields: set[str] = set()
                for field in variant.fields:
                    if field.name in seen_fields:
                        self._report("E2016", f"The field '{field.name}' is declared more than once in "
                                     f"'{key}.{variant.name}'", field.name_span)
                        broken = True
                        continue
                    seen_fields.add(field.name)
                    kind = self._value_type(field.type, f"The field '{field.name}' of '{key}.{variant.name}'",
                                            declared_records=True)
                    if kind is None:
                        broken = True
                    else:
                        fields.append((field.name, kind))
                variants.append(EnumVariantType(variant.name, tuple(fields), variant))
            if variants and not broken:
                identity = identities[key]
                self._enums[key] = EnumType(key, declaration, tuple(variants), identity)

    def _record_dependencies(self, reference: ast.TypeRef) -> list[str]:
        """The record types a type reference depends on, looking inside `List[...]` too.

        The reference is read, not its text: a field of type `List[List[Point]]`
        depends on `Point` just as one of type `Point` does.
        """
        found: list[str] = []
        if self._key(reference.name) in self._record_names:
            found.append(self._key(reference.name))
        for argument in reference.arguments:
            found.extend(self._record_dependencies(argument))
        return found

    def _find_record_cycles(self, field_refs: dict[str, tuple[tuple[str, ast.TypeRef], ...]]) -> None:
        """Reports every cycle of record types, once, where the cycle starts."""
        visiting: list[str] = []
        done: set[str] = set()

        def walk(name: str) -> None:
            if name in done:
                return
            if name in visiting:
                cycle = visiting[visiting.index(name):] + [name]
                start = cycle[0]
                declaration = self._record_names[start]
                self._report(
                    "E2016",
                    f"The record '{start}' cannot contain itself",
                    declaration.name_span,
                    hint="A record cannot hold a value of its own type, directly or through another record.",
                    notes=(f"The cycle is: {' -> '.join(cycle)}",),
                )
                self._cyclic_records.update(cycle)
                return
            visiting.append(name)
            for _, reference in field_refs.get(name, ()):
                for dependency in self._record_dependencies(reference):
                    walk(dependency)
            visiting.pop()
            done.add(name)

        for name in list(field_refs):
            walk(name)

    def _build_order(self, names: list[str]) -> list[str]:
        """The records ordered so that every one comes after the ones it depends on."""
        ordered: list[str] = []
        done: set[str] = set()

        def build(name: str) -> None:
            if name in done:
                return
            done.add(name)
            for _, reference in self._record_refs.get(name, ()):
                for dependency in self._record_dependencies(reference):
                    build(dependency)
            ordered.append(name)

        for name in names:
            build(name)
        return ordered

    def _root(self, kind: str) -> str:
        """The built-in type a type is made of: itself, or the end of a chain of refinements.

        Primitive names, refined types valid in the current checker state and list
        types go through the D01 model. Names outside that model keep the legacy
        behaviour and are returned unchanged: `ANY_VALUE`, qualifiers, unknown names
        and constructors the language does not enable yet. A known primitive or a
        valid refined type missing from the model is an internal inconsistency, not a
        fallback case, so it raises instead of hiding the broken bridge.
        """
        if kind in self._refined:
            model = self._type_adapter.refined(kind)
            if model is None:
                raise RuntimeError(f"the refined type {kind!r} is missing from the type model")
            return type_model.display(type_model.root(model))
        if kind in KNOWN_TYPES:
            model = self._type_adapter.resolve(kind)
            if model is None:
                raise RuntimeError(f"the primitive type {kind!r} is missing from the type model")
            return type_model.display(type_model.root(model))
        model = self._type_adapter.try_resolve(kind)
        if model is not None:
            return type_model.display(type_model.root(model))
        return kind

    def _accepts(self, expected: str, found: str) -> bool:
        """Whether a value of type `found` can be used where `expected` is needed.

        Primitive names and refined types that are valid in the current checker
        state use the D01 `assignable` rule, with the expected type first. Names
        outside that model keep the legacy name-chain rule: unknown names,
        qualifiers, `ANY_VALUE` and generic constructions are unchanged. A
        representable type missing from the model is an internal inconsistency,
        not a fallback case.
        """
        expected_model = self._current_type_model(expected)
        found_model = self._current_type_model(found)
        if expected_model is not None and found_model is not None:
            return type_model.assignable(expected_model, found_model)
        return self._accepts_legacy(expected, found)

    def _current_type_model(self, kind: str) -> type_model.Type | None:
        """The model for a type the checker currently represents, or None if it is outside D01.

        A primitive or a refined type valid in `_refined` must have a model; a
        missing one is an internal inconsistency and raises instead of falling back.
        A canonical list type such as `List[Int]` resolves through the adapter; a
        malformed or unsupported composite name stays outside the model.
        """
        if kind in self._refined:
            model = self._type_adapter.refined(kind)
            if model is None:
                raise RuntimeError(f"the refined type {kind!r} is missing from the type model")
            return model
        if kind in KNOWN_TYPES:
            model = self._type_adapter.resolve(kind)
            if model is None:
                raise RuntimeError(f"the primitive type {kind!r} is missing from the type model")
            return model
        return self._type_adapter.try_resolve(kind)

    def _accepts_legacy(self, expected: str, found: str) -> bool:
        """The pre-D01 name-chain rule, kept for names outside the model."""
        kind: str | None = found
        while kind is not None:
            if kind == expected:
                return True
            refined = self._refined.get(kind)
            kind = refined.base if refined is not None else None
        return False

    def _constant(self, node: ast.Expr):
        """The value of a literal (possibly negated or in parentheses), or None for anything else."""
        if isinstance(node, (ast.IntLiteral, ast.FloatLiteral, ast.TextLiteral, ast.BoolLiteral)):
            return node.value
        if isinstance(node, ast.Group):
            return self._constant(node.expression)
        if isinstance(node, ast.Unary):
            inner = self._constant(node.operand)
            if node.operator == "-" and isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return -inner
            if node.operator == "not" and isinstance(inner, bool):
                return not inner
        return None

    def _check_constant(self, node: ast.Expr, kind: str) -> None:
        """Reports E2017 if the constant `node` is not a valid value of the refined type `kind`."""
        refined = self._refined.get(kind)
        constant = self._constant(node)
        if refined is None or constant is None or self._refinement_steps is None:
            return
        self._refinement_steps += refined.cost
        if self._refinement_steps > MAX_REFINEMENT_STEPS:
            self._refinement_steps = None
            self._report(
                "E2019",
                f"Checking constants against refined types needs more than {MAX_REFINEMENT_STEPS} steps",
                node.span,
                hint="Use fewer constants of long chains of refined types, or shorter conditions. "
                     "The limit keeps the analysis fast; every constant is still checked before running.",
            )
            return
        # Imported here: the interpreter depends on this module.
        from .interpreter import broken_rule
        from .values import show_value

        written = show_value(constant)
        try:
            broken = broken_rule(refined.chain, constant)
        except NexoraRuntimeError as error:
            self._report(
                "E2017",
                f"{written} cannot be checked against the condition of '{kind}'",
                node.span,
                notes=(f"Evaluating the condition stops with: {error.diagnostic.label}",),
            )
            return
        if broken is not None:
            self._report("E2017", f"{written} is not a valid {kind}", node.span,
                         notes=refinement_notes(kind, broken, written))

    def _expect_type(self, expected: str, found: str, node: ast.Expr, notes: tuple[str, ...]) -> None:
        """Checks that the expression `node`, of type `found`, can be used where `expected` is needed.

        A constant of the base type is accepted where a refined type is expected if it satisfies
        the condition, which is checked here. Any other value has to be checked explicitly."""
        if self._accepts(expected, found):
            return
        expected_model = self._current_type_model(expected)
        if expected_model is not None and isinstance(expected_model, type_model.Refined):
            found_model = self._current_type_model(found)
            if found_model is None:
                same_root = self._root(found) == self._root(expected)
                found_is_refined = False
            else:
                same_root = type_model.equal(
                    type_model.root(found_model), type_model.root(expected_model)
                )
                found_is_refined = isinstance(found_model, type_model.Refined)
            if same_root:
                if self._constant(node) is not None and not found_is_refined:
                    self._check_constant(node, expected)
                    return
                self._report(
                    "E2011",
                    f"Expected {expected}, found {found}",
                    node.span,
                    hint=f"Check the value explicitly with {expected}(...). "
                         f"The program stops there if the value does not satisfy the condition of {expected}.",
                    notes=notes,
                )
                return
        self._report(
            "E2011",
            f"Expected {expected}, found {found}",
            node.span,
            hint=_conversion_hint(self._root(found), self._root(expected)),
            notes=notes,
        )

    def _report(self, code: str, label: str, span: Span | None, *, hint: str | None = None,
                notes: tuple[str, ...] = ()) -> None:
        self._diagnostics.append(Diagnostic(code, label, span, hint, notes))
        if len(self._diagnostics) >= MAX_DIAGNOSTICS:
            raise _TooManyErrors

    def _warnings(self, program: ast.Program, symbols: list[Symbol]) -> None:
        """The warnings of one module, once it is known to have no errors.

        Warnings describe improvements, not failures: an unused name, a `var` whose value
        never changes, or a name that does not follow the convention. They never stop the
        program and they are not emitted when the program already has an error.
        """
        pending: list[Diagnostic] = []
        public_functions = {function.name for function in program.functions if function.public}
        for symbol in symbols:
            if symbol.category not in ("variable", "parameter") or symbol.name == "_":
                continue
            kind = "parameter" if symbol.category == "parameter" else (
                "iterator" if symbol.loop_variable else "variable")
            if not symbol.reads:
                if kind == "parameter":
                    hint = "Remove it, or use it in the body. Name it '_' if the signature must keep the position."
                elif kind == "iterator":
                    hint = "Remove it, or use it in the body of the loop."
                else:
                    hint = "Remove it, or use its value in an expression."
                pending.append(Diagnostic(
                    "W2001", f"The {kind} '{symbol.name}' is never used", symbol.span,
                    hint=hint, severity=WARNING,
                ))
            elif symbol.mutable and not symbol.assignments:
                pending.append(Diagnostic(
                    "W2002", f"'{symbol.name}' is declared with 'var' but is never reassigned",
                    symbol.span,
                    hint="Declare it with 'let': its value never changes.",
                    severity=WARNING,
                ))
            # A parameter of a public function is part of what another module sees, so its
            # spelling is left alone here: the interface is not renamed behind its callers.
            if symbol.category == "parameter" and symbol.function in public_functions:
                continue
            if _SNAKE_CASE.fullmatch(symbol.name) is None:
                pending.append(Diagnostic(
                    "W2003", f"The {kind} name '{symbol.name}' does not follow snake_case",
                    symbol.span,
                    hint=f"Write it as '{_snake_case(symbol.name)}'.",
                    severity=WARNING,
                ))
        for function in program.functions:
            # Types of the standard library and public functions keep their own spelling:
            # a public name belongs to every module that imports this one.
            if function.public or function.name == "_":
                continue
            if _SNAKE_CASE.fullmatch(function.name) is None:
                pending.append(Diagnostic(
                    "W2003", f"The function name '{function.name}' does not follow snake_case",
                    function.name_span,
                    hint=f"Write it as '{_snake_case(function.name)}'.",
                    severity=WARNING,
                ))
        pending.sort(key=lambda diagnostic: (diagnostic.span.line, diagnostic.span.column, diagnostic.code)
                     if diagnostic.span is not None else (0, 0, diagnostic.code))
        self._diagnostics.extend(pending)

    # Declarations

    def _value_type(self, reference: ast.TypeRef, what: str, *, declared_records: bool = False) -> str | None:
        """The type named by `reference`, which must be a type a value can have.

        `declared_records` accepts a record the program declares even when its own
        declaration has an error: the error is reported where it happens, not at
        every use.
        """
        if reference.name == VOID:
            self._report(
                "E2012",
                f"{what} cannot have the type Void",
                reference.span,
                # Since 0.12 Void is never written, not even after 'gives' (decision 0019, 4.1).
                hint="Void means 'no value', and it is never written: a function that gives nothing has no 'gives'.",
            )
            return None
        return self._known_type(reference, declared_records=declared_records)

    def _known_type(self, reference: ast.TypeRef, *, declared_records: bool = False) -> str | None:
        # A type of another module is written with its module in front, and it is looked
        # up qualified: `models.Point` is the record `Point` of the module `models`
        # (decision 0018, 5). The type the analysis returns is that same qualified name,
        # so two modules can both declare a `Point` without the analysis confusing them.
        key = self._type_key(reference)
        if reference.arguments:
            if reference.qualifier is not None:
                self._report(
                    "E2012",
                    f"'{key}' cannot take type arguments",
                    reference.span,
                    hint="Only 'List', 'Option' and 'Result' take type arguments, and they are "
                         "built-in: a module does not declare them.",
                )
                return None
            arity = _TYPE_ARGUMENT_COUNTS.get(reference.name)
            if arity is None:
                self._report(
                    "E2012",
                    f"'{reference.name}' cannot take type arguments",
                    reference.span,
                    hint="Only 'List', 'Option' and 'Result' take type arguments: "
                         "List[Int], Option[Text], Result[Int, Text].",
                )
                return None
            if len(reference.arguments) != arity:
                self._report(
                    "E2012",
                    f"'{reference.name}' takes exactly {arity} type argument{'' if arity == 1 else 's'}, "
                    f"but {len(reference.arguments)} were given",
                    reference.span,
                    hint=f"Write {reference.name}[Int]" + (", Text]" if arity == 2 else "]"),
                )
                return None
            what = "A list element" if reference.name == "List" else f"An argument of '{reference.name}'"
            arguments: list[str] = []
            for argument in reference.arguments:
                resolved = self._value_type(argument, what, declared_records=declared_records)
                if resolved is None:
                    return None
                arguments.append(resolved)
            if reference.name == "Option":
                return f"Option[{arguments[0]}]"
            if reference.name == "Result":
                return f"Result[{arguments[0]}, {arguments[1]}]"
            return f"List[{arguments[0]}]"
        if reference.qualifier is None and reference.name in KNOWN_TYPES:
            # A built-in type belongs to no module: `Int` is `Int` in every file of the
            # program. A module cannot redeclare one; that is reported where it declares.
            return reference.name
        if key in self._type_names:
            if not self._is_public(key):
                self._private(key, reference.span)
                return None
            # A declared type whose own declaration has an error: that error is already reported.
            return key if key in self._refined else None
        if key in self._record_names:
            if not self._is_public(key):
                self._private(key, reference.span)
                return None
            # A record the program declares: a type, unless its own declaration has an
            # error, which is already reported.
            if key in self._records or declared_records:
                return key
            return None
        if key in self._enum_names:
            if not self._is_public(key):
                self._private(key, reference.span)
                return None
            if key in self._enums or declared_records:
                return key
            return None
        candidates = [*KNOWN_TYPES, *self._visible(self._type_names), *self._visible(self._record_names),
                      *self._visible(self._enum_names)]
        written = key
        close = difflib.get_close_matches(written, candidates, n=1, cutoff=0.5)
        if reference.name == "String":
            hint = "The text type is called Text."
        elif reference.qualifier is not None and reference.name in KNOWN_TYPES:
            # A built-in written with a module in front: the correction is the other way
            # around, to drop the module (decision 0018, 2).
            hint = (f"'{reference.name}' is a built-in type: it belongs to no module. "
                    f"Write it as '{reference.name}'.")
        elif close:
            hint = f"Did you mean '{close[0]}'?"
        else:
            hint = "The types are Int, Float, Bool, Text and Void, and the types the program declares."
        self._report("E2012", f"'{written}' is not a type", reference.span, hint=hint)
        return None

    def _signature(self, function: ast.Function) -> Signature:
        params = tuple(
            (param.name, self._value_type(param.type, f"The parameter '{param.name}'"))
            for param in function.params
        )
        if function.return_type is None:
            return Signature(function.name, params, VOID)
        if function.return_type.name == VOID and function.return_type.qualifier is None:
            # `gives Void` is not written (decision 0019, 4.1); the function still gives nothing.
            self._report(
                "E2012",
                "'Void' is not written after 'gives'",
                function.return_type.span,
                hint="A function that gives nothing has no 'gives'",
            )
            return Signature(function.name, params, VOID)
        return Signature(function.name, params, self._known_type(function.return_type))

    def _main(self, main: ast.Function | None) -> None:
        if main is None:
            self._report(
                "E2001",
                "This program has no 'main' function, so there is nothing to run",
                None,
                hint="Add the entry point: fn main() { ... }",
            )
            return
        if main.params:
            self._report(
                "E2013",
                "'main' cannot have parameters",
                main.params[0].span.to(main.params[-1].span),
                hint="Write: fn main() {",
            )
        signature = self._signatures.get(self._key("main"))
        if signature is not None and signature.return_type not in (None, VOID):
            self._report("E2004", "'main' gives nothing", main.return_type.span, hint="Write: fn main() {")

    def _function(self, function: ast.Function, signature: Signature) -> None:
        self._function_name = function.name
        self._return_type = signature.return_type

        scope = _Scope()
        scope.span = function.body.span
        for param, (_, param_type) in zip(function.params, signature.params, strict=True):
            if param.name == "result":
                self._report(
                    "E2013",
                    "A parameter cannot be named 'result'",
                    param.name_span,
                    hint="'result' is the name of the value a function gives, inside a 'promises' clause.",
                )
            elif not self._name_is_free(param.name, param.name_span, scope):
                continue
            self._declare(scope, param.name, "parameter", param_type, param.name_span)

        self._clause_names(function)
        for contract in function.contracts:
            contract_scope = scope
            if contract.clause == "promises" and signature.return_type not in (None, VOID):
                # 'result' exists only here, and only when there is a value to name.
                contract_scope = _Scope(scope)
                # Not a declared symbol: it only names the return value inside this clause.
                contract_scope.names["result"] = Symbol(
                    "result", "result", signature.return_type, function.return_type.span, function.name, contract.span,
                )
            self._condition(contract.condition, contract_scope, f"'{contract.clause}'")

        for example in function.examples:
            self._example(example, function.name)

        returns = self._block(function.body, _Scope(scope))
        if signature.return_type not in (None, VOID) and not returns:
            self._report(
                "E2014",
                f"'{function.name}' must return a value of type {signature.return_type}, "
                "but its body can end without a 'return'",
                function.name_span,
                hint="Make sure every path through the function ends with 'return'. "
                     "An 'if' without 'else' can be skipped, and a loop may not run at all.",
            )

    def _clause_names(self, function: ast.Function) -> None:
        """E2031: a clause name is used once in a function, its loops included, and is neither a
        parameter nor `result` (decision 0019, 4.1). A name is not a variable."""
        clauses = [*function.contracts, *(clause for loop in _loops(function.body) for clause in loop.clauses)]
        clauses.sort(key=lambda clause: (clause.span.line, clause.span.column))
        params = {param.name for param in function.params}
        seen: dict[str, Span] = {}
        for clause in clauses:
            if clause.name is None:
                continue
            if clause.name in seen:
                first = seen[clause.name]
                self._report(
                    "E2031",
                    f"The promise name '{clause.name}' is used twice in '{function.name}'",
                    clause.span,
                    hint="Give each clause of a function, and of its loops, its own name.",
                    notes=(f"It is first used at line {first.line}, column {first.column}.",),
                )
            elif clause.name in params:
                self._report(
                    "E2031",
                    f"The promise name '{clause.name}' is also a parameter of '{function.name}'",
                    clause.span,
                    hint="A clause name says what the clause is about; choose one that is not a parameter.",
                )
            elif clause.name == "result":
                self._report(
                    "E2031",
                    "'result' cannot be the name of a clause",
                    clause.span,
                    hint="'result' is the value the function gives; choose another name.",
                )
            seen.setdefault(clause.name, clause.span)

    def _example(self, example: ast.Example, function: str) -> None:
        """An 'example' clause (decision 0008). It is checked, never evaluated. It does not happen
        inside a call, so it sees no parameter and no 'result', only the functions and types of the
        program; and the calls it makes are references, not edges of the call graph."""
        self._in_example = function
        try:
            self._condition(example.condition, _Scope(), "'example'")
        finally:
            self._in_example = None
        if not own_calls(example, function):
            self._report(
                "E2020",
                f"This example of '{function}' never calls '{function}'",
                example.condition.span,
                hint=f"Write the call with its inputs, for example: example {function}(2) == 4",
            )

    # Records

    def _record_construction(self, node: ast.RecordConstruction, scope: _Scope) -> str | None:
        """`Point(x: 1, y: 2)`: builds a record value.

        Every field of the record is given once, with a value of its type. The order of
        the text does not matter (decision 0014, 2 and 5).
        """
        key = f"{node.qualifier}.{node.name}" if node.qualifier else self._key(node.name)
        record = self._records.get(key)
        if record is not None:
            # The interpreter builds it from this one; a module writes it with its own
            # bare name, and only the analysis knows which one it is (decision 0018, 5).
            self._targets[id(node)] = key
        if record is None and node.qualifier is not None:
            self._unknown_record(node.qualifier, node.name, node.span)
        if record is None or not self._is_public(key):
            if record is not None:
                self._private(key, node.span)
            # Either the declaration of the record has an error, already reported where it
            # happens, or the module does not make it public. The values are still checked,
            # so that a mistake inside one of them is not hidden.
            for field in node.fields:
                self._expression(field.value, scope)
            return None
        given: dict[str, ast.FieldInitializer] = {}
        repeated: list[ast.FieldInitializer] = []
        unknown: list[ast.FieldInitializer] = []
        for field in node.fields:
            if record.field_type(field.name) is None:
                unknown.append(field)
            elif field.name in given:
                repeated.append(field)
            else:
                given[field.name] = field
        for field in unknown:
            self._report(
                "E2023",
                f"The record '{record.name}' has no field named '{field.name}'",
                field.name_span,
                hint=f"The fields of {record.name} are: {', '.join(name for name, _ in record.fields)}.",
            )
        for field in repeated:
            self._report("E2023", f"The field '{field.name}' is given twice", field.name_span)
        for name, _ in record.fields:
            if name not in given:
                self._report(
                    "E2023",
                    f"The field '{name}' of '{record.name}' is missing",
                    node.name_span,
                    hint=f"Give it a value: {record.name}({name}: ...)",
                )
        for field in node.fields:
            expected = record.field_type(field.name)
            value_type = self._expression(field.value, scope, expected)
            if value_type is not None and expected is not None:
                self._expect_type(
                    expected, value_type, field.value,
                    (f"The field '{field.name}' of '{record.name}' is {expected}.",),
                )
        return record.name

    def _field_access(self, node: ast.FieldAccess, scope: _Scope) -> str | None:
        """`p.x`: reads a field of a record value."""
        target = self._expression(node.target, scope)
        if target is None:
            return None
        record = self._records.get(target)
        if record is None:
            self._report(
                "E2024",
                f"A value of type {target} is not a record, so it has no fields",
                node.target.span,
                hint="Only a record has fields.",
            )
            return None
        kind = record.field_type(node.name)
        if kind is None:
            self._report(
                "E2024",
                f"The record '{target}' has no field named '{node.name}'",
                node.name_span,
                hint=f"The fields of {target} are: {', '.join(name for name, _ in record.fields)}.",
            )
            return None
        return kind

    def _field_assign(self, statement: ast.FieldAssign, scope: _Scope) -> None:
        """`p.x = value`: a record is immutable, so its fields never change."""
        target = self._expression(statement.target, scope)
        if target is None:
            return
        record = self._records.get(target)
        if record is None:
            self._report(
                "E2024",
                f"A value of type {target} is not a record, so it has no fields",
                statement.target.span,
                hint="Only a record has fields.",
            )
            return
        if record.field_type(statement.name) is None:
            self._report(
                "E2024",
                f"The record '{target}' has no field named '{statement.name}'",
                statement.name_span,
                hint=f"The fields of {target} are: {', '.join(name for name, _ in record.fields)}.",
            )
            return
        self._report(
            "E2025",
            f"The field '{statement.name}' of '{target}' cannot be given a new value",
            statement.name_span,
            hint="A record is immutable: build another one with the value you want.",
        )
        # The value is checked, but its type is not compared with the type of the field:
        # the field cannot be given a new value anyway (decision 0014, 5).
        self._expression(statement.value, scope)

    def _name_is_free(self, name: str, span: Span, scope: _Scope) -> bool:
        """Reports E2006 and returns False if `name` cannot be declared in `scope`.

        Functions, parameters and variables share one namespace, and a visible name is never
        declared again: every name in a function means exactly one thing.
        """
        if self._key(name) in self._type_names or self._key(name) in self._record_names:
            self._report(
                "E2006",
                f"'{name}' is the name of a type and cannot be used for something else",
                span,
                hint="Choose a different name. Types start with a capital letter; values usually do not.",
            )
            return False
        if name in BUILTINS or self._key(name) in self._signatures:
            kind = "a built-in function" if name in BUILTINS else "a function"
            self._report(
                "E2006",
                f"'{name}' is the name of {kind} and cannot be used for something else",
                span,
                hint="Choose a different name.",
            )
            return False
        existing = scope.find(name)
        if existing is not None:
            first = existing.span
            self._report(
                "E2006",
                f"'{name}' is already declared and still visible here",
                span,
                hint="Choose a different name: a visible name cannot be declared again.",
                notes=(f"It was first declared at line {first.line}, column {first.column}.",),
            )
            return False
        return True

    # Statements. Each returns True when it always ends the function with 'return'.

    def _declare(self, scope: _Scope, name: str, category: str, kind: str | None, span: Span, *,
                 mutable: bool = False, loop_variable: bool = False) -> None:
        symbol = Symbol(name, category, kind, span, self._function_name, scope.span, mutable=mutable,
                        loop_variable=loop_variable, module=self._module)
        scope.names[name] = symbol
        self._symbols.append(symbol)

    def _block(self, block: ast.Block, scope: _Scope) -> bool:
        if scope.span is None:
            scope.span = block.span
        returned = False
        reported = False
        for statement in block.statements:
            if returned and not reported:
                self._report(
                    "E2015",
                    "This code can never run: the function has already returned",
                    statement.span,
                    hint="Remove it, or move it before the 'return'.",
                )
                reported = True
            if self._statement(statement, scope):
                returned = True
        return returned

    def _statement(self, statement: ast.Statement, scope: _Scope) -> bool:
        if isinstance(statement, (ast.Let, ast.Var)):
            self._let(statement, scope)
        elif isinstance(statement, ast.Return):
            self._return(statement, scope)
            return True
        elif isinstance(statement, ast.If):
            return self._if(statement, scope)
        elif isinstance(statement, ast.IfLet):
            return self._if_let(statement, scope)
        elif isinstance(statement, ast.Block):
            return self._block(statement, _Scope(scope))
        elif isinstance(statement, ast.While):
            self._while(statement, scope)
        elif isinstance(statement, ast.For):
            self._for(statement, scope)
        elif isinstance(statement, ast.Assign):
            self._assign(statement, scope)
        elif isinstance(statement, ast.FieldAssign):
            self._field_assign(statement, scope)
        else:
            expression = statement.expression
            found = self._expression(expression, scope)
            if found is None:
                pass
            elif isinstance(expression, ast.MatchExpr) and found == VOID:
                pass
            elif not isinstance(expression, ast.Call):
                self._report(
                    "E2010",
                    "The value of this expression is never used",
                    expression.span,
                    hint="Store it with 'let name = ...' or pass it to a function.",
                )
            elif found != VOID:
                self._report(
                    "E2010",
                    f"The {found} returned by '{expression.callee}' is never used",
                    expression.span,
                    hint="Store it with 'let name = ...' or pass it to a function.",
                )
        return False

    def _let(self, statement: ast.Let | ast.Var, scope: _Scope) -> None:
        # The annotation is read first because it is the expected type of the initialiser:
        # `let xs: List[Int] = []` needs it to infer the element type. The variable itself is
        # still not visible inside its own declaration.
        declared = None
        if statement.declared_type is not None:
            declared = self._value_type(statement.declared_type, f"The variable '{statement.name}'")
        value_type = self._expression(statement.value, scope, declared)
        if value_type == VOID:
            self._report("E2011", "This call does not produce a value to store", statement.value.span)
            value_type = None

        variable_type = value_type
        if declared is not None:
            # The annotation decides the type, so later uses are checked against what was intended.
            variable_type = declared
            if value_type is not None:
                self._expect_type(declared, value_type, statement.value,
                                  (f"'{statement.name}' is declared as {declared}.",))

        if self._name_is_free(statement.name, statement.name_span, scope):
            self._declare(scope, statement.name, "variable", variable_type, statement.name_span,
                          mutable=isinstance(statement, ast.Var))

    def _assign(self, statement: ast.Assign, scope: _Scope) -> None:
        """`name = value`: only a variable declared with 'var' takes a new value, and only of its type.
        Parameters stay immutable, so 'promises' and the diagnostics see the values a call received."""
        name, span = statement.name, statement.name_span
        target = scope.find(name)
        # The variable's type is the expected type of the value: `xs = []` needs it to
        # infer the element type. Looking the name up reports nothing by itself.
        value_type = self._expression(statement.value, scope, None if target is None else target.type)
        if target is None:
            self._unknown_variable(name, span, scope)
            return
        if target.category == "parameter":
            self._report(
                "E2007",
                f"'{name}' is a parameter and cannot be given a new value",
                span,
                hint=f"Copy it into a variable: 'var name = {name}'.",
            )
            return
        if target.loop_variable:
            self._report(
                "E2007",
                f"'{name}' is the iterator of a 'for' loop and cannot be given a new value",
                span,
                hint="The iterator takes each element of the list in turn; declare a 'var' for anything that changes.",
            )
            return
        if not target.mutable:
            self._report(
                "E2007",
                f"'{name}' was declared with 'let' and cannot be given a new value",
                span,
                hint="Declare it with 'var' if its value has to change.",
                notes=(f"'{name}' is declared at line {target.span.line}, column {target.span.column}.",),
            )
            return
        target.references.append(span)
        target.reference_modules.append(self._module)
        target.assignments.append(span)
        if value_type == VOID:
            self._report("E2011", "This call does not produce a value to store", statement.value.span)
        elif value_type is not None and target.type is not None:
            self._expect_type(target.type, value_type, statement.value, (f"'{name}' is declared as {target.type}.",))

    def _while(self, statement: ast.While, scope: _Scope) -> None:
        """A loop and its clauses (decision 0010). The clauses see what is visible where the loop is,
        not what its body declares. A loop never counts as always returning: the analysis does not
        evaluate conditions, and the condition may be false from the start."""
        self._condition(statement.condition, scope, "'while'")
        measures = [clause for clause in statement.clauses if clause.clause == "shrinks"]
        for clause in statement.clauses:
            if clause.clause == "keeps":
                self._condition(clause.condition, scope, "'keeps'")
                continue
            found = self._expression(clause.condition, scope)
            if found is not None:
                # The measure is valid when the root of its type is exactly Int. A name outside
                # the model (`ANY_VALUE`, unknown names, dropped refinements) is not an Int and
                # keeps the same diagnostic; a representable type missing from it raises.
                measure_model = self._current_type_model(self._root(found))
                if measure_model is None or not type_model.equal(measure_model, type_model.INT):
                    self._report(
                        "E2011",
                        f"The measure of 'shrinks' must be Int, found {found}",
                        clause.condition.span,
                        hint="The measure is a whole number that gets smaller on every turn and never goes below 0.",
                    )
        if not measures:
            keyword = statement.span
            self._report(
                "E2021",
                "This loop does not say why it ends",
                Span(keyword.line, keyword.column, keyword.line, keyword.column + len("while")),
                hint="Add 'shrinks <expression>' to the header of the loop, with an Int that gets smaller on "
                     "every turn and never goes below 0, for example 'shrinks n - i'.",
            )
        for extra in measures[1:]:
            first = measures[0].span
            self._report(
                "E2021",
                "A loop has exactly one measure",
                extra.span,
                hint="Combine them into one Int that gets smaller on every turn.",
                notes=(f"The first 'shrinks' is at line {first.line}, column {first.column}.",),
            )
        self._block(statement.body, _Scope(scope))

    def _for(self, statement: ast.For, scope: _Scope) -> None:
        """A `for` loop over a `List[T]` (decision 0012). The iterable is checked once, in the
        scope where the loop appears; its element type becomes the type of the iterator, which is
        declared immutable in the scope of the body. The clauses see the same names as the loop,
        never the iterator, as in a `while`; a `for` has no measure because the list is finite."""
        found = self._expression(statement.iterable, scope)
        item: str | None = None
        if found == VOID:
            self._report("E2011", "This call does not produce a value to walk over", statement.iterable.span)
        elif found is not None:
            item = self._list_item(found)
            if item is None:
                self._report(
                    "E2011",
                    f"The value a 'for' walks over must be a List, found {found}",
                    statement.iterable.span,
                    hint="Write the list the loop walks over, for example: for x in xs { ... }.",
                )
        for clause in statement.clauses:
            if clause.clause == "keeps":
                self._condition(clause.condition, scope, "'keeps'")
            else:
                self._report(
                    "E2022",
                    "'shrinks' has no meaning in a 'for' loop",
                    clause.span,
                    hint="A 'for' loop ends when the list is exhausted; remove the 'shrinks' clause.",
                )
        body_scope = _Scope(scope)
        body_scope.span = statement.body.span
        if self._name_is_free(statement.name, statement.name_span, body_scope):
            self._declare(body_scope, statement.name, "variable", item, statement.name_span,
                          loop_variable=True)
        self._block(statement.body, body_scope)

    def _return(self, statement: ast.Return, scope: _Scope) -> None:
        expected = self._return_type
        name = self._function_name

        if statement.value is None:
            if expected not in (None, VOID):
                self._report(
                    "E2011",
                    f"Expected a value of type {expected} after 'return'",
                    statement.span,
                    notes=(f"'{name}' is declared to return {expected}.",),
                )
            return

        found = self._expression(statement.value, scope, expected if expected not in (None, VOID) else None)
        if found is None or expected is None:
            return
        if expected == VOID:
            self._report(
                "E2011",
                f"'{name}' returns Void, so 'return' cannot be followed by a value",
                statement.value.span,
                hint="Write 'return' on its own, or change the return type of the function.",
            )
        elif found == VOID:
            self._report("E2011", "This call does not produce a value to return", statement.value.span)
        else:
            self._expect_type(expected, found, statement.value, (f"'{name}' is declared to return {expected}.",))

    def _if(self, statement: ast.If | ast.IfLet, scope: _Scope) -> bool:
        if isinstance(statement, ast.IfLet):
            return self._if_let(statement, scope)
        self._condition(statement.condition, scope, "'if'")
        then_returns = self._block(statement.then_block, _Scope(scope))
        if statement.else_branch is None:
            return False
        if isinstance(statement.else_branch, (ast.If, ast.IfLet)):
            else_returns = self._if(statement.else_branch, scope)
        else:
            else_returns = self._block(statement.else_branch, _Scope(scope))
        return then_returns and else_returns

    def _if_let(self, statement: ast.IfLet, scope: _Scope) -> bool:
        value_type = self._expression(statement.value, scope)
        then_scope = _Scope(scope)
        if value_type is not None:
            self._check_pattern(statement.pattern, value_type, then_scope)
        then_returns = self._block(statement.then_block, then_scope)
        if statement.else_branch is None:
            return False
        if isinstance(statement.else_branch, (ast.If, ast.IfLet)):
            else_returns = self._if(statement.else_branch, scope)
        else:
            else_returns = self._block(statement.else_branch, _Scope(scope))
        return then_returns and else_returns

    def _condition(self, condition: ast.Expr, scope: _Scope, owner: str) -> None:
        found = self._expression(condition, scope)
        if found is None:
            return
        found_model = self._current_type_model(found)
        if found_model is not None:
            if type_model.assignable(type_model.BOOL, found_model):
                return
        elif self._root(found) == BOOL:
            return
        hint = None
        if found in (INT, FLOAT):
            hint = "A number is not a condition. Compare it explicitly, for example: x != 0"
        elif found == VOID:
            hint = "A call to a Void function does not produce a value."
        self._report("E2011", f"The condition of {owner} must be Bool, found {found}", condition.span, hint=hint)

    def _unknown_variable(self, name: str, span: Span, scope: _Scope) -> None:
        if self._in_example is not None:
            self._report(
                "E2005",
                f"There is no variable named '{name}' here",
                span,
                hint=f"An example has no parameters: write its inputs as values, for example: {self._in_example}(2)",
            )
            return
        if self._refining is not None:
            self._report(
                "E2005",
                f"There is no variable named '{name}' here",
                span,
                hint=f"In the condition of '{self._refining}', the only name is 'value': the value being checked.",
            )
            return
        if name == "result":
            self._report(
                "E2005",
                "There is no variable named 'result' here",
                span,
                hint="'result' only exists inside a 'promises' clause of a function that gives a value.",
            )
            return
        close = difflib.get_close_matches(name, scope.visible(), n=1)
        hint = f"Did you mean '{close[0]}'?" if close else "Declare it first with 'let'."
        self._report("E2005", f"There is no variable named '{name}' here", span, hint=hint)

    # Expressions. Each returns the type of the expression, or None after an error
    # (None silences follow-up errors about the same expression).

    def _expression(self, node: ast.Expr, scope: _Scope, expected: str | None = None) -> str | None:
        found = self._infer(node, scope, expected)
        if found is not None:
            self._types[id(node)] = found
            self._type_adapter.record_expression(id(node), found)
        return found

    def _infer(self, node: ast.Expr, scope: _Scope, expected: str | None = None) -> str | None:
        if isinstance(node, ast.IntLiteral):
            return INT
        if isinstance(node, ast.FloatLiteral):
            return FLOAT
        if isinstance(node, ast.TextLiteral):
            return TEXT
        if isinstance(node, ast.BoolLiteral):
            return BOOL
        if isinstance(node, ast.ListLiteral):
            return self._list_literal(node, scope, expected)
        if isinstance(node, ast.MatchExpr):
            return self._match_expression(node, scope, expected)
        if isinstance(node, ast.Group):
            return self._expression(node.expression, scope, expected)
        if isinstance(node, ast.RecordConstruction):
            return self._record_construction(node, scope)
        if isinstance(node, ast.FieldAccess):
            return self._field_access(node, scope)
        if isinstance(node, ast.Name):
            return self._name(node, scope, expected)
        if isinstance(node, ast.Unary):
            return self._unary(node, scope)
        if isinstance(node, ast.Binary):
            if node.operator in EQUALITY and self._is_none_constant(node.right, scope):
                # `None` is an Option with no value: in a comparison, the other side says
                # which Option it is, so `x == None` has a type to work with.
                left = self._expression(node.left, scope)
                right = self._expression(node.right, scope, left)
            elif node.operator in EQUALITY and self._is_none_constant(node.left, scope):
                right = self._expression(node.right, scope)
                left = self._expression(node.left, scope, right)
            else:
                left = self._expression(node.left, scope)
                # The left side is an expected type for an empty list on the right: `[1] == []`.
                right_expected = left if isinstance(node.right, ast.ListLiteral) and not node.right.elements else None
                right = self._expression(node.right, scope, right_expected)
            if left is None or right is None:
                return None
            # A refined value takes part in operations as a value of its base type: the result of
            # Percent + Percent is an Int, which may well be outside the range of Percent.
            result = self._binary_result(node.operator, self._root(left), self._root(right))
            if result is None:
                self._report(
                    "E2011",
                    f"Cannot apply '{node.operator}' to {left} and {right}",
                    node.operator_span,
                    hint=_binary_hint(node.operator, self._root(left), self._root(right)),
                )
            return result
        return self._call(node, scope, expected)

    def _variant_pattern_info(self, pattern: ast.VariantPattern, expected: str) -> tuple[str, tuple[tuple[str, str], ...]] | None:
        """Resolve a variant pattern against the scrutinee's closed type."""
        model = self._current_type_model(expected)
        enum_name = expected
        variants: dict[str, tuple[tuple[str, str], ...]] = {}
        if isinstance(model, type_model.Application) and model.constructor.identity == type_model.OPTION.identity:
            enum_name = "Option"
            variants = {"None": (), "Some": (("value", type_model.display(model.arguments[0])),)}
        elif isinstance(model, type_model.Application) and model.constructor.identity == type_model.RESULT.identity:
            enum_name = "Result"
            variants = {"Ok": (("value", type_model.display(model.arguments[0])),),
                        "Err": (("error", type_model.display(model.arguments[1])),)}
        elif expected in self._enums:
            variants = {variant.name: variant.fields for variant in self._enums[expected].variants}
        else:
            self._report("E2033", f"A variant pattern cannot match a value of type {expected}", pattern.span,
                         hint="Match a value whose type is an enum, Option, or Result.")
            return None

        if pattern.qualifier is not None:
            written_enum = self._key(pattern.qualifier)
            if written_enum != enum_name:
                self._report("E2033", f"'{pattern.qualifier}.{pattern.name}' is not a variant of {expected}",
                             pattern.span)
                return None
        fields = variants.get(pattern.name)
        if fields is None:
            self._report("E2033", f"'{pattern.name}' is not a variant of {expected}", pattern.name_span,
                         hint=f"The variants are: {', '.join(variants)}.")
            return None
        if len(pattern.arguments) != len(fields):
            self._report("E2033", f"'{pattern.name}' takes {len(fields)} pattern argument(s), "
                         f"but {len(pattern.arguments)} were given", pattern.span)
            return None
        key = f"{enum_name}.{pattern.name}"
        self._targets[id(pattern)] = key
        return key, fields

    def _check_pattern(self, pattern: ast.Pattern, expected: str, scope: _Scope) -> str | None:
        """Type-check a pattern and bind its names in the arm's fresh scope."""
        if isinstance(pattern, ast.WildcardPattern):
            return None
        if isinstance(pattern, ast.BindingPattern):
            if self._name_is_free(pattern.name, pattern.name_span, scope):
                self._declare(scope, pattern.name, "pattern variable", expected, pattern.name_span)
            return None
        if isinstance(pattern, ast.LiteralPattern):
            found = BOOL if isinstance(pattern.value, bool) else INT if isinstance(pattern.value, int) \
                else FLOAT if isinstance(pattern.value, float) else TEXT
            if not self._accepts(expected, found):
                self._report("E2011", f"Expected {expected}, found {found}", pattern.span)
            return None
        resolved = self._variant_pattern_info(pattern, expected)
        if resolved is None:
            return None
        _, fields = resolved
        for child, (_, field_type) in zip(pattern.arguments, fields, strict=True):
            self._check_pattern(child, field_type, scope)
        return self._targets.get(id(pattern))

    @staticmethod
    def _catchall_pattern(pattern: ast.Pattern | None) -> bool:
        return pattern is None or isinstance(pattern, (ast.WildcardPattern, ast.BindingPattern))

    def _finite_constructors(self, kind: str) -> list[tuple[str, str, tuple[tuple[str, str], ...]]]:
        """Finite constructors of a type. Open domains deliberately return no constructors."""
        model = self._current_type_model(kind)
        root = type_model.root(model) if model is not None else None
        if root is not None and type_model.equal(root, type_model.BOOL):
            return [("Bool.true", "true", ()), ("Bool.false", "false", ())]
        if isinstance(model, type_model.Application) and model.constructor.identity == type_model.OPTION.identity:
            return [("Option.None", "None", ()),
                    ("Option.Some", "Some", (("value", type_model.display(model.arguments[0])),))]
        if isinstance(model, type_model.Application) and model.constructor.identity == type_model.RESULT.identity:
            return [("Result.Ok", "Ok", (("value", type_model.display(model.arguments[0])),)),
                    ("Result.Err", "Err", (("error", type_model.display(model.arguments[1])),))]
        enum = self._enums.get(kind)
        if enum is not None:
            return [(f"{kind}.{variant.name}", variant.name, variant.fields) for variant in enum.variants]
        return []

    @staticmethod
    def _pattern_key(pattern: ast.Pattern, kind: str) -> str | None:
        if isinstance(pattern, ast.VariantPattern):
            return None
        if isinstance(pattern, ast.LiteralPattern):
            if isinstance(pattern.value, bool):
                return f"Bool.{str(pattern.value).lower()}"
            return f"{kind}::{pattern.value!r}"
        return None

    def _pattern_constructor(self, pattern: ast.Pattern | None, kind: str):
        if pattern is None:
            return None
        constructors = self._finite_constructors(kind)
        if isinstance(pattern, ast.VariantPattern):
            key = self._targets.get(id(pattern))
            return next((item for item in constructors if item[0] == key), None)
        key = self._pattern_key(pattern, kind)
        return next((item for item in constructors if item[0] == key), None)

    def _specialize_patterns(self, matrix, key: str, arity: int, kind: str):
        rows = []
        for row in matrix:
            head, *tail = row
            if self._catchall_pattern(head):
                rows.append([None] * arity + tail)
                continue
            constructor = self._pattern_constructor(head, kind)
            if constructor is not None and constructor[0] == key:
                arguments = list(head.arguments) if isinstance(head, ast.VariantPattern) else []
                rows.append(arguments + tail)
        return rows

    def _is_exhaustive(self, matrix, kinds: list[str]) -> bool:
        if not kinds:
            return bool(matrix)
        kind, *tail_kinds = kinds
        constructors = self._finite_constructors(kind)
        if constructors:
            present = {constructor[0] for row in matrix
                       if (constructor := self._pattern_constructor(row[0], kind)) is not None}
            finite_keys = {constructor[0] for constructor in constructors}
            if finite_keys.issubset(present):
                for key, _, fields in constructors:
                    specialized = self._specialize_patterns(matrix, key, len(fields), kind)
                    if not self._is_exhaustive(specialized, [field for _, field in fields] + tail_kinds):
                        return False
                return True
        defaults = [row[1:] for row in matrix if self._catchall_pattern(row[0])]
        return self._is_exhaustive(defaults, tail_kinds)

    def _useful_pattern(self, matrix, vector: list[ast.Pattern | None], kinds: list[str]) -> bool:
        if not kinds:
            return not matrix
        kind, *tail_kinds = kinds
        pattern, *tail = vector
        if self._catchall_pattern(pattern):
            constructors = self._finite_constructors(kind)
            present = {constructor[0] for row in matrix
                       if (constructor := self._pattern_constructor(row[0], kind)) is not None}
            finite_keys = {constructor[0] for constructor in constructors}
            if constructors and finite_keys.issubset(present):
                for key, _, fields in constructors:
                    specialized = self._specialize_patterns(matrix, key, len(fields), kind)
                    if self._useful_pattern(specialized, [None] * len(fields) + tail,
                                            [field for _, field in fields] + tail_kinds):
                        return True
                return False
            defaults = [row[1:] for row in matrix if self._catchall_pattern(row[0])]
            return self._useful_pattern(defaults, tail, tail_kinds)

        constructor = self._pattern_constructor(pattern, kind)
        if constructor is not None:
            key, _, fields = constructor
            arguments = list(pattern.arguments) if isinstance(pattern, ast.VariantPattern) else []
            specialized = self._specialize_patterns(matrix, key, len(fields), kind)
            return self._useful_pattern(specialized, arguments + tail, [field for _, field in fields] + tail_kinds)

        # Literal patterns over open types are useful unless that exact literal or a wildcard was
        # already covered. They never make an infinite domain exhaustive.
        literal_key = self._pattern_key(pattern, kind)
        specialized = []
        for row in matrix:
            head, *rest = row
            if self._catchall_pattern(head) or self._pattern_key(head, kind) == literal_key:
                specialized.append(rest)
        return self._useful_pattern(specialized, tail, tail_kinds)

    def _missing_pattern(self, matrix, kinds: list[str]) -> list[str] | None:
        if not kinds:
            return [] if not matrix else None
        kind, *tail_kinds = kinds
        constructors = self._finite_constructors(kind)
        if constructors:
            for key, display, fields in constructors:
                specialized = self._specialize_patterns(matrix, key, len(fields), kind)
                witness = self._missing_pattern(specialized, [field for _, field in fields] + tail_kinds)
                if witness is not None:
                    args = witness[:len(fields)]
                    head = display if not args else f"{display}({', '.join(args)})"
                    return [head, *witness[len(fields):]]
            return None
        defaults = [row[1:] for row in matrix if self._catchall_pattern(row[0])]
        witness = self._missing_pattern(defaults, tail_kinds)
        return None if witness is None else ["_", *witness]

    def _match_expression(self, node: ast.MatchExpr, scope: _Scope, expected: str | None) -> str | None:
        scrutinee = self._expression(node.value, scope)
        if scrutinee is None:
            for arm in node.arms:
                self._check_pattern(arm.pattern, "<unknown>", _Scope(scope))
            return None

        matrix = []
        result_type = expected
        failed = False
        for arm in node.arms:
            arm_scope = _Scope(scope)
            self._check_pattern(arm.pattern, scrutinee, arm_scope)
            if not self._useful_pattern(matrix, [arm.pattern], [scrutinee]):
                self._report("E2034", "This arm can never be reached", arm.pattern.span)
            matrix.append([arm.pattern])

            if isinstance(arm.body, ast.Block):
                self._block(arm.body, arm_scope)
                found = VOID
            else:
                found = self._expression(arm.body, arm_scope, expected if result_type is None else result_type)
            if found is None:
                failed = True
                continue
            if result_type is None:
                result_type = found
            elif not self._accepts(result_type, found):
                self._report("E2011", f"Expected {result_type}, found {found}", arm.body.span,
                             notes=("Every arm of a match expression must produce the same type.",))
                failed = True

        if not self._is_exhaustive(matrix, [scrutinee]):
            witness = self._missing_pattern(matrix, [scrutinee]) or ["_"]
            self._report("E2032", f"This match does not cover: {', '.join(witness)}", node.span,
                         hint="Add an arm for the missing pattern, or a final '_' arm.")
        return None if failed else result_type

    def _list_item(self, expected: str | None) -> str | None:
        """The element type an expected list type fixes, or None if it fixes none."""
        model = self._current_type_model(expected)
        if isinstance(model, type_model.Application) and model.constructor.identity == type_model.LIST.identity:
            return type_model.display(model.arguments[0])
        return None

    def _list_literal(self, node: ast.ListLiteral, scope: _Scope, expected: str | None) -> str | None:
        """The type of `[a, b]`, or None if an element is invalid or an empty list is ambiguous.

        The first element (or the expected type) fixes the element type. Every other
        element has to be usable as that type; generic arguments are invariant, so a
        `List[Percent]` is not a `List[Int]` merely because `Percent` widens to `Int`.
        An empty list needs an expected `List[T]` to know `T`.
        """
        item = self._list_item(expected)
        if not node.elements:
            if item is None:
                self._report(
                    "E2011",
                    "Cannot infer the type of an empty list without an expected type",
                    node.span,
                    hint="Write the type of its elements, for example: let xs: List[Int] = [].",
                )
                return None
            return f"List[{item}]"

        invalid = False
        for element in node.elements:
            found = self._expression(element, scope, item)
            if found is None:
                invalid = True
                continue
            if found == VOID:
                self._report("E2011", "This call does not produce a value to put in a list", element.span)
                invalid = True
                continue
            if item is None:
                item = found
                continue
            if not self._accepts(item, found):
                self._report(
                    "E2011",
                    f"Expected {item}, found {found}",
                    element.span,
                    hint=f"Every element of a list has the same type: {item}.",
                    notes=(f"The first element of this list is {item}.",) if expected is None else (),
                )
                invalid = True
        if invalid or item is None:
            return None
        return f"List[{item}]"

    def _binary_result(self, operator: str, left: str, right: str) -> str | None:
        """The type of `left operator right`, or None if the operation is not defined.

        `left` and `right` arrive already rooted by `_infer`. The decision uses the identity
        and value-type rules of the D01 model with the operator categories that already exist;
        a name outside the model keeps the legacy string result unchanged. `assignable` is
        deliberately not used: both operands must be the same exact type, with no implicit
        promotion. A list is a value type, so `==` and `!=` are defined for it.
        """
        left_model = self._current_type_model(left)
        right_model = self._current_type_model(right)
        if left_model is None or right_model is None:
            return binary_result(operator, left, right)
        if not type_model.is_value_type(left_model) or not type_model.equal(left_model, right_model):
            return None
        if operator in LOGICAL:
            return BOOL if type_model.equal(left_model, type_model.BOOL) else None
        if operator in EQUALITY:
            return BOOL
        if operator in ORDERING:
            if (type_model.equal(left_model, type_model.INT)
                    or type_model.equal(left_model, type_model.FLOAT)
                    or type_model.equal(left_model, type_model.TEXT)):
                return BOOL
            return None
        if type_model.equal(left_model, type_model.INT) or type_model.equal(left_model, type_model.FLOAT):
            return type_model.display(left_model)
        if type_model.equal(left_model, type_model.TEXT) and operator == "+":
            return TEXT
        return None

    def _name(self, node: ast.Name, scope: _Scope, expected: str | None = None) -> str | None:
        found = scope.find(node.name)
        if found is not None:
            found.references.append(node.span)
            found.reference_modules.append(self._module)
            found.reads.append(node.span)
            return found.type
        if self._key(node.name) in self._type_names or self._key(node.name) in self._enum_names:
            self._report(
                "E2011",
                f"'{node.name}' is a type, not a value",
                node.span,
                hint=f"To check a refined value use {node.name}(x); to build an enum use {node.name}.Variant(...).",
            )
        elif self._key(node.name) in self._record_names:
            self._report(
                "E2011",
                f"'{node.name}' is a type, not a value",
                node.span,
                hint=f"To build one, write it: {node.name}(field: value)",
            )
        elif node.name in BUILTINS or self._key(node.name) in self._signatures:
            self._report(
                "E2011",
                f"'{node.name}' is a function, not a value",
                node.span,
                hint=f"Call it with parentheses: {node.name}(...)",
            )
        elif node.name == NONE:
            # `None` is the absence of a value: an Option without a payload. The type of its
            # item comes from the context that expects it.
            return self._none_type(node, expected)
        else:
            self._unknown_variable(node.name, node.span, scope)
        return None

    def _is_none_constant(self, node: ast.Expr, scope: _Scope) -> bool:
        """Whether the expression is the `None` constant and not a variable of the program."""
        return isinstance(node, ast.Name) and node.name == NONE and scope.find(NONE) is None

    def _none_type(self, node: ast.Name, expected: str | None) -> str | None:
        """The type of `None`: an Option with no payload, whose item type the context fixes."""
        if expected is None:
            self._report(
                "E2011",
                "Cannot infer the type of None without an expected type",
                node.span,
                hint="Write the type of the option explicitly, for example: let x: Option[Int] = None.",
            )
            return None
        model = self._current_type_model(expected)
        if isinstance(model, type_model.Application) and model.constructor.identity == type_model.OPTION.identity:
            return expected
        self._report(
            "E2011",
            f"Expected {expected}, found None",
            node.span,
            hint="None is an Option without a value: it needs a type of the form Option[Text].",
        )
        return None

    def _unary(self, node: ast.Unary, scope: _Scope) -> str | None:
        found = self._expression(node.operand, scope)
        if found is None:
            return None
        operand = self._root(found)
        # A representable operand is decided with the model. `None` means a name outside it
        # (`ANY_VALUE`, unknown names, unenabled generics, dropped refinements), which neither
        # operator accepts, so the legacy diagnostics are kept unchanged.
        operand_model = self._current_type_model(operand)
        if node.operator == "-":
            if operand_model is not None and (
                type_model.equal(operand_model, type_model.INT)
                or type_model.equal(operand_model, type_model.FLOAT)
            ):
                return type_model.display(operand_model)
            self._report("E2011", f"Cannot apply '-' to {operand}", node.span, hint="'-' negates an Int or a Float.")
            return None
        if operand_model is not None and type_model.equal(operand_model, type_model.BOOL):
            return BOOL
        hint = "'not' negates a Bool."
        if operand_model is not None and (
            type_model.equal(operand_model, type_model.INT)
            or type_model.equal(operand_model, type_model.FLOAT)
        ):
            hint += " To negate a comparison, put it in parentheses: not (a == b)"
        self._report("E2011", f"Cannot apply 'not' to {operand}", node.span, hint=hint)
        return None

    def _argument_expectations(self, node: ast.Call) -> list[str | None]:
        """The type each argument is checked against, before the arguments are read.

        Only a resolved signature or a refined-type check fixes one; `ANY_VALUE` fixes
        nothing. The empty list uses it to learn its element type, as in `take([])`.
        """
        missing = [None] * len(node.arguments)
        key = self._key(node.callee)
        if key in self._type_names:
            return missing
        if (node.qualifier is not None and node.callee not in BUILTINS
                and key not in self._signatures):
            # A function of a type, not of a module: its arguments have no expectation.
            return missing
        signature = BUILTINS.get(node.callee) or self._signatures.get(key)
        if signature is None:
            return missing
        if signature.parametric is not None:
            # A parameter that still mentions a type variable has no concrete type to
            # offer: `List.append([], 1)` needs a list whose element type is written.
            # A concrete parameter, such as the index of List.get, is used as usual.
            return [
                None
                if index >= len(signature.parametric.params)
                or _contains_type_variable(signature.parametric.params[index][1])
                else type_model.display(signature.parametric.params[index][1])
                for index in range(len(node.arguments))
            ]
        return [
            None if index >= len(signature.params) or signature.params[index][1] == ANY_VALUE
            else signature.params[index][1]
            for index in range(len(node.arguments))
        ]

    def _call(self, node: ast.Call, scope: _Scope, expected: str | None = None) -> str | None:
        if node.qualifier is not None:
            enum_key = node.callee.rsplit(".", 1)[0] if node.callee.count(".") > 1 else self._key(node.qualifier)
            if enum_key in self._enum_names:
                return self._enum_construction(node, enum_key, scope)
        key = self._key(node.callee)
        if (node.qualifier is not None and node.callee not in BUILTINS
                and key not in self._signatures and key not in self._type_names and key not in self._enum_names):
            # `Name.function(...)`: the name is not a function, nor a type the module
            # declares, so it can only be a function of a type (decision 0011, 9).
            self._unknown_qualified_call(node, scope)
            return None
        expectations = self._argument_expectations(node)
        argument_types = [
            self._expression(argument, scope, expected)
            for argument, expected in zip(node.arguments, expectations, strict=True)
        ]
        if key in self._type_names:
            if not self._is_public(key):
                self._private(key, node.callee_span)
                return None
            return self._refinement_check(node, argument_types)
        if self._refining is not None and key in self._function_names and node.callee not in BUILTINS:
            self._report(
                "E2018",
                f"The condition of '{self._refining}' cannot call the function '{node.callee}'",
                node.callee_span,
                hint="A refinement only describes the value itself: it can use operators, literals and the "
                     "built-in conversions. Write the rule there, or check it with 'needs'.",
            )
            return None
        signature = BUILTINS.get(node.callee) or self._signatures.get(key)

        if signature is None:
            if scope.find(node.callee) is not None:
                self._report("E2008", f"'{node.callee}' is a variable, not a function", node.callee_span)
            else:
                self._report("E2008", f"There is no function named '{node.callee}'", node.callee_span,
                             hint=self._function_hint(node.callee))
            return None
        if not signature.builtin and not self._is_public(key):
            # A function of another module that is not marked with `pub`.
            self._private(key, node.callee_span)
            return None

        # The call is resolved: it is recorded even if its arguments turn out to be wrong. A call
        # written in an example is a reference to the function, but not an edge of the call graph:
        # the function does not make that call when it runs (decision 0008, section 2).
        if self._in_example is None:
            # Both ends are qualified with their module: two modules can declare one
            # function with the same name, and the call graph has to tell them apart
            # (decision 0018, 5).
            self._calls.append((self._key(self._function_name), key))
        if not signature.builtin:
            self._function_symbols[key].references.append(node.callee_span)
            self._function_symbols[key].reference_modules.append(self._module)
            self._targets[id(node)] = key

        expected_count, count = len(signature.params), len(node.arguments)
        if count != expected_count:
            self._report(
                "E2009",
                f"'{signature.name}' takes {expected_count} argument{'' if expected_count == 1 else 's'}, "
                f"but {count} {'was' if count == 1 else 'were'} given",
                node.span,
                notes=(f"Its signature is: {signature.describe()}",),
            )
            # A parametric result such as 'T' is not a type until a call binds it, so
            # there is nothing safe to report as the type of this failed call.
            return None if signature.parametric is not None else signature.return_type

        if node.callee in CAPABILITY_FUNCTIONS:
            self._check_capability(node)

        if signature.parametric is not None:
            return self._parametric_call(node, argument_types, signature, expected)

        checked_arguments = zip(node.arguments, argument_types, signature.params, strict=True)
        for argument, found, (param_name, expected) in checked_arguments:
            if found is None or expected is None:
                continue
            if found == VOID:
                self._report("E2011", "This call does not produce a value to pass as an argument", argument.span)
            elif expected != ANY_VALUE:
                self._expect_type(expected, found, argument,
                                  (f"This is the argument for '{param_name}' in: {signature.describe()}",))
        return signature.return_type

    def _enum_construction(self, node: ast.Call, enum_name: str, scope: _Scope) -> str | None:
        enum = self._enums.get(enum_name)
        if enum is None:
            return None
        variant_name = node.callee.rsplit(".", 1)[-1]
        variant = next((candidate for candidate in enum.variants if candidate.name == variant_name), None)
        if variant is None:
            self._report("E2035", f"'{variant_name}' is not a variant of {enum_name}", node.callee_span,
                         hint=f"The variants are: {', '.join(item.name for item in enum.variants)}.")
            return None
        if not self._is_public(enum_name):
            self._private(enum_name, node.callee_span)
            return None
        if len(node.arguments) != len(variant.fields):
            self._report("E2035", f"'{enum_name}.{variant_name}' takes {len(variant.fields)} argument(s), "
                         f"but {len(node.arguments)} were given", node.span)
        for index, argument in enumerate(node.arguments):
            kind = variant.fields[index][1] if index < len(variant.fields) else None
            found = self._expression(argument, scope, kind)
            if found is not None and kind is not None:
                self._expect_type(kind, found, argument,
                                  (f"This is the payload for '{enum_name}.{variant_name}'.",))
        self._targets[id(node)] = f"{enum_name}.{variant_name}"
        return enum_name

    def _parametric_call(self, node: ast.Call, argument_types: list[str | None],
                         signature: Signature, expected_result: str | None = None) -> str | None:
        """Checks a call to a built-in whose signature mentions type variables.

        Each argument is unified, in order, with its parameter type. Later parameters
        see what earlier ones bound, and the result is the return type after the same
        substitution. When a parameter is already concrete, the ordinary assignment
        rule applies, so a refined element can still widen to its base type.

        The type the context expects is unified first: it fixes the variables that no
        argument can, such as the error type of an `Ok` or the item type of an `Err`.
        """
        parametric = signature.parametric
        if parametric is None:
            raise TypeError(f"'{signature.name}' is not a parametric signature")

        mapping: dict[int, type_model.Type] = {}
        invalid = False
        checked_arguments = zip(node.arguments, argument_types, parametric.params, strict=True)
        for argument, found, (param_name, declared) in checked_arguments:
            if found is None:
                invalid = True
                continue
            if found == VOID:
                self._report("E2011", "This call does not produce a value to pass as an argument", argument.span)
                invalid = True
                continue
            found_model = self._current_type_model(found)
            if found_model is None:
                # A checked expression always has a representable type. A name outside
                # the model cannot be unified, so it is reported as the mismatch it is.
                self._report(
                    "E2011",
                    f"Expected {type_model.display(declared)}, found {found}",
                    argument.span,
                    notes=(f"This is the argument for '{param_name}' in: {signature.describe()}",),
                )
                invalid = True
                continue

            expected = type_model.substitute(declared, mapping)
            if _contains_type_variable(expected):
                unified = type_model.unify(expected, found_model, mapping)
                if unified is None:
                    self._report(
                        "E2011",
                        f"Expected {type_model.display(expected)}, found {found}",
                        argument.span,
                        hint="A list accepts only one element type: List[Int] and List[Text] are different types.",
                        notes=(f"This is the argument for '{param_name}' in: {signature.describe()}",),
                    )
                    invalid = True
                else:
                    mapping = unified
                continue

            before = len(self._diagnostics)
            self._expect_type(
                type_model.display(expected), found, argument,
                (f"This is the argument for '{param_name}' in: {signature.describe()}",),
            )
            if len(self._diagnostics) != before:
                invalid = True

        if invalid:
            return None
        result = type_model.substitute(parametric.return_type, mapping)
        # The type the context expects binds what the arguments could not: the error type of
        # an `Ok`, the item type of an `Err`. It is used only for what is still free, so a
        # call whose arguments already decide keeps deciding the same.
        if expected_result is not None and _contains_type_variable(result):
            expected_model = self._current_type_model(expected_result)
            if expected_model is not None:
                unified = type_model.unify(result, expected_model, mapping)
                if unified is None:
                    self._report(
                        "E2011",
                        f"Expected {expected_result}, found {type_model.display(result)}",
                        node.span,
                        hint=f"This is the result of: {signature.describe()}",
                    )
                    return None
                mapping = unified
                result = type_model.substitute(parametric.return_type, mapping)
        if _contains_type_variable(result):
            what, hint = _UNINFERABLE.get(
                signature.name,
                ("Cannot infer the type of the elements of this list",
                 "Write the type of the list explicitly, for example: let xs: List[Int] = []."),
            )
            self._report("E2011", what, node.span, hint=hint)
            return None
        return type_model.display(result)

    def _function_hint(self, callee: str) -> str | None:
        """The suggestion for a call to a function that does not exist. A name that is a function of
        a type, written without it ("length"), suggests the qualified name first (decision 0011, 9)."""
        def qualified(member: str) -> list[str]:
            return sorted(name for name in BUILTINS if "." in name and name.split(".")[1] == member)

        def suggest(names: list[str]) -> str:
            return "Did you mean " + " or ".join(f"'{name}'" for name in names) + "?"

        if qualified(callee):
            return suggest(qualified(callee))
        plain = [*self._visible(self._signatures), *(name for name in BUILTINS if "." not in name)]
        close = difflib.get_close_matches(callee, plain, n=1)
        if close:
            return suggest(close)
        members = sorted({name.split(".")[1] for name in BUILTINS if "." in name})
        close = difflib.get_close_matches(callee, members, n=1)
        return suggest(qualified(close[0])) if close else None

    def _unknown_qualified_call(self, node: ast.Call, scope: _Scope) -> None:
        """`Name.function(...)` where Name is neither a type with that function nor a module
        that makes one public (decisions 0011, 9 and 0018, 2)."""
        qualifier = node.qualifier
        function = node.callee.split(".", 1)[1]
        hint: str | None = None
        notes: tuple[str, ...] = ()
        symbol = scope.find(qualifier)
        if qualifier in self._modules:
            public = sorted(key.split(".", 1)[1] for key in self._public if key.startswith(f"{qualifier}."))
            close = difflib.get_close_matches(function, public, n=1)
            label = f"The module '{qualifier}' has no function named '{function}'"
            if close:
                hint = f"Did you mean '{qualifier}.{close[0]}'?"
            elif public:
                notes = (f"The functions '{qualifier}' makes public: {', '.join(public)}.",)
            else:
                notes = (f"The module '{qualifier}' makes no function public: it declares none with 'pub'.",)
        elif qualifier in KNOWN_TYPES or qualifier == type_model.LIST.name:
            label = f"'{qualifier}' has no function named '{function}'"
            functions = TYPE_FUNCTIONS.get(qualifier, [])
            if functions:
                close = difflib.get_close_matches(function, functions, n=1)
                hint = f"Did you mean '{qualifier}.{close[0]}'?" if close else None
                notes = (f"The functions of {qualifier}: {', '.join(functions)}.",)
            else:
                notes = (f"{qualifier} has no functions yet.",)
        elif (self._key(qualifier) in self._type_names or self._key(qualifier) in self._record_names
              or self._key(qualifier) in self._enum_names):
            label = f"'{qualifier}' has no functions of its own"
            base = self._root(qualifier)
            if TYPE_FUNCTIONS.get(base):
                hint = f"A value of {qualifier} can be passed to the functions of its base type, {base}."
        elif symbol is not None:
            label = f"'{qualifier}' is a {symbol.category}: values have no functions of their own"
            base = self._root(symbol.type) if symbol.type is not None else None
            if function in TYPE_FUNCTIONS.get(base, []):
                hint = f"Call the function of its type: {base}.{function}({qualifier})"
        elif qualifier in BUILTINS or self._key(qualifier) in self._signatures:
            label = f"'{qualifier}' is a function, not a type"
        else:
            if qualifier[:1].islower():
                # A type always starts with a capital letter, so a name before the '.' that
                # starts with a lower case one can only be a module (decision 0018, 2).
                self._unknown_module(qualifier, node.callee_span)
                return
            label = f"There is no type named '{qualifier}'"
            close = difflib.get_close_matches(
                qualifier,
                [*KNOWN_TYPES, type_model.LIST.name, *self._visible(self._type_names),
                 *self._visible(self._record_names), *self._visible(self._enum_names)],
                n=1,
            )
            hint = f"Did you mean '{close[0]}'?" if close else None
        self._report("E2008", label, node.callee_span, hint=hint, notes=notes)

    def _refinement_check(self, node: ast.Call, argument_types: list[str | None]) -> str | None:
        """`Percent(x)`: checks, when the program runs, that x satisfies the condition of Percent."""
        name = node.callee
        if self._refining is not None:
            self._report(
                "E2018",
                f"The condition of '{self._refining}' cannot check a value against '{name}'",
                node.callee_span,
                hint=f"To build on '{name}', refine it: type {self._refining} = {name} where ...",
            )
            return None
        refined = self._refined.get(self._key(name))
        if refined is not None:
            # The interpreter runs the check on this one; a module writes it with its own
            # bare name, and only the analysis knows which one it is (decision 0018, 5).
            self._targets[id(node)] = self._key(name)
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
        else:
            # Both roots are resolved before deciding, so a representable root missing from
            # the model raises even when the other root is outside it. `None` means a name
            # outside the model, which is not a matching root.
            found_root_model = self._current_type_model(self._root(found))
            expected_root_model = self._current_type_model(refined.root)
            if (
                found_root_model is None
                or expected_root_model is None
                or not type_model.equal(found_root_model, expected_root_model)
            ):
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


def check(program: ast.Program, *, require_main: bool = True) -> tuple[CheckedProgram, list[Diagnostic]]:
    """Checks a program. `require_main=False` is only for `nex test`, which runs examples, not 'main'."""
    checker = Checker()
    checker.require_main = require_main
    return checker.check(program)


def _loops(node) -> list[ast.While | ast.For]:
    """The loops inside a block, at any depth, in the order they are written."""
    found: list[ast.While | ast.For] = []
    if isinstance(node, ast.Block):
        for statement in node.statements:
            found.extend(_loops(statement))
    elif isinstance(node, (ast.While, ast.For)):
        found.append(node)
        found.extend(_loops(node.body))
    elif isinstance(node, ast.If):
        found.extend(_loops(node.then_block))
        if node.else_branch is not None:
            found.extend(_loops(node.else_branch))
    return found

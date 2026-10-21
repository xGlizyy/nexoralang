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
from dataclasses import dataclass, field, fields

from . import ast_nodes as ast
from . import types as type_model
from .diagnostics import MAX_DIAGNOSTICS, Diagnostic, NexoraRuntimeError, Span
from .type_adapter import TypeAdapter
from .values import BOOL, FLOAT, INT, TEXT, VALUE_TYPES, VOID

KNOWN_TYPES = (VOID, *VALUE_TYPES)

# Parameter "type" of the built-in functions that accept a value of any type.
ANY_VALUE = "Int | Float | Bool | Text"

# The most work the analysis may spend checking constants against refined types, counted as the
# nodes of the conditions it evaluates. Checking one constant costs the size of every condition in
# its type's chain, so without a bound the work would grow with types x conditions x constants.
# Ordinary programs stay far below it; a program above it is rejected (E2019), never half-checked.
MAX_REFINEMENT_STEPS = 100_000

ARITHMETIC = ("+", "-", "*", "/")
EQUALITY = ("==", "!=")
ORDERING = ("<", "<=", ">", ">=")
LOGICAL = ("and", "or")


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
        return f"fn {self.name}({params}) -> {self.return_type or '?'}"


# The item variable shared by the signatures of the functions of List. `unify` returns a
# fresh mapping for each call, so the same variable can be reused without keeping state.
_LIST_ITEM = type_model.TypeVariable(0, "T")


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
    )
}

# The functions of each built-in type, by type: {"Text": ["contains", ...], ...}.
TYPE_FUNCTIONS: dict[str, list[str]] = {}
for _name in sorted(BUILTINS):
    if "." in _name:
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
    # True only for a variable declared with 'var'.
    mutable: bool = False
    # True for the iterator a 'for' loop declares: it is immutable for its own reason.
    loop_variable: bool = False
    # Where the variable is given a new value. Each of these is also in `references`.
    assignments: list[Span] = field(default_factory=list)


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
    def __init__(self) -> None:
        self._diagnostics: list[Diagnostic] = []
        self._signatures: dict[str, Signature] = {}
        self._types: dict[int, str] = {}
        self._symbols: list[Symbol] = []
        self._function_symbols: dict[str, Symbol] = {}
        self._calls: list[tuple[str, str]] = []
        # Every declared type name, including those whose declaration has an error.
        self._type_names: dict[str, ast.TypeDecl] = {}
        self._refined: dict[str, RefinedType] = {}
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

    def check(self, program: ast.Program) -> tuple[CheckedProgram, list[Diagnostic]]:
        """Checks a program. The CheckedProgram may only be run when the list is empty."""
        declared: dict[str, ast.Function] = {}
        try:
            self._check_program(program, declared)
        except _TooManyErrors:
            pass
        checked = CheckedProgram(
            program, declared, self._types, tuple(self._symbols), tuple(self._calls), dict(self._refined),
        )
        return checked, self._diagnostics

    def _check_program(self, program: ast.Program, declared: dict[str, ast.Function]) -> None:
        # Types first: any signature or annotation may name one, wherever it is declared. Their
        # conditions are checked before the signatures, so that a type whose condition is wrong is
        # already unusable when a signature names it: its error is reported once, not at every use.
        self._declare_types(program.types)
        self._function_names = {function.name for function in program.functions}
        for declaration in program.types:
            self._type_condition(declaration)
        own_signatures: list[tuple[ast.Function, Signature]] = []

        # Signatures first: a function can be called before the line that declares it.
        for function in program.functions:
            signature = self._signature(function)
            own_signatures.append((function, signature))
            if function.name in BUILTINS:
                self._report(
                    "E2002",
                    f"'{function.name}' is a built-in function and cannot be declared again",
                    function.name_span,
                    hint="Choose a different name for this function.",
                )
            elif function.name in self._type_names:
                self._report(
                    "E2006",
                    f"'{function.name}' is the name of a type and cannot be used for a function",
                    function.name_span,
                    hint=f"{function.name}(x) already means: check that x is a valid {function.name}.",
                )
            elif function.name in declared:
                first = declared[function.name].name_span
                self._report(
                    "E2002",
                    f"The function '{function.name}' is declared more than once",
                    function.name_span,
                    notes=(f"It was first declared at line {first.line}, column {first.column}.",),
                )
            else:
                declared[function.name] = function
                self._signatures[function.name] = signature
                symbol = Symbol(function.name, "function", signature.return_type, function.name_span, None, None)
                self._function_symbols[function.name] = symbol
                self._symbols.append(symbol)

        if self.require_main or "main" in declared:
            self._main(declared.get("main"))
        for function, signature in own_signatures:
            self._function(function, signature)

    # Refined types

    def _declare_types(self, declarations: tuple[ast.TypeDecl, ...]) -> None:
        """Registers the type names, then resolves what each one refines."""
        for declaration in declarations:
            name, span = declaration.name, declaration.name_span
            if name in KNOWN_TYPES:
                self._report("E2016", f"'{name}' is a built-in type and cannot be declared again", span,
                             hint="Choose a different name for this type.")
            elif not name[0].isupper():
                self._report("E2016", f"The type name '{name}' must start with a capital letter", span,
                             hint=f"Write it as: {name[0].upper()}{name[1:]}")
            elif name in self._type_names:
                first = self._type_names[name].name_span
                self._report("E2016", f"The type '{name}' is declared more than once", span,
                             notes=(f"It was first declared at line {first.line}, column {first.column}.",))
            else:
                self._type_names[name] = declaration

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
        base_name = declaration.base.name
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
        current = self._type_names[name].base.name
        while current in self._type_names and current not in seen:
            if current == name:
                return True
            seen.add(current)
            current = self._type_names[current].base.name
        return False

    def _type_condition(self, declaration: ast.TypeDecl) -> None:
        """Checks the condition after 'where'. Only `value` is visible in it, and it calls no
        function of the program: a refinement is a fact about one value and nothing else."""
        refined = self._refined.get(declaration.name)
        if refined is None or self._type_names.get(declaration.name) is not declaration:
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

    # Declarations

    def _value_type(self, reference: ast.TypeRef, what: str) -> str | None:
        """The type named by `reference`, which must be a type a value can have."""
        if reference.name == VOID:
            self._report(
                "E2012",
                f"{what} cannot have the type Void",
                reference.span,
                hint="Void means 'no value'. It can only be the return type of a function.",
            )
            return None
        return self._known_type(reference)

    def _known_type(self, reference: ast.TypeRef) -> str | None:
        if reference.arguments:
            if reference.name != "List":
                self._report(
                    "E2012",
                    f"'{reference.name}' cannot take type arguments",
                    reference.span,
                    hint="Only 'List' takes a type argument in this version: List[Int].",
                )
                return None
            if len(reference.arguments) != 1:
                self._report(
                    "E2012",
                    f"'List' takes exactly one type argument, but {len(reference.arguments)} were given",
                    reference.span,
                    hint="Write List[Int].",
                )
                return None
            element = self._value_type(reference.arguments[0], "A list element")
            if element is None:
                return None
            return f"List[{element}]"
        if reference.name in KNOWN_TYPES:
            return reference.name
        if reference.name in self._type_names:
            # A declared type whose own declaration has an error: that error is already reported.
            return reference.name if reference.name in self._refined else None
        candidates = [*KNOWN_TYPES, *self._type_names]
        close = difflib.get_close_matches(reference.name, candidates, n=1, cutoff=0.5)
        if reference.name == "String":
            hint = "The text type is called Text."
        elif close:
            hint = f"Did you mean '{close[0]}'?"
        else:
            hint = "The types are Int, Float, Bool, Text and Void, and the types the program declares."
        self._report("E2012", f"'{reference.name}' is not a type", reference.span, hint=hint)
        return None

    def _signature(self, function: ast.Function) -> Signature:
        params = tuple(
            (param.name, self._value_type(param.type, f"The parameter '{param.name}'"))
            for param in function.params
        )
        return Signature(function.name, params, self._known_type(function.return_type))

    def _main(self, main: ast.Function | None) -> None:
        if main is None:
            self._report(
                "E2001",
                "This program has no 'main' function, so there is nothing to run",
                None,
                hint="Add the entry point: fn main() -> Void { ... }",
            )
            return
        if main.params:
            self._report(
                "E2013",
                "'main' cannot have parameters",
                main.params[0].span.to(main.params[-1].span),
                hint="Write: fn main() -> Void",
            )
        signature = self._signatures.get("main")
        if signature is not None and signature.return_type not in (None, VOID):
            self._report("E2004", "'main' must return Void", main.return_type.span, hint="Write: fn main() -> Void")

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
                    hint="'result' is the name of the return value inside an 'ensures' clause.",
                )
            elif not self._name_is_free(param.name, param.name_span, scope):
                continue
            self._declare(scope, param.name, "parameter", param_type, param.name_span)

        for contract in function.contracts:
            contract_scope = scope
            if contract.clause == "ensures" and signature.return_type not in (None, VOID):
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

    def _name_is_free(self, name: str, span: Span, scope: _Scope) -> bool:
        """Reports E2006 and returns False if `name` cannot be declared in `scope`.

        Functions, parameters and variables share one namespace, and a visible name is never
        declared again: every name in a function means exactly one thing.
        """
        if name in self._type_names:
            self._report(
                "E2006",
                f"'{name}' is the name of a type and cannot be used for something else",
                span,
                hint="Choose a different name. Types start with a capital letter; values usually do not.",
            )
            return False
        if name in BUILTINS or name in self._signatures:
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
                        loop_variable=loop_variable)
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
        elif isinstance(statement, ast.Block):
            return self._block(statement, _Scope(scope))
        elif isinstance(statement, ast.While):
            self._while(statement, scope)
        elif isinstance(statement, ast.For):
            self._for(statement, scope)
        elif isinstance(statement, ast.Assign):
            self._assign(statement, scope)
        else:
            expression = statement.expression
            found = self._expression(expression, scope)
            if found is None:
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
        Parameters stay immutable, so 'ensures' and the diagnostics see the values a call received."""
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
        measures = [clause for clause in statement.clauses if clause.clause == "decreases"]
        for clause in statement.clauses:
            if clause.clause == "invariant":
                self._condition(clause.condition, scope, "'invariant'")
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
                        f"The measure of 'decreases' must be Int, found {found}",
                        clause.condition.span,
                        hint="The measure is a whole number that gets smaller on every turn and never goes below 0.",
                    )
        if not measures:
            keyword = statement.span
            self._report(
                "E2021",
                "This loop does not say why it ends",
                Span(keyword.line, keyword.column, keyword.line, keyword.column + len("while")),
                hint="Add 'decreases <expression>' with an Int that gets smaller on every turn and never goes "
                     "below 0, for example 'decreases n - i'.",
            )
        for extra in measures[1:]:
            first = measures[0].span
            self._report(
                "E2021",
                "A loop has exactly one measure",
                extra.span,
                hint="Combine them into one Int that gets smaller on every turn.",
                notes=(f"The first 'decreases' is at line {first.line}, column {first.column}.",),
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
            if clause.clause == "invariant":
                self._condition(clause.condition, scope, "'invariant'")
            else:
                self._report(
                    "E2022",
                    "'decreases' has no meaning in a 'for' loop",
                    clause.span,
                    hint="A 'for' loop ends when the list is exhausted; remove the 'decreases' clause.",
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

    def _if(self, statement: ast.If, scope: _Scope) -> bool:
        self._condition(statement.condition, scope, "'if'")
        then_returns = self._block(statement.then_block, _Scope(scope))
        if statement.else_branch is None:
            return False
        if isinstance(statement.else_branch, ast.If):
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
                hint="'result' only exists inside an 'ensures' clause of a function that returns a value.",
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
        if isinstance(node, ast.Group):
            return self._expression(node.expression, scope, expected)
        if isinstance(node, ast.Name):
            return self._name(node, scope)
        if isinstance(node, ast.Unary):
            return self._unary(node, scope)
        if isinstance(node, ast.Binary):
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
        return self._call(node, scope)

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

    def _name(self, node: ast.Name, scope: _Scope) -> str | None:
        found = scope.find(node.name)
        if found is not None:
            found.references.append(node.span)
            return found.type
        if node.name in self._type_names:
            self._report(
                "E2011",
                f"'{node.name}' is a type, not a value",
                node.span,
                hint=f"To check a value against it, call it: {node.name}(x)",
            )
        elif node.name in BUILTINS or node.name in self._signatures:
            self._report(
                "E2011",
                f"'{node.name}' is a function, not a value",
                node.span,
                hint=f"Call it with parentheses: {node.name}(...)",
            )
        else:
            self._unknown_variable(node.name, node.span, scope)
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
        if node.callee in self._type_names:
            return missing
        if node.qualifier is not None and node.callee not in BUILTINS:
            return missing
        signature = BUILTINS.get(node.callee) or self._signatures.get(node.callee)
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

    def _call(self, node: ast.Call, scope: _Scope) -> str | None:
        expectations = self._argument_expectations(node)
        argument_types = [
            self._expression(argument, scope, expected)
            for argument, expected in zip(node.arguments, expectations, strict=True)
        ]
        if node.qualifier is not None and node.callee not in BUILTINS:
            self._unknown_qualified_call(node, scope)
            return None
        if node.callee in self._type_names:
            return self._refinement_check(node, argument_types)
        if self._refining is not None and node.callee in self._function_names and node.callee not in BUILTINS:
            self._report(
                "E2018",
                f"The condition of '{self._refining}' cannot call the function '{node.callee}'",
                node.callee_span,
                hint="A refinement only describes the value itself: it can use operators, literals and the "
                     "built-in conversions. Write the rule there, or check it with 'requires'.",
            )
            return None
        signature = BUILTINS.get(node.callee) or self._signatures.get(node.callee)

        if signature is None:
            if scope.find(node.callee) is not None:
                self._report("E2008", f"'{node.callee}' is a variable, not a function", node.callee_span)
            else:
                self._report("E2008", f"There is no function named '{node.callee}'", node.callee_span,
                             hint=self._function_hint(node.callee))
            return None

        # The call is resolved: it is recorded even if its arguments turn out to be wrong. A call
        # written in an example is a reference to the function, but not an edge of the call graph:
        # the function does not make that call when it runs (decision 0008, section 2).
        if self._in_example is None:
            self._calls.append((self._function_name, signature.name))
        if not signature.builtin:
            self._function_symbols[signature.name].references.append(node.callee_span)

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

        if signature.parametric is not None:
            return self._parametric_call(node, argument_types, signature)

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

    def _parametric_call(self, node: ast.Call, argument_types: list[str | None],
                         signature: Signature) -> str | None:
        """Checks a call to a built-in whose signature mentions type variables.

        Each argument is unified, in order, with its parameter type. Later parameters
        see what earlier ones bound, and the result is the return type after the same
        substitution. When a parameter is already concrete, the ordinary assignment
        rule applies, so a refined element can still widen to its base type.
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
        if _contains_type_variable(result):
            self._report(
                "E2011",
                "Cannot infer the type of the elements of this list",
                node.span,
                hint="Write the type of the list explicitly, for example: let xs: List[Int] = [].",
            )
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
        plain = [*self._signatures, *(name for name in BUILTINS if "." not in name)]
        close = difflib.get_close_matches(callee, plain, n=1)
        if close:
            return suggest(close)
        members = sorted({name.split(".")[1] for name in BUILTINS if "." in name})
        close = difflib.get_close_matches(callee, members, n=1)
        return suggest(qualified(close[0])) if close else None

    def _unknown_qualified_call(self, node: ast.Call, scope: _Scope) -> None:
        """`Name.function(...)` where Name is not a type with that function (decision 0011, 9)."""
        qualifier = node.qualifier
        function = node.callee.split(".", 1)[1]
        hint: str | None = None
        notes: tuple[str, ...] = ()
        symbol = scope.find(qualifier)
        if qualifier in KNOWN_TYPES or qualifier == type_model.LIST.name:
            label = f"'{qualifier}' has no function named '{function}'"
            functions = TYPE_FUNCTIONS.get(qualifier, [])
            if functions:
                close = difflib.get_close_matches(function, functions, n=1)
                hint = f"Did you mean '{qualifier}.{close[0]}'?" if close else None
                notes = (f"The functions of {qualifier}: {', '.join(functions)}.",)
            else:
                notes = (f"{qualifier} has no functions yet.",)
        elif qualifier in self._type_names:
            label = f"'{qualifier}' has no functions of its own"
            base = self._root(qualifier)
            if TYPE_FUNCTIONS.get(base):
                hint = f"A value of {qualifier} can be passed to the functions of its base type, {base}."
        elif symbol is not None:
            label = f"'{qualifier}' is a {symbol.category}: values have no functions of their own"
            base = self._root(symbol.type) if symbol.type is not None else None
            if function in TYPE_FUNCTIONS.get(base, []):
                hint = f"Call the function of its type: {base}.{function}({qualifier})"
        elif qualifier in BUILTINS or qualifier in self._signatures:
            label = f"'{qualifier}' is a function, not a type"
        else:
            label = f"There is no type named '{qualifier}'"
            close = difflib.get_close_matches(
                qualifier, [*KNOWN_TYPES, type_model.LIST.name, *self._type_names], n=1,
            )
            hint = f"Did you mean '{close[0]}'?" if close else None
            if qualifier[:1].islower():
                notes = ("Before the '.' goes the name of a type, such as Text. "
                         "Modules are not part of NEXORA yet.",)
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

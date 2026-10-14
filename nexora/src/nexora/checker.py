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
from dataclasses import dataclass, field

from . import ast_nodes as ast
from .diagnostics import MAX_DIAGNOSTICS, Diagnostic, NexoraRuntimeError, Span
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
class Signature:
    """What a call needs to know about a function. A type is None when it was written wrong
    in the declaration; calls then skip the checks that depend on it."""

    name: str
    params: tuple[tuple[str, str | None], ...]
    return_type: str | None
    builtin: bool = False

    def describe(self) -> str:
        params = ", ".join(f"{name}: {kind or '?'}" for name, kind in self.params)
        return f"fn {self.name}({params}) -> {self.return_type or '?'}"


# The built-in functions. These are the only conversions between types: nothing converts implicitly.
BUILTINS: dict[str, Signature] = {
    signature.name: signature
    for signature in (
        Signature("print", (("value", ANY_VALUE),), VOID, builtin=True),
        Signature("to_text", (("value", ANY_VALUE),), TEXT, builtin=True),
        Signature("to_float", (("value", INT),), FLOAT, builtin=True),
        Signature("to_int", (("value", FLOAT),), INT, builtin=True),
    )
}


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
    return 1


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
        return BOOL if left in (INT, FLOAT) else None
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
        return f"'{operator}' compares two Int values or two Float values."
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
        # Every function name the program declares, known before any condition is checked.
        self._function_names: set[str] = set()
        # Work spent so far checking constants (see MAX_REFINEMENT_STEPS); None once over the limit.
        self._refinement_steps: int | None = 0
        # The function being checked.
        self._function_name = ""
        self._return_type: str | None = None
        # The refined type whose condition is being checked, if any.
        self._refining: str | None = None

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

    def _root(self, kind: str) -> str:
        """The built-in type a type is made of: itself, or the end of a chain of refinements."""
        refined = self._refined.get(kind)
        return refined.root if refined is not None else kind

    def _accepts(self, expected: str, found: str) -> bool:
        """Whether a value of type `found` can be used where `expected` is needed: the same type,
        or a refinement of it (a Percent is an Int, an Int is not a Percent)."""
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
        if expected in self._refined and self._root(found) == self._root(expected):
            if self._constant(node) is not None and found not in self._refined:
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
        if main.return_type.name in VALUE_TYPES or main.return_type.name in self._type_names:
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

        returns = self._block(function.body, _Scope(scope))
        if signature.return_type not in (None, VOID) and not returns:
            self._report(
                "E2014",
                f"'{function.name}' must return a value of type {signature.return_type}, "
                "but its body can end without a 'return'",
                function.name_span,
                hint="Make sure every path through the function ends with 'return'. "
                     "An 'if' without 'else' can be skipped.",
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

    def _declare(self, scope: _Scope, name: str, category: str, kind: str | None, span: Span) -> None:
        symbol = Symbol(name, category, kind, span, self._function_name, scope.span)
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
        if isinstance(statement, ast.Let):
            self._let(statement, scope)
        elif isinstance(statement, ast.Return):
            self._return(statement, scope)
            return True
        elif isinstance(statement, ast.If):
            return self._if(statement, scope)
        elif isinstance(statement, ast.Block):
            return self._block(statement, _Scope(scope))
        elif isinstance(statement, ast.Assign):
            self._expression(statement.value, scope)
            if scope.find(statement.name) is None:
                self._unknown_variable(statement.name, statement.name_span, scope)
            else:
                self._report(
                    "E2007",
                    f"'{statement.name}' cannot be given a new value: variables are immutable",
                    statement.name_span,
                    hint="Declare a new variable with a different name instead.",
                )
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

    def _let(self, statement: ast.Let, scope: _Scope) -> None:
        # The initialiser is checked first: a variable is not visible inside its own declaration.
        value_type = self._expression(statement.value, scope)
        if value_type == VOID:
            self._report("E2011", "This call does not produce a value to store", statement.value.span)
            value_type = None

        variable_type = value_type
        if statement.declared_type is not None:
            declared = self._value_type(statement.declared_type, f"The variable '{statement.name}'")
            if declared is not None:
                # The annotation decides the type, so later uses are checked against what was intended.
                variable_type = declared
                if value_type is not None:
                    self._expect_type(declared, value_type, statement.value,
                                      (f"'{statement.name}' is declared as {declared}.",))

        if self._name_is_free(statement.name, statement.name_span, scope):
            self._declare(scope, statement.name, "variable", variable_type, statement.name_span)

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

        found = self._expression(statement.value, scope)
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
        if found is None or self._root(found) == BOOL:
            return
        hint = None
        if found in (INT, FLOAT):
            hint = "A number is not a condition. Compare it explicitly, for example: x != 0"
        elif found == VOID:
            hint = "A call to a Void function does not produce a value."
        self._report("E2011", f"The condition of {owner} must be Bool, found {found}", condition.span, hint=hint)

    def _unknown_variable(self, name: str, span: Span, scope: _Scope) -> None:
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

    def _expression(self, node: ast.Expr, scope: _Scope) -> str | None:
        found = self._infer(node, scope)
        if found is not None:
            self._types[id(node)] = found
        return found

    def _infer(self, node: ast.Expr, scope: _Scope) -> str | None:
        if isinstance(node, ast.IntLiteral):
            return INT
        if isinstance(node, ast.FloatLiteral):
            return FLOAT
        if isinstance(node, ast.TextLiteral):
            return TEXT
        if isinstance(node, ast.BoolLiteral):
            return BOOL
        if isinstance(node, ast.Group):
            return self._expression(node.expression, scope)
        if isinstance(node, ast.Name):
            return self._name(node, scope)
        if isinstance(node, ast.Unary):
            return self._unary(node, scope)
        if isinstance(node, ast.Binary):
            left = self._expression(node.left, scope)
            right = self._expression(node.right, scope)
            if left is None or right is None:
                return None
            # A refined value takes part in operations as a value of its base type: the result of
            # Percent + Percent is an Int, which may well be outside the range of Percent.
            result = binary_result(node.operator, self._root(left), self._root(right))
            if result is None:
                self._report(
                    "E2011",
                    f"Cannot apply '{node.operator}' to {left} and {right}",
                    node.operator_span,
                    hint=_binary_hint(node.operator, self._root(left), self._root(right)),
                )
            return result
        return self._call(node, scope)

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
        if node.operator == "-":
            if operand in (INT, FLOAT):
                return operand
            self._report("E2011", f"Cannot apply '-' to {operand}", node.span, hint="'-' negates an Int or a Float.")
            return None
        if operand == BOOL:
            return BOOL
        hint = "'not' negates a Bool."
        if operand in (INT, FLOAT):
            hint += " To negate a comparison, put it in parentheses: not (a == b)"
        self._report("E2011", f"Cannot apply 'not' to {operand}", node.span, hint=hint)
        return None

    def _call(self, node: ast.Call, scope: _Scope) -> str | None:
        argument_types = [self._expression(argument, scope) for argument in node.arguments]
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
                known = [*self._signatures, *BUILTINS]
                close = difflib.get_close_matches(node.callee, known, n=1)
                hint = f"Did you mean '{close[0]}'?" if close else None
                self._report("E2008", f"There is no function named '{node.callee}'", node.callee_span, hint=hint)
            return None

        # The call is resolved: it is recorded even if its arguments turn out to be wrong.
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
            return signature.return_type

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


def check(program: ast.Program) -> tuple[CheckedProgram, list[Diagnostic]]:
    return Checker().check(program)

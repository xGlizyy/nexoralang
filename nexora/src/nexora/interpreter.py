"""Interpreter: runs a checked NEXORA program by walking its AST.

It works on the tree directly; no Python code is generated or evaluated. The only
effect a program can have is writing text through `print`.

The interpreter only accepts a `CheckedProgram`: names and types were verified by the
checker and are not verified again here. What is checked here is exactly what cannot be
known before running: division by zero, overflow, conversions out of range, the depth of
the call stack, whether the `requires` and `ensures` conditions hold, whether a value
checked with `Percent(x)` satisfies the condition of its refined type, and whether every
loop keeps its invariants and makes its measure smaller on every turn.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from . import ast_nodes as ast
from .checker import BUILTINS, CheckedProgram, refinement_notes
from .diagnostics import Diagnostic, NexoraRuntimeError, Span
from .prelude import IMPLEMENTATIONS, parse_hint, requirements
from .values import INT_MAX, INT_MIN, RecordValue, Value, format_value, show_value

# The deepest chain of calls a program may have (main counts as the first).
MAX_CALL_DEPTH = 1000
# Python frames needed to run MAX_CALL_DEPTH ordinary NEXORA calls, with room to spare.
_PYTHON_RECURSION_LIMIT = 25_000
# How many calls a run-time diagnostic lists, and how many loops it names.
_TRACE_LENGTH = 6
# Every note that says where in a loop a diagnostic happened contains this text.
_LOOP_NOTE = " of the loop at line "
_MORE_LOOPS = "... and more loops."


class _Returned:
    """Signals that a `return` statement ran, carrying its value (None for a bare return)."""

    __slots__ = ("value",)

    def __init__(self, value: Value | None) -> None:
        self.value = value


@dataclass
class OwnCall:
    """An own call of an example (decision 0008, 6.3) that was invoked: its arguments were evaluated
    and the function was entered. It stays "stopped" unless the function returns a value."""

    node: ast.Call
    status: str = "stopped"          # "stopped" or "returned"
    value: Value | None = None


@dataclass
class ExampleRun:
    """What happened when one example was evaluated. `value` is None when the evaluation stopped
    with `error`. Nothing here is guessed: a call is listed only if it was really invoked."""

    value: bool | None
    invoked: list[OwnCall] = field(default_factory=list)
    # id() of the own calls that an 'and' or an 'or' did not need to evaluate.
    short_circuited: set[int] = field(default_factory=set)
    error: Diagnostic | None = None
    output: str = ""


class Environment:
    """The variables of one block, linked to the block that encloses it."""

    __slots__ = ("_parent", "_values")

    def __init__(self, parent: Environment | None = None) -> None:
        self._parent = parent
        self._values: dict[str, Value] = {}

    def lookup(self, name: str) -> Value:
        environment: Environment | None = self
        while environment is not None:
            if name in environment._values:
                return environment._values[name]
            environment = environment._parent
        # Unreachable for a checked program; reported as an internal error, not a user error.
        raise LookupError(f"variable '{name}' is not defined")

    def declare(self, name: str, value: Value) -> None:
        self._values[name] = value

    def assign(self, name: str, value: Value) -> None:
        """Gives a new value to a variable, in the block that declared it."""
        environment: Environment | None = self
        while environment is not None:
            if name in environment._values:
                environment._values[name] = value
                return
            environment = environment._parent
        raise LookupError(f"variable '{name}' is not defined")

    def visible(self) -> list[tuple[str, Value]]:
        """Every variable and parameter visible here, in the order they were declared."""
        chain: list[Environment] = []
        environment: Environment | None = self
        while environment is not None:
            chain.append(environment)
            environment = environment._parent
        return [pair for scope in reversed(chain) for pair in scope._values.items()]


class Interpreter:
    def __init__(self, checked: CheckedProgram, write: Callable[[str], object],
                 text_limit: int | None = None) -> None:
        """`write` receives the text produced by `print`. `text_limit`, if given, is the longest
        Text (in characters) a program may build; a host sets it to bound memory use."""
        self._functions = checked.functions
        # Refined type -> the declarations whose conditions its values satisfy, root first.
        self._refined = {name: refined.chain for name, refined in checked.refined.items()}
        # Record type -> its declaration. The identity comes from here: the interpreter
        # never rebuilds it from the name (decision 0014, 3).
        self._records = checked.records
        self._write = write
        self._text_limit = text_limit
        # The calls in progress: (function name, where it was called from). main has no call site.
        self._stack: list[tuple[str, Span | None]] = []
        # Where each loop in progress is, outermost first: the note _in_loop adds for it. Like _stack,
        # it is left as it was when MemoryError or RecursionError leaves the loops, so that _guarded
        # can add the same notes to E3004 and E3007 (decision 0010, section 7). Only text: no value
        # of the program is kept alive by it (decision 0009, 3.1).
        self._loops: list[str] = []
        # While an example is evaluated: id() of its own calls, and what is observed about them.
        self._own_calls: dict[int, ast.Call] = {}
        self._invoked: list[OwnCall] = []
        self._short_circuited: set[int] = set()

    def run(self) -> None:
        """Runs `main`. Raises NexoraRuntimeError if the program fails."""
        self._guarded(lambda: self._invoke(self._functions["main"], [], None))

    def evaluate_example(self, example: ast.Example, own_calls: list[ast.Call]) -> bool:
        """Evaluates the expression of an example, outside any call, and records its own calls.
        Raises NexoraRuntimeError if the evaluation fails. Meant for a fresh interpreter: one per
        example, so that a failure cannot leave its call stack behind (decision 0008, 3.3)."""
        self._own_calls = {id(call): call for call in own_calls}
        return self._guarded(lambda: self._evaluate(example.condition, Environment()))

    def _guarded(self, action: Callable[[], Value | None]) -> Value | None:
        """Runs `action` with enough Python stack for MAX_CALL_DEPTH calls, and turns running out of
        Python's own stack (E3004) or out of memory (E3007) into an error of the program instead of
        an internal error."""
        previous_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(previous_limit, _PYTHON_RECURSION_LIMIT))
        try:
            return action()
        except MemoryError:
            # Only take note here. Raised inside this block, E3007 would keep the MemoryError as its
            # __context__ (even with `from None`), and with it every frame and value of the program
            # (decision 0009, 3.1). Out of the block, they are no longer referenced.
            pass
        except RecursionError:
            # Calls combined with deeply nested expressions can exhaust Python's own stack before
            # MAX_CALL_DEPTH is reached. Same error code; the message says what actually happened.
            depth = len(self._stack)
            raise self._with_loop_notes(self._fail(
                "E3004",
                f"The program ran out of stack space after {depth} nested calls",
                None,
                hint="Calls that sit inside deeply nested expressions use more stack. "
                     "Reduce the recursion depth, or move parts of the expression into 'let' declarations.",
            )) from None
        finally:
            sys.setrecursionlimit(previous_limit)
        # Only reached after a MemoryError. If building the diagnostic runs out of memory again, that
        # second MemoryError leaves unconverted (decision 0009, 3.5).
        raise self._with_loop_notes(self._fail(
            "E3007",
            "The program needed more memory than is available.",
            None,
            hint="Reduce the size of values created by the program, especially values that grow with "
                 "each function call.",
        ))

    def _with_loop_notes(self, error: NexoraRuntimeError) -> NexoraRuntimeError:
        """`error` with the notes of the loops it left, innermost first: the ones _in_loop would have
        added if the error had passed through it. For E3004 and E3007, which are built here, after
        MemoryError or RecursionError has left every loop."""
        if not self._loops:
            return error
        notes = self._loops[::-1]
        if len(notes) > _TRACE_LENGTH:
            notes = [*notes[:_TRACE_LENGTH], _MORE_LOOPS]
        diagnostic = error.diagnostic
        return NexoraRuntimeError(replace(diagnostic, notes=(*diagnostic.notes, *notes)))

    # Errors

    def _fail(self, code: str, label: str, span: Span | None, *, hint: str | None = None,
              notes: tuple[str, ...] = (), skip_frames: int = 0) -> NexoraRuntimeError:
        """A run-time error, with the chain of calls that led to it as notes."""
        frames = self._stack[: len(self._stack) - skip_frames]
        trace = [
            f"In '{name}', called at line {site.line}, column {site.column}."
            for name, site in reversed(frames)
            if site is not None
        ]
        if len(trace) > _TRACE_LENGTH:
            hidden = len(trace) - _TRACE_LENGTH
            trace = trace[:_TRACE_LENGTH] + [f"... and {hidden} more call{'' if hidden == 1 else 's'}."]
        return NexoraRuntimeError(Diagnostic(code, label, span, hint, (*notes, *trace)))

    def _too_deep(self, span: Span | None) -> NexoraRuntimeError:
        return self._fail(
            "E3004",
            f"The program nested more than {MAX_CALL_DEPTH} calls",
            span,
            hint="A recursive function probably never reaches the case where it stops calling itself.",
        )

    # Functions

    def _invoke(self, function: ast.Function, arguments: list[Value], site: Span | None) -> Value | None:
        if len(self._stack) >= MAX_CALL_DEPTH:
            raise self._too_deep(site)
        self._stack.append((function.name, site))

        parameters = Environment()
        for param, argument in zip(function.params, arguments, strict=True):
            parameters.declare(param.name, argument)

        for contract in function.contracts:
            if contract.clause == "requires" and not self._evaluate(contract.condition, parameters):
                raise self._fail(
                    "E4001",
                    f"This call breaks a 'requires' condition of '{function.name}'",
                    site,
                    notes=(
                        f"The condition at line {contract.span.line} is false: {self._source_of(contract)}",
                        *self._reason_note(contract),
                        *self._values_note(function, arguments),
                    ),
                    # The callee never started: the trace begins at the caller.
                    skip_frames=1,
                )

        outcome = self._block(function.body, Environment(parameters))
        result = outcome.value if outcome is not None else None

        for contract in function.contracts:
            if contract.clause != "ensures":
                continue
            environment = parameters
            if result is not None:
                environment = Environment(parameters)
                environment.declare("result", result)
            if not self._evaluate(contract.condition, environment):
                notes = [f"'{function.name}' finished, but its condition is false: {self._source_of(contract)}"]
                notes.extend(self._reason_note(contract))
                if result is not None:
                    notes.append(f"It returned: result = {show_value(result)}")
                notes.extend(self._values_note(function, arguments))
                raise self._fail(
                    "E4002",
                    f"'{function.name}' breaks its own 'ensures' condition",
                    contract.span,
                    notes=tuple(notes),
                )

        self._stack.pop()
        return result

    @staticmethod
    def _values_note(function: ast.Function, arguments: list[Value]) -> tuple[str, ...]:
        if not function.params:
            return ()
        pairs = zip(function.params, arguments, strict=True)
        values = ", ".join(f"{param.name} = {show_value(value)}" for param, value in pairs)
        return (f"It was called with: {values}",)

    @staticmethod
    def _reason_note(contract: ast.Contract) -> tuple[str, ...]:
        return (f"Reason: {contract.message}",) if contract.message is not None else ()

    @staticmethod
    def _source_of(contract: ast.Contract) -> str:
        return f"{contract.clause} {unparse(contract.condition)}"

    # Refined types

    def broken_rule(self, chain: tuple[ast.TypeDecl, ...], value: Value) -> ast.TypeDecl | None:
        """The first declaration in `chain` whose condition `value` does not satisfy, or None."""
        for declaration in chain:
            environment = Environment()
            environment.declare("value", value)
            if not self._evaluate(declaration.condition, environment):
                return declaration
        return None

    def _refine(self, node: ast.Call, value: Value) -> Value:
        """`Percent(x)`: lets `value` through only if it satisfies the condition of the type."""
        try:
            broken = self.broken_rule(self._refined[node.callee], value)
        except NexoraRuntimeError as error:
            # The error points into the type's declaration; say which check led there.
            site = node.span
            where = f"While checking that a value is a valid {node.callee}, at line {site.line}, column {site.column}."
            diagnostic = error.diagnostic
            raise NexoraRuntimeError(replace(diagnostic, notes=(where, *diagnostic.notes))) from None
        if broken is None:
            return value
        raise self._fail(
            "E4003",
            f"This value is not a valid {node.callee}",
            node.span,
            notes=refinement_notes(node.callee, broken, show_value(value)),
        )

    # Statements. Each returns a _Returned when a 'return' ran inside it, and None otherwise.

    def _block(self, block: ast.Block, environment: Environment) -> _Returned | None:
        for statement in block.statements:
            outcome = self._statement(statement, environment)
            if outcome is not None:
                return outcome
        return None

    def _statement(self, statement: ast.Statement, environment: Environment) -> _Returned | None:
        if isinstance(statement, (ast.Let, ast.Var)):
            environment.declare(statement.name, self._evaluate(statement.value, environment))
            return None
        if isinstance(statement, ast.Assign):
            environment.assign(statement.name, self._evaluate(statement.value, environment))
            return None
        if isinstance(statement, ast.While):
            return self._while(statement, environment)
        if isinstance(statement, ast.For):
            return self._for(statement, environment)
        if isinstance(statement, ast.Return):
            if statement.value is None:
                return _Returned(None)
            return _Returned(self._evaluate(statement.value, environment))
        if isinstance(statement, ast.If):
            # Iterative over the 'else if' chain.
            branch: ast.If | ast.Block | None = statement
            while isinstance(branch, ast.If):
                if self._evaluate(branch.condition, environment):
                    return self._block(branch.then_block, Environment(environment))
                branch = branch.else_branch
            if branch is not None:
                return self._block(branch, Environment(environment))
            return None
        if isinstance(statement, ast.Block):
            return self._block(statement, Environment(environment))
        if isinstance(statement, ast.ExprStatement):
            self._evaluate(statement.expression, environment)
            return None
        raise TypeError(f"statement {type(statement).__name__} reached the interpreter")

    # Loops (decision 0010, section 6)

    def _while(self, loop: ast.While, environment: Environment) -> _Returned | None:
        """Runs a loop without recursion. Before every evaluation of the condition the invariants must
        hold; before every turn the measure must be 0 or more and smaller than on the turn before. So a
        loop always ends, or stops with a diagnostic that names the turn and the values."""
        invariants = [clause for clause in loop.clauses if clause.clause == "invariant"]
        measure = next(clause for clause in loop.clauses if clause.clause == "decreases")
        line = loop.span.line
        previous: int | None = None
        turn = 0
        while True:
            when = (f"Before the first turn of the loop at line {line}." if turn == 0
                    else f"After turn {turn} of the loop at line {line}.")
            for invariant in invariants:
                if not self._in_loop(when, lambda clause=invariant: self._evaluate(clause.condition, environment)):
                    raise self._fail(
                        "E4005",
                        "This condition is false",
                        invariant.condition.span,
                        notes=(
                            f"The condition at line {invariant.span.line} is false: "
                            f"invariant {unparse(invariant.condition)}",
                            *self._reason_note(invariant),
                            when,
                            *self._loop_values(environment),
                        ),
                    )
            if not self._in_loop(when, lambda: self._evaluate(loop.condition, environment)):
                return None

            turn += 1
            before = f"Before turn {turn} of the loop at line {line}."
            current = self._in_loop(before, lambda: self._evaluate(measure.condition, environment))
            if current < 0 or (previous is not None and current >= previous):
                if current < 0:
                    label = f"The measure is {current}; it must be 0 or more"
                elif current == previous:
                    label = f"The measure was {previous} and is still {current}"
                else:
                    label = f"The measure was {previous} and is now {current}"
                raise self._fail(
                    "E4006",
                    label,
                    measure.condition.span,
                    notes=(
                        f"The measure at line {measure.span.line}: decreases {unparse(measure.condition)}",
                        *self._reason_note(measure),
                        before,
                        *self._loop_values(environment),
                    ),
                )
            previous = current
            outcome = self._in_loop(f"In turn {turn} of the loop at line {line}.",
                                    lambda: self._block(loop.body, Environment(environment)))
            if outcome is not None:
                return outcome

    def _for(self, loop: ast.For, environment: Environment) -> _Returned | None:
        """Walks the list once. The iterable is evaluated once, before the first turn, and every
        turn runs the body in a new environment where the iterator is that element. Invariants are
        checked before each turn and once after the last one, exactly as in a `while`; the list is
        finite, so a `for` has no measure (decision 0012)."""
        items = self._evaluate(loop.iterable, environment)
        invariants = [clause for clause in loop.clauses if clause.clause == "invariant"]
        line = loop.span.line
        turn = 0
        while True:
            when = (f"Before the first turn of the loop at line {line}." if turn == 0
                    else f"After turn {turn} of the loop at line {line}.")
            for invariant in invariants:
                if not self._in_loop(when, lambda clause=invariant: self._evaluate(clause.condition, environment)):
                    raise self._fail(
                        "E4005",
                        "This condition is false",
                        invariant.condition.span,
                        notes=(
                            f"The condition at line {invariant.span.line} is false: "
                            f"invariant {unparse(invariant.condition)}",
                            *self._reason_note(invariant),
                            when,
                            *self._loop_values(environment),
                        ),
                    )
            if turn == len(items):
                return None
            item = items[turn]
            turn += 1
            body = Environment(environment)
            body.declare(loop.name, item)
            outcome = self._in_loop(f"In turn {turn} of the loop at line {line}.",
                                    lambda body=body: self._block(loop.body, body))
            if outcome is not None:
                return outcome

    def _in_loop(self, where: str, action: Callable[[], object]):
        """Runs part of a loop. A diagnostic raised inside it gains a note saying where in the loop it
        happened, so an error nested in several loops names each one, innermost first. Anything else
        that leaves it (MemoryError, RecursionError) leaves `where` in _loops for _guarded."""
        self._loops.append(where)
        try:
            result = action()
        except NexoraRuntimeError as error:
            self._loops.pop()
            diagnostic = error.diagnostic
            if _MORE_LOOPS in diagnostic.notes:
                raise
            loops = sum(1 for note in diagnostic.notes if _LOOP_NOTE in note)
            note = where if loops < _TRACE_LENGTH else _MORE_LOOPS
            raise NexoraRuntimeError(replace(diagnostic, notes=(*diagnostic.notes, note))) from None
        self._loops.pop()
        return result

    @staticmethod
    def _loop_values(environment: Environment) -> tuple[str, ...]:
        pairs = environment.visible()
        if not pairs:
            return ()
        return ("The values: " + ", ".join(f"{name} = {show_value(value)}" for name, value in pairs),)

    # Expressions

    def _evaluate(self, node: ast.Expr, environment: Environment) -> Value | None:
        """Evaluates an expression. Only a call to a Void function yields None."""
        if isinstance(node, (ast.IntLiteral, ast.FloatLiteral, ast.TextLiteral, ast.BoolLiteral)):
            return node.value
        if isinstance(node, ast.ListLiteral):
            return tuple(self._evaluate(element, environment) for element in node.elements)
        if isinstance(node, ast.Name):
            return environment.lookup(node.name)
        if isinstance(node, ast.RecordConstruction):
            return self._record(node, environment)
        if isinstance(node, ast.FieldAccess):
            return self._field(node, environment)
        if isinstance(node, ast.Group):
            return self._evaluate(node.expression, environment)
        if isinstance(node, ast.Binary):
            return self._binary(node, environment)
        if isinstance(node, ast.Unary):
            operand = self._evaluate(node.operand, environment)
            if node.operator == "not":
                return not operand
            if isinstance(operand, float):
                return -operand
            return self._int(-operand, node.span)
        return self._call(node, environment)

    def _record(self, node: ast.RecordConstruction, environment: Environment) -> Value:
        """`Point(x: 1, y: 2)`: builds a record value.

        The fields are kept in the order of the declaration, not in the order they were
        written, so two records built the same way are the same value.
        """
        record = self._records[node.name]
        values = {field.name: self._evaluate(field.value, environment) for field in node.fields}
        fields = tuple((name, values[name]) for name, _ in record.fields)
        return RecordValue(record.identity, record.name, fields)

    def _field(self, node: ast.FieldAccess, environment: Environment) -> Value:
        """`p.x`: reads a field of a record value."""
        target = self._evaluate(node.target, environment)
        if not isinstance(target, RecordValue):
            raise LookupError(f"the value of '{node.target.span}' is not a record")
        return target.value_of(node.name)

    def _binary(self, node: ast.Binary, environment: Environment) -> Value:
        operator = node.operator
        left = self._evaluate(node.left, environment)

        # 'and' and 'or' only evaluate their right side when it can change the result.
        if operator in ("and", "or"):
            if left if operator == "or" else not left:
                self._skipped(node.right)
                return left
            return self._evaluate(node.right, environment)

        right = self._evaluate(node.right, environment)
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right

        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        else:
            if right == 0:
                raise self._fail("E3001", "The right-hand side of this division is zero", node.right.span)
            if isinstance(left, float):
                result = left / right
            else:
                # Int division drops the fractional part (rounds toward zero): -7 / 2 is -3.
                result = abs(left) // abs(right)
                if (left < 0) != (right < 0):
                    result = -result

        if isinstance(result, float):
            if not math.isfinite(result):
                raise self._fail("E3003", "The result of this operation is too large for a Float", node.span)
            return result
        if isinstance(result, int):
            return self._int(result, node.span)
        if self._text_limit is not None and len(result) > self._text_limit:
            raise self._fail(
                "E3006",
                f"The result of this operation is longer than {self._text_limit} characters",
                node.span,
                hint="This environment limits the length of a Text value.",
            )
        return result

    def _int(self, value: int, span: Span) -> int:
        if not INT_MIN <= value <= INT_MAX:
            raise self._fail(
                "E3002",
                "The result of this operation does not fit in an Int",
                span,
                hint=f"Int holds whole numbers from {INT_MIN} to {INT_MAX}.",
            )
        return value

    def _call(self, node: ast.Call, environment: Environment) -> Value | None:
        arguments = [self._evaluate(argument, environment) for argument in node.arguments]
        function = self._functions.get(node.callee)
        if function is not None:
            if id(node) not in self._own_calls:
                return self._invoke(function, arguments, node.span)
            # An own call of the example being evaluated: recorded when it is invoked, so the list
            # follows the real order of invocation, and marked "returned" only if it returns.
            record = OwnCall(node)
            self._invoked.append(record)
            result = self._invoke(function, arguments, node.span)
            record.status, record.value = "returned", result
            return result
        if node.callee in self._refined:
            return self._refine(node, arguments[0])

        # The functions of a type (decision 0011): their requires first, then the operation.
        implementation = IMPLEMENTATIONS.get(node.callee)
        if implementation is not None:
            self._check_requirements(node, arguments)
            return implementation(*arguments)

        # Built-in functions.
        value = arguments[0]
        if node.callee == "print":
            self._write(format_value(value) + "\n")
            return None
        if node.callee == "to_text":
            return format_value(value)
        if node.callee == "to_float":
            return float(value)
        if node.callee == "to_int":
            # Drops the fractional part (rounds toward zero), like Int division.
            whole = math.trunc(value)
            if not INT_MIN <= whole <= INT_MAX:
                raise self._fail(
                    "E3005",
                    f"{format_value(value)} is outside the range of Int",
                    node.arguments[0].span,
                    hint=f"Int holds whole numbers from {INT_MIN} to {INT_MAX}.",
                )
            return whole
        raise TypeError(f"call to '{node.callee}' reached the interpreter")


    def _check_requirements(self, node: ast.Call, arguments: list[Value]) -> None:
        """Checks the `requires` of a function of a type, in the order they are written, and stops
        at the first that is false with the same E4001 as a function of the program (decision 0011,
        7.1 and 7.2). Its conditions cannot fail: they only compare Ints and call functions that
        have an answer for any text."""
        contracts = requirements(node.callee)
        if not contracts:
            return
        params = [name for name, _ in BUILTINS[node.callee].params]
        environment = Environment()
        for name, value in zip(params, arguments, strict=True):
            environment.declare(name, value)
        for contract in contracts:
            if self._evaluate(contract.condition, environment):
                continue
            values = ", ".join(f"{name} = {show_value(value)}" for name, value in zip(params, arguments, strict=True))
            raise self._fail(
                "E4001",
                f"This call breaks a 'requires' condition of '{node.callee}'",
                node.span,
                hint=parse_hint(node.callee, arguments[0]),
                notes=(
                    f"The condition of the built-in function is false: requires {unparse(contract.condition)}",
                    f"Reason: {contract.message}",
                    f"It was called with: {values}",
                ),
            )

    def _skipped(self, node: ast.Expr) -> None:
        """Marks the own calls inside an operand that 'and' or 'or' did not need to evaluate."""
        if not self._own_calls:
            return
        pending = [node]
        while pending:
            current = pending.pop()
            if isinstance(current, ast.Call):
                if id(current) in self._own_calls:
                    self._short_circuited.add(id(current))
                pending.extend(current.arguments)
            elif isinstance(current, ast.Binary):
                pending.extend((current.left, current.right))
            elif isinstance(current, ast.Unary):
                pending.append(current.operand)
            elif isinstance(current, ast.Group):
                pending.append(current.expression)
            elif isinstance(current, ast.ListLiteral):
                pending.extend(current.elements)
            elif isinstance(current, ast.RecordConstruction):
                pending.extend(field.value for field in current.fields)
            elif isinstance(current, ast.FieldAccess):
                pending.append(current.target)


def unparse(node: ast.Expr) -> str:
    """An expression written back as source text, for contract and refinement diagnostics."""
    if isinstance(node, ast.TextLiteral):
        return show_value(node.value)
    if isinstance(node, (ast.IntLiteral, ast.FloatLiteral, ast.BoolLiteral)):
        return format_value(node.value)
    if isinstance(node, ast.Name):
        return node.name
    if isinstance(node, ast.Group):
        return f"({unparse(node.expression)})"
    if isinstance(node, ast.Unary):
        separator = " " if node.operator == "not" else ""
        return f"{node.operator}{separator}{unparse(node.operand)}"
    if isinstance(node, ast.Binary):
        return f"{unparse(node.left)} {node.operator} {unparse(node.right)}"
    if isinstance(node, ast.ListLiteral):
        return "[" + ", ".join(unparse(element) for element in node.elements) + "]"
    if isinstance(node, ast.RecordConstruction):
        fields = ", ".join(f"{field.name}: {unparse(field.value)}" for field in node.fields)
        return f"{node.name}({fields})"
    if isinstance(node, ast.FieldAccess):
        return f"{unparse(node.target)}.{node.name}"
    return f"{node.callee}({', '.join(unparse(argument) for argument in node.arguments)})"


def broken_rule(chain: tuple[ast.TypeDecl, ...], value: Value) -> ast.TypeDecl | None:
    """The first declaration in `chain` whose condition `value` does not satisfy, or None.

    Used by the checker on constants. The conditions of refined types call no function of the
    program, so no program is needed to evaluate them. Raises NexoraRuntimeError if evaluating a
    condition fails (a division by zero inside it, for instance)."""
    bare = Interpreter(CheckedProgram(ast.Program(chain[0].span, (), ()), {}, {}), lambda text: None)
    return bare.broken_rule(chain, value)


def run(checked: CheckedProgram, write: Callable[[str], object], *, text_limit: int | None = None) -> None:
    """Runs a program that passed the static checks."""
    Interpreter(checked, write, text_limit).run()


def run_example(checked: CheckedProgram, example: ast.Example, own_calls: list[ast.Call]) -> ExampleRun:
    """Evaluates one example of a program that passed the static checks, in a new interpreter.

    A diagnostic of the program (a runtime error or a broken rule, including E3004 for running out
    of Python's stack and E3007 for running out of memory) is returned in `error`. Anything else,
    such as an exception that reveals a defect in NEXORA or KeyboardInterrupt, propagates:
    decisions 0008, 3.4, and 0009."""
    output: list[str] = []
    interpreter = Interpreter(checked, output.append)
    try:
        value = interpreter.evaluate_example(example, own_calls)
    except NexoraRuntimeError as error:
        return ExampleRun(None, interpreter._invoked, interpreter._short_circuited, error.diagnostic, "".join(output))
    return ExampleRun(bool(value), interpreter._invoked, interpreter._short_circuited, None, "".join(output))

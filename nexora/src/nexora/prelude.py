"""The functions that belong to a type, such as Text.length and Int.parse (decision 0011).

Three things live here, and only here:

- their contracts, written in NEXORA and parsed with the real parser: the `needs` that say when
  a function has an answer, and the `promises` that describe its result;
- their implementations, which the interpreter calls once every `needs` holds;
- the grammar of a number written in a text (decision 0011, section 6).

Their signatures are in checker.py, next to the other built-in functions.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import ast_nodes as ast
from .diagnostics import Source
from .lexer import tokenize
from .parser import parse_expression
from .values import ERR, INT_MAX, INT_MIN, NONE, OK, SOME, Value, VariantValue

# Decision 0011, 6.1. `[0-9]` is ASCII only, unlike `\d`.
_INTEGER = re.compile(r"-?[0-9]+")
_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)")
# The most digits a value inside the range of Int can have, once the leading zeros are skipped.
_INT_DIGITS = len(str(INT_MAX))


@dataclass(frozen=True)
class Contract:
    """A `needs` or `promises` of a built-in function."""

    clause: str                 # "needs" or "promises"
    source: str                 # the condition, as written here
    condition: ast.Expr         # the same condition, parsed
    message: str

    @property
    def checked_at_run_time(self) -> bool:
        """Only `needs` is checked when the program runs; `promises` is kept by the implementation
        and checked by the tests (decision 0011, 7.1)."""
        return self.clause == "needs"


def _contract(clause: str, source: str, message: str) -> Contract:
    tokens, errors = tokenize(Source("<built-in>", source))
    if errors:
        raise ValueError(f"the built-in condition {source!r} does not tokenize: {errors[0].label}")
    return Contract(clause, source, parse_expression(tokens), message)


# Decision 0011, section 4. A function without an entry has no contract.
CONTRACTS: dict[str, tuple[Contract, ...]] = {
    "Text.length": (
        _contract("promises", "result >= 0", "A text never has a negative number of characters"),
    ),
    "Text.slice": (
        _contract("needs", "start >= 0", "A slice cannot start before the first character"),
        _contract("needs", "start <= end", "A slice cannot end before it starts"),
        _contract("needs", "end <= Text.length(text)", "A slice cannot end after the last character"),
        _contract("promises", "Text.length(result) == end - start", "The slice has exactly end - start characters"),
    ),
    "Int.parse": (
        _contract("needs", "Int.can_parse(text)",
                  "Only a whole number within the range of Int can be read as an Int"),
    ),
    "Float.parse": (
        _contract("needs", "Float.can_parse(text)",
                  "Only a decimal number that fits in a Float can be read as a Float"),
    ),
    "List.get": (
        _contract("needs", "0 <= i and i < List.length(xs)",
                  "An index must be inside the list"),
    ),
}


def requirements(name: str) -> tuple[Contract, ...]:
    """The `needs` of a built-in function, in the order they are checked."""
    return tuple(contract for contract in CONTRACTS.get(name, ()) if contract.clause == "needs")


# Numbers written in a text (decision 0011, section 6)

def can_parse_int(text: str) -> bool:
    """Linear in the length of the text, and never converts more than 19 digits: Python refuses to
    convert a text of more than 4300 digits, and a long one would cost memory (decision 0011, 6.4)."""
    if _INTEGER.fullmatch(text) is None:
        return False
    return _int_value(text) is not None


def _int_value(text: str) -> int | None:
    """The value of a text that follows the rule `entero`, or None if it is outside the range of Int."""
    negative = text.startswith("-")
    digits = (text[1:] if negative else text).lstrip("0") or "0"
    if len(digits) > _INT_DIGITS:
        return None
    value = -int(digits) if negative else int(digits)
    return value if INT_MIN <= value <= INT_MAX else None


def parse_int(text: str) -> int:
    """Only called once `can_parse_int(text)` holds (its `needs`)."""
    value = _int_value(text) if _INTEGER.fullmatch(text) else None
    if value is None:
        raise ValueError("Int.parse was called without checking its needs")
    return value


def can_parse_float(text: str) -> bool:
    """The grammar first: Python's float() would also accept spaces, '_', '+', 'inf' and 'nan'.
    Then the value, correctly rounded: accepted unless it rounds to infinity (decision 0011, 6.4)."""
    return _DECIMAL.fullmatch(text) is not None and not math.isinf(float(text))


def parse_float(text: str) -> float:
    """Only called once `can_parse_float(text)` holds (its `needs`)."""
    if not can_parse_float(text):
        raise ValueError("Float.parse was called without checking its needs")
    return float(text)


def parse_hint(name: str, text: str) -> str | None:
    """The hint of the E4001 of Int.parse or Float.parse: what to do in each case, chosen with the
    same grammar, so it cannot fail or contradict the condition (decision 0011, 7.2)."""
    if name == "Int.parse":
        if _INTEGER.fullmatch(text):
            return f"Int holds whole numbers from {INT_MIN} to {INT_MAX}."
        return "Check the text first with Int.can_parse(...), and call Int.parse only when it is true."
    if name == "Float.parse":
        if _INTEGER.fullmatch(text):
            return "This text is a whole number: read it with to_float(Int.parse(...))."
        if _DECIMAL.fullmatch(text):
            return "The number is too large for a Float."
        return "Check the text first with Float.can_parse(...), and call Float.parse only when it is true."
    return None


# The implementations. Each receives the values of the arguments, in order, once every `needs`
# holds, and returns the value of the call.
IMPLEMENTATIONS = {
    "Text.length": lambda text: len(text),
    "Text.slice": lambda text, start, end: text[start:end],
    "Text.contains": lambda text, part: part in text,
    "Text.starts_with": lambda text, part: text.startswith(part),
    "Text.ends_with": lambda text, part: text.endswith(part),
    "Int.can_parse": can_parse_int,
    "Int.parse": parse_int,
    "Float.can_parse": can_parse_float,
    "Float.parse": parse_float,
    # Lists are immutable tuples: append and concat build a new value and never change
    # the one they receive. List.get is only reached after its 'needs' holds.
    "List.length": lambda xs: len(xs),
    "List.get": lambda xs, i: xs[i],
    "List.append": lambda xs, x: xs + (x,),
    "List.concat": lambda xs, ys: xs + ys,
    "List.contains": lambda xs, x: x in xs,
    # The inspection of an Option and a Result (decision 0016). The variant is part of the
    # value, so None is never Some(x) and Ok(x) is never Err(x).
    "Option.is_some": lambda value: value.kind == SOME,
    "Option.is_none": lambda value: value.kind == NONE,
    "Option.value_or": lambda value, fallback: value.payload if value.kind == SOME else fallback,
    "Result.is_ok": lambda value: value.kind == OK,
    "Result.is_err": lambda value: value.kind == ERR,
    "Result.value_or": lambda value, fallback: value.payload if value.kind == OK else fallback,
}


def some(value: Value) -> VariantValue:
    """`Some(value)`: an Option with a value."""
    return VariantValue(SOME, value)


def ok(value: Value) -> VariantValue:
    """`Ok(value)`: a Result that succeeded."""
    return VariantValue(OK, value)


def error(value: Value) -> VariantValue:
    """`Err(value)`: a Result that failed, with the error it failed with."""
    return VariantValue(ERR, value)

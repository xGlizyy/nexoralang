"""Runtime values of NEXORA and how they are named and printed.

A NEXORA value is represented by a Python `int`, `float`, `bool`, `str`, an
immutable tuple of values (a list) or a `RecordValue` (a record).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import RecordIdentity

INT_MIN = -(2 ** 63)
INT_MAX = 2 ** 63 - 1

INT = "Int"
FLOAT = "Float"
BOOL = "Bool"
TEXT = "Text"
VOID = "Void"

# The types a variable, a parameter or an expression can have. Void is only a return type.
VALUE_TYPES = (INT, FLOAT, BOOL, TEXT)


@dataclass(frozen=True)
class RecordValue:
    """A record value: the identity of its type, its name and its fields.

    Equality is by identity and by fields, never by the name alone: two declarations
    that look the same are still different types (decision 0014, 3). `fields` holds
    the name and the value of every field, in the order of the declaration.
    """

    identity: RecordIdentity
    type_name: str = field(compare=False)
    fields: tuple[tuple[str, Value], ...]

    def value_of(self, name: str) -> Value:
        """The value of the field `name`."""
        for field_name, value in self.fields:
            if field_name == name:
                return value
        raise KeyError(name)


Value = int | float | bool | str | RecordValue | tuple["Value", ...]


def format_value(value: Value) -> str:
    """The text `print` writes for a value, and what `to_text` returns."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Shortest text that reads back as the same Float; it always shows a '.' or an exponent.
        return repr(value)
    if isinstance(value, tuple):
        return "[" + ", ".join(format_value(item) for item in value) + "]"
    if isinstance(value, RecordValue):
        fields = ", ".join(f"{name}: {format_value(item)}" for name, item in value.fields)
        return f"{value.type_name}({fields})"
    return str(value)


def show_value(value: Value) -> str:
    """A value as it would be written in source code, for diagnostics: Text is quoted."""
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    if isinstance(value, tuple):
        return "[" + ", ".join(show_value(item) for item in value) + "]"
    if isinstance(value, RecordValue):
        fields = ", ".join(f"{name}: {show_value(item)}" for name, item in value.fields)
        return f"{value.type_name}({fields})"
    return format_value(value)

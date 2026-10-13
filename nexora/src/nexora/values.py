"""Runtime values of NEXORA and how they are named and printed.

A NEXORA value is represented by a Python `int`, `float`, `bool` or `str`.
"""

from __future__ import annotations

INT_MIN = -(2 ** 63)
INT_MAX = 2 ** 63 - 1

INT = "Int"
FLOAT = "Float"
BOOL = "Bool"
TEXT = "Text"
VOID = "Void"

# The types a variable, a parameter or an expression can have. Void is only a return type.
VALUE_TYPES = (INT, FLOAT, BOOL, TEXT)

Value = int | float | bool | str


def format_value(value: Value) -> str:
    """The text `print` writes for a value, and what `to_text` returns."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Shortest text that reads back as the same Float; it always shows a '.' or an exponent.
        return repr(value)
    return str(value)


def show_value(value: Value) -> str:
    """A value as it would be written in source code, for diagnostics: Text is quoted."""
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    return format_value(value)

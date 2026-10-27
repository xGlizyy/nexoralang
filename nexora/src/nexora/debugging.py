"""Events exposed by the optional statement-level debugger hook."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .diagnostics import Span
from .values import RecordValue, Value, VariantValue, show_value


@dataclass(frozen=True)
class DebugFrame:
    """One live function in a debug call stack; `call_site` is None for `main`."""

    function: str
    call_site: Span | None


@dataclass(frozen=True)
class DebugEvent:
    """State immediately before a statement runs."""

    step: int
    span: Span
    function: str
    call_stack: tuple[DebugFrame, ...]
    variables: tuple[tuple[str, Value], ...]


class DebugStop(Exception):
    """Internal control signal: stop before executing the event's statement."""

    def __init__(self, event: DebugEvent) -> None:
        super().__init__("debug session stopped")
        self.event = event


def format_debug_value(value: Value, *, max_chars: int = 256, depth: int = 0) -> str:
    """Render a value for an inspector without expanding large collections or texts."""
    if isinstance(value, str):
        limit = max(1, min(96, max_chars - 3))
        rendered = show_value(value[:limit])
        if len(value) > limit:
            rendered = rendered[:-1] + "…\""
        return rendered[:max_chars]
    if depth >= 3:
        if isinstance(value, (tuple, RecordValue, VariantValue)):
            return "…"
        return show_value(value)[:max_chars]
    if isinstance(value, tuple):
        items = [format_debug_value(item, max_chars=48, depth=depth + 1) for item in value[:8]]
        if len(value) > len(items):
            items.append("…")
        rendered = "[" + ", ".join(items) + "]"
    elif isinstance(value, RecordValue):
        fields = [f"{name}: {format_debug_value(item, max_chars=48, depth=depth + 1)}"
                  for name, item in value.fields[:8]]
        if len(value.fields) > len(fields):
            fields.append("…")
        rendered = f"{value.type_name}({', '.join(fields)})"
    elif isinstance(value, VariantValue):
        rendered = value.kind if value.payload is None else (
            f"{value.kind}({format_debug_value(value.payload, max_chars=48, depth=depth + 1)})"
        )
    else:
        rendered = show_value(value)
    return rendered if len(rendered) <= max_chars else rendered[:max_chars - 1] + "…"


DebugObserver = Callable[[DebugEvent], bool | None]

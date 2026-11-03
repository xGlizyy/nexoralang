"""Compare declared requirements between two checked NEXORA program versions.

The checker intentionally proves only a small, explicit fragment of condition implication.
Every other condition change is reported as changed with an unknown direction, never as safe.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast
from .diagnostics import Source
from .lexer import tokenize
from .pipeline import Analysis
from .tokens import TokenType
from .values import INT_MAX, INT_MIN
from .version import __version__


@dataclass(frozen=True)
class Requirement:
    module: str
    function: str
    scope: str
    clause: str
    name: str | None
    condition: str
    normalized: tuple
    message: str | None
    span: object
    condition_node: ast.Expr


Interval = tuple[int, int]
Intervals = tuple[Interval, ...]
UNIVERSE: Intervals = ((INT_MIN, INT_MAX),)


def _normalize(expression: ast.Expr, source: Source) -> tuple:
    fragment = Source(source.name, source.text_of(expression.span))
    tokens, _ = tokenize(fragment)
    return tuple((token.type.value, token.value if token.value is not None else token.lexeme)
                 for token in tokens if token.type not in (TokenType.NEWLINE, TokenType.EOF))


def _all_requirements(analysis: Analysis) -> list[Requirement]:
    project = analysis.project
    if project is None:
        return []
    result: list[Requirement] = []
    for module in project.modules:
        if module.program is None:
            continue
        module_name = "" if module is project.entry else module.path.replace("\\", "/")
        for function in module.program.functions:
            for contract in function.contracts:
                result.append(Requirement(
                    module_name, function.name, "function", contract.clause, contract.name,
                    module.source.text_of(contract.condition.span),
                    _normalize(contract.condition, module.source), contract.message,
                    contract.condition.span, contract.condition,
                ))

            loop_counts: dict[str, int] = {}

            def visit(block: ast.Block, parent: str = "function") -> None:
                for statement in block.statements:
                    if isinstance(statement, ast.If):
                        visit(statement.then_block, parent)
                        if isinstance(statement.else_branch, ast.Block):
                            visit(statement.else_branch, parent)
                        elif isinstance(statement.else_branch, ast.If):
                            visit(ast.Block(statement.else_branch.span, (statement.else_branch,)), parent)
                        elif isinstance(statement.else_branch, ast.IfLet):
                            visit(ast.Block(statement.else_branch.span, (statement.else_branch,)), parent)
                    elif isinstance(statement, ast.IfLet):
                        visit(statement.then_block, parent)
                        if isinstance(statement.else_branch, ast.Block):
                            visit(statement.else_branch, parent)
                        elif isinstance(statement.else_branch, ast.If):
                            visit(ast.Block(statement.else_branch.span, (statement.else_branch,)), parent)
                        elif isinstance(statement.else_branch, ast.IfLet):
                            visit(ast.Block(statement.else_branch.span, (statement.else_branch,)), parent)
                    elif isinstance(statement, (ast.While, ast.For)):
                        if isinstance(statement, ast.While):
                            loop_kind, head = "while", statement.condition
                        else:
                            loop_kind, head = "for", statement.iterable
                        head_key = repr(_normalize(head, module.source))
                        stem = f"{parent}/{loop_kind}:{head_key}"
                        loop_counts[stem] = loop_counts.get(stem, 0) + 1
                        scope = f"{stem}#{loop_counts[stem]}"
                        for clause in statement.clauses:
                            result.append(Requirement(
                                module_name, function.name, scope, clause.clause, clause.name,
                                module.source.text_of(clause.condition.span),
                                _normalize(clause.condition, module.source), clause.message,
                                clause.condition.span, clause.condition,
                            ))
                        visit(statement.body, scope)
                    elif isinstance(statement, ast.Block):
                        visit(statement, parent)

            visit(function.body)
    return result


def _merge(intervals: list[Interval]) -> Intervals:
    if not intervals:
        return ()
    intervals.sort()
    merged = [intervals[0]]
    for low, high in intervals[1:]:
        previous_low, previous_high = merged[-1]
        if low <= previous_high + 1:
            merged[-1] = (previous_low, max(previous_high, high))
        else:
            merged.append((low, high))
    return tuple(merged)


def _union(left: Intervals, right: Intervals) -> Intervals:
    return _merge(list(left + right))


def _intersect(left: Intervals, right: Intervals) -> Intervals:
    pieces = []
    for a, b in left:
        for c, d in right:
            low, high = max(a, c), min(b, d)
            if low <= high:
                pieces.append((low, high))
    return _merge(pieces)


def _complement(value: Intervals) -> Intervals:
    pieces = []
    start = INT_MIN
    for low, high in value:
        if start < low:
            pieces.append((start, low - 1))
        start = high + 1
    if start <= INT_MAX:
        pieces.append((start, INT_MAX))
    return tuple(pieces)


def _integer(node: ast.Expr) -> int | None:
    if isinstance(node, ast.IntLiteral):
        return node.value
    if isinstance(node, ast.Group):
        return _integer(node.expression)
    if isinstance(node, ast.Unary) and node.operator == "-":
        value = _integer(node.operand)
        return None if value is None else -value
    return None


def _simple_set(node: ast.Expr, variable: str | None = None) -> tuple[str | None, Intervals] | None:
    """Return a one-variable integer set when the expression is in the supported fragment."""
    if isinstance(node, ast.Group):
        return _simple_set(node.expression, variable)
    if isinstance(node, ast.BoolLiteral):
        return variable, UNIVERSE if node.value else ()
    if isinstance(node, ast.Unary) and node.operator == "not":
        inner = _simple_set(node.operand, variable)
        return None if inner is None else (inner[0], _complement(inner[1]))
    if isinstance(node, ast.Binary) and node.operator in {"and", "or"}:
        left = _simple_set(node.left, variable)
        if left is None:
            return None
        right = _simple_set(node.right, left[0])
        if right is None:
            return None
        if left[0] is not None and right[0] is not None and left[0] != right[0]:
            return None
        target = left[0] or right[0]
        if node.operator == "and":
            return target, _intersect(left[1], right[1])
        return target, _union(left[1], right[1])
    if not isinstance(node, ast.Binary) or node.operator not in {
        "==", "!=", "<", "<=", ">", ">=",
    }:
        return None

    left_variable = node.left.name if isinstance(node.left, ast.Name) else None
    right_variable = node.right.name if isinstance(node.right, ast.Name) else None
    left_number, right_number = _integer(node.left), _integer(node.right)
    if left_variable and right_number is not None and not right_variable:
        name, value, operator = left_variable, right_number, node.operator
    elif right_variable and left_number is not None and not left_variable:
        name, value = right_variable, left_number
        operator = {"<": ">", "<=": ">=", ">": "<", ">=": "<=",
                    "==": "==", "!=": "!="}[node.operator]
    elif left_number is not None and right_number is not None:
        valid = {"==": left_number == right_number, "!=": left_number != right_number,
                 "<": left_number < right_number, "<=": left_number <= right_number,
                 ">": left_number > right_number, ">=": left_number >= right_number}[node.operator]
        return variable, UNIVERSE if valid else ()
    elif left_variable and right_variable and left_variable == right_variable:
        valid = {"==": True, "!=": False, "<": False, "<=": True,
                 ">": False, ">=": True}[node.operator]
        return left_variable, UNIVERSE if valid else ()
    else:
        return None
    if variable is not None and variable != name:
        return None
    if operator == "==":
        intervals = ((value, value),) if INT_MIN <= value <= INT_MAX else ()
    elif operator == "!=":
        intervals = _complement(((value, value),)) if INT_MIN <= value <= INT_MAX else UNIVERSE
    elif operator == "<":
        intervals = ((INT_MIN, min(INT_MAX, value - 1)),) if value > INT_MIN else ()
    elif operator == "<=":
        intervals = ((INT_MIN, min(INT_MAX, value)),) if value >= INT_MIN else ()
    elif operator == ">":
        intervals = ((max(INT_MIN, value + 1), INT_MAX),) if value < INT_MAX else ()
    else:
        intervals = ((max(INT_MIN, value), INT_MAX),) if value <= INT_MAX else ()
    return name, intervals


def _subset(left: Intervals, right: Intervals) -> bool:
    return all(_intersect((item,), right) == (item,) for item in left)


def _direction(before: ast.Expr, after: ast.Expr) -> str:
    old_set = _simple_set(before)
    new_set = _simple_set(after)
    if old_set is None or new_set is None:
        return "unknown"
    if old_set[0] != new_set[0]:
        return "unknown"
    old_values, new_values = old_set[1], new_set[1]
    if old_values == new_values:
        return "equivalent"
    if _subset(old_values, new_values):
        return "weakened"
    if _subset(new_values, old_values):
        return "strengthened"
    return "incomparable"


def compare(before: Analysis, after: Analysis) -> dict:
    """Compare checked function clauses, conservatively identifying provable weakenings."""
    old = _all_requirements(before)
    new = _all_requirements(after)
    old_by_id = {(r.module, r.function, r.scope, r.name): r for r in old if r.name is not None}
    new_by_id = {(r.module, r.function, r.scope, r.name): r for r in new if r.name is not None}
    changes: list[dict] = []
    matched_old: set[int] = set()
    matched_new: set[int] = set()

    def add(status: str, old_item: Requirement | None, new_item: Requirement | None,
            direction: str | None = None) -> None:
        item = new_item or old_item
        changes.append({
            "module": item.module,
            "function": item.function,
            "scope": item.scope,
            "clause": item.clause,
            "name": item.name,
            "status": status,
            "direction": direction,
            "before": None if old_item is None else old_item.condition,
            "after": None if new_item is None else new_item.condition,
            "before_message": None if old_item is None else old_item.message,
            "after_message": None if new_item is None else new_item.message,
        })

    for identity in sorted(old_by_id.keys() & new_by_id.keys(), key=repr):
        a, b = old_by_id[identity], new_by_id[identity]
        matched_old.add(id(a)); matched_new.add(id(b))
        if a.clause != b.clause:
            add("kind_changed", a, b, "unknown")
        elif a.normalized != b.normalized:
            direction = _direction(a.condition_node, b.condition_node)
            status = "weakened" if direction == "weakened" else "condition_changed"
            add(status, a, b, direction)
        elif a.message != b.message:
            add("explanation_changed", a, b)

    remaining_named_old = [item for item in old if item.name is not None and id(item) not in matched_old]
    remaining_named_new = [item for item in new if item.name is not None and id(item) not in matched_new]
    rename_keys = {(item.module, item.function, item.scope, item.clause, item.normalized)
                   for item in remaining_named_old + remaining_named_new}
    for key in rename_keys:
        left = [item for item in remaining_named_old
                if (item.module, item.function, item.scope, item.clause, item.normalized) == key]
        right = [item for item in remaining_named_new
                 if (item.module, item.function, item.scope, item.clause, item.normalized) == key]
        if len(left) == len(right) == 1:
            a, b = left[0], right[0]
            matched_old.add(id(a)); matched_new.add(id(b))
            changes.append({"module": b.module, "function": b.function, "scope": b.scope, "clause": b.clause,
                            "name": b.name, "status": "renamed", "direction": None,
                            "before": a.condition, "after": b.condition,
                            "before_message": a.message, "after_message": b.message,
                            "previous_name": a.name})

    # Unnamed clauses can be matched only when their kind and token-normalized condition agree.
    unnamed_old: dict[tuple, list[Requirement]] = {}
    unnamed_new: dict[tuple, list[Requirement]] = {}
    for item in old:
        if item.name is None and id(item) not in matched_old:
            unnamed_old.setdefault((item.module, item.function, item.scope, item.clause, item.normalized), []).append(item)
    for item in new:
        if item.name is None and id(item) not in matched_new:
            unnamed_new.setdefault((item.module, item.function, item.scope, item.clause, item.normalized), []).append(item)
    for key in unnamed_old.keys() | unnamed_new.keys():
        left, right = unnamed_old.get(key, []), unnamed_new.get(key, [])
        for _ in range(min(len(left), len(right))):
            left.pop(); right.pop()
        if len(left) == len(right) == 1:
            a, b = left.pop(), right.pop()
            direction = _direction(a.condition_node, b.condition_node)
            status = "weakened" if direction == "weakened" else "condition_changed"
            add(status, a, b, direction)
        elif left and right:
            for item in left:
                add("ambiguous", item, None, "unknown")
            for item in right:
                add("ambiguous", None, item, "unknown")
            left.clear(); right.clear()
        for item in left:
            if item.name is None:
                add("removed", item, None, "weakened" if item.clause in {"needs", "promises"} else "unknown")
        for item in right:
            if item.name is None:
                add("added", None, item)

    for item in remaining_named_old:
        if id(item) not in matched_old:
            add("removed", item, None, "weakened" if item.clause in {"needs", "promises"} else "unknown")
    for item in remaining_named_new:
        if id(item) not in matched_new:
            add("added", None, item)

    changes.sort(key=lambda item: (item["module"], item["function"], item["scope"], item["name"] or "",
                                   item["clause"], item["status"], item["before"] or ""))
    return {"schema": "nexora.impact/1", "nexora_version": __version__, "ok": True,
            "diagnostics": [], "changes": changes,
            "summary": {"changes": len(changes),
                        "weakened": sum(item["direction"] == "weakened" for item in changes),
                        "removed": sum(item["status"] == "removed" for item in changes),
                        "unknown_direction": sum(item["direction"] == "unknown" for item in changes)}}


def render(document: dict) -> str:
    changes = document["changes"]
    if not changes:
        return "No requirement changes."
    lines = []
    for item in changes:
        location = f"{item['module'] + ':' if item['module'] else ''}{item['function']}"
        if item["scope"] != "function":
            location += f" [{item['scope']}]"
        if item["name"]:
            location += f".{item['name']}"
        if item["status"] == "removed":
            label = "POTENTIAL WEAKENING" if item["direction"] == "weakened" else "REMOVED"
            lines.append(f"{label}: {location} ({item['clause']})")
            lines.append(f"  before: {item['before']}")
        elif item["status"] == "weakened":
            lines.append(f"WEAKENED: {location} ({item['clause']})")
            lines.append(f"  before: {item['before']}")
            lines.append(f"  after:  {item['after']}")
        elif item["status"] == "added":
            lines.append(f"ADDED: {location} ({item['clause']})")
            lines.append(f"  after: {item['after']}")
        elif item["status"] == "condition_changed":
            lines.append(f"CHANGED, DIRECTION {item['direction'].upper()}: {location} ({item['clause']})")
            lines.append(f"  before: {item['before']}")
            lines.append(f"  after:  {item['after']}")
        else:
            lines.append(f"{item['status'].upper()}: {location} ({item['clause']})")
            if item["before"] is not None:
                lines.append(f"  before: {item['before']}")
            if item["after"] is not None:
                lines.append(f"  after:  {item['after']}")
    summary = document["summary"]
    lines.append(f"{summary['changes']} change(s); {summary['weakened']} proven weakening(s); "
                 f"{summary['unknown_direction']} change(s) with unknown direction.")
    lines.append("Only simple one-variable integer conditions are classified; unknown means review manually.")
    return "\n".join(lines)

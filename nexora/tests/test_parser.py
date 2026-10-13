import json

import pytest

from nexora import ast_nodes as ast
from nexora.parser import MAX_EXPRESSION_DEPTH, MAX_NESTING

from helpers import codes, in_main, parse_text


def parse_ok(text: str) -> ast.Program:
    program, errors = parse_text(text)
    assert errors == [], [error.label for error in errors]
    return program


def statements(body: str) -> tuple:
    return parse_ok(in_main(body)).functions[0].body.statements


def expression(text: str) -> ast.Expr:
    return statements(f"let x = {text}")[0].value


def shape(node) -> object:
    """Compact, position-free view of an expression, to compare structure."""
    if isinstance(node, ast.Binary):
        return (node.operator, shape(node.left), shape(node.right))
    if isinstance(node, ast.Unary):
        return (node.operator, shape(node.operand))
    if isinstance(node, ast.Group):
        return ("group", shape(node.expression))
    if isinstance(node, ast.Call):
        return ("call", node.callee, [shape(argument) for argument in node.arguments])
    if isinstance(node, ast.Name):
        return node.name
    return node.value


def errors_of(text: str):
    return parse_text(text)[1]


# Valid programs

def test_main_function():
    program = parse_ok('fn main() -> Void {\n    print("Hello from NEXORA")\n}\n')
    assert len(program.functions) == 1
    function = program.functions[0]
    assert function.name == "main"
    assert function.return_type.name == "Void"
    assert len(function.body.statements) == 1


def test_empty_program_and_empty_body():
    assert parse_ok("").functions == ()
    assert parse_ok("fn main() -> Void {}").functions[0].body.statements == ()


def test_function_on_one_line_and_with_brace_on_the_next():
    assert len(parse_ok("fn main() -> Void { print(1) }").functions[0].body.statements) == 1
    assert len(parse_ok("fn main() -> Void\n{\n    print(1)\n}").functions[0].body.statements) == 1


def test_several_functions_are_parsed():
    program = parse_ok("fn main() -> Void {}\n\nfn other() -> Void {}\n")
    assert [function.name for function in program.functions] == ["main", "other"]


def test_let_declaration():
    (statement,) = statements('let name = "NEXORA"')
    assert isinstance(statement, ast.Let)
    assert statement.name == "name"
    assert isinstance(statement.value, ast.TextLiteral) and statement.value.value == "NEXORA"
    assert statement.declared_type is None


def test_let_with_a_type_annotation():
    (statement,) = statements("let age: Int = 25")
    assert statement.name == "age"
    assert statement.declared_type.name == "Int"
    assert (statement.declared_type.span.column, statement.declared_type.span.end_column) == (14, 17)
    assert statement.value.value == 25


def test_literals():
    assert isinstance(expression("1"), ast.IntLiteral)
    assert isinstance(expression("1.5"), ast.FloatLiteral)
    assert isinstance(expression('"s"'), ast.TextLiteral)
    assert expression("true").value is True
    assert expression("false").value is False


def test_call_statement_and_arguments():
    (statement,) = statements("print(a, 2)")
    assert isinstance(statement, ast.ExprStatement)
    assert shape(statement.expression) == ("call", "print", ["a", 2])
    assert shape(statements("print()")[0].expression) == ("call", "print", [])


def test_assignment_is_parsed_as_its_own_statement():
    (statement,) = statements("x = 1")
    assert isinstance(statement, ast.Assign) and statement.name == "x"


def test_nested_blocks():
    (outer,) = statements("{\n    let a = 1\n    {\n        print(a)\n    }\n}")
    assert isinstance(outer, ast.Block)
    assert isinstance(outer.statements[1], ast.Block)


# Expressions and precedence

def test_multiplication_binds_tighter_than_addition():
    assert shape(expression("1 + 2 * 3")) == ("+", 1, ("*", 2, 3))
    assert shape(expression("1 * 2 + 3")) == ("+", ("*", 1, 2), 3)
    assert shape(expression("8 - 6 / 2")) == ("-", 8, ("/", 6, 2))


def test_operators_are_left_associative():
    assert shape(expression("10 - 4 - 3")) == ("-", ("-", 10, 4), 3)
    assert shape(expression("16 / 4 / 2")) == ("/", ("/", 16, 4), 2)


def test_parentheses_override_precedence():
    assert shape(expression("(1 + 2) * 3")) == ("*", ("group", ("+", 1, 2)), 3)


def test_unary_minus_binds_tighter_than_binary_operators():
    assert shape(expression("-a * b")) == ("*", ("-", "a"), "b")
    assert shape(expression("a - -b")) == ("-", "a", ("-", "b"))
    assert shape(expression("--1")) == ("-", ("-", 1))


def test_expression_can_continue_across_lines_inside_parentheses():
    assert shape(expression("(\n    1 +\n    2\n)")) == ("group", ("+", 1, 2))


def test_nodes_record_their_position():
    (statement,) = statements("let total = 10 + 5")
    binary = statement.value
    assert (statement.name_span.line, statement.name_span.column) == (2, 9)
    assert (binary.span.column, binary.span.end_column) == (17, 23)
    assert (binary.operator_span.column, binary.operator_span.end_column) == (20, 21)


def test_ast_converts_to_json():
    program = parse_ok(in_main("let x = 1 + 2"))
    document = json.loads(json.dumps(ast.to_dict(program)))
    let = document["functions"][0]["body"]["statements"][0]
    assert document["kind"] == "Program"
    assert let["kind"] == "Let" and let["name"] == "x"
    assert let["value"]["kind"] == "Binary" and let["value"]["operator"] == "+"
    assert let["value"]["left"] == {
        "kind": "IntLiteral",
        "span": {"line": 2, "column": 13, "end_line": 2, "end_column": 14},
        "value": 1,
    }


# Syntax errors

@pytest.mark.parametrize("body, code, line, column", [
    ('let = "Hello"', "E1101", 2, 9),          # missing name
    ("let x 5", "E1101", 2, 11),               # missing '='
    ("let x =", "E1101", 2, 12),               # missing value
    ("let x = 1 +", "E1101", 2, 16),           # incomplete expression
    ("let x = (1 + 2", "E1101", 2, 19),        # missing ')'
    ("let x = 1 2", "E1101", 2, 15),           # two expressions on one line
    ("print(1", "E1101", 2, 12),               # missing ')' in a call
    ("let x = )", "E1101", 2, 13),             # unexpected token
    ("let x = * 2", "E1101", 2, 13),           # operator with no left operand
    ("let while = 1", "E1103", 2, 9),          # reserved word as a name
    ("let true = 1", "E1101", 2, 9),           # keyword as a name
    ("let if = 1", "E1101", 2, 9),
    ("var x = 1", "E1103", 2, 5),              # reserved statement
    ("let x = match", "E1103", 2, 13),         # reserved word in an expression
    ("let x: = 1", "E1101", 2, 12),            # annotation without a type
    ("let x: Int", "E1101", 2, 15),            # annotation without a value
    ("fn inner() -> Void {}", "E1101", 2, 5),  # nested function
    ("let x = 1 < 2 < 3", "E1101", 2, 19),     # chained comparison
    ("let x = 1 ==", "E1101", 2, 17),          # comparison without a right side
    ("let x = not", "E1101", 2, 16),           # 'not' without an operand
    ("let x = a and", "E1101", 2, 18),         # 'and' without a right side
    ("if {\n}", "E1101", 2, 8),                # 'if' without a condition
    ("if true\nprint(1)", "E1101", 2, 12),     # 'if' without a block
    ("else {\n}", "E1101", 2, 5),              # 'else' without an 'if'
    ("if true {\n}\nelse {\n}", "E1101", 4, 5),   # 'else' on its own line
    ("let x = 1\nensures x > 0", "E1106", 3, 5),  # contract clause after a statement
    ("{\n    requires true\n}", "E1106", 3, 9),   # contract clause inside a nested block
])
def test_statement_errors(body, code, line, column):
    errors = errors_of(in_main(body))
    assert codes(errors) == [code], [error.label for error in errors]
    assert (errors[0].span.line, errors[0].span.column) == (line, column)


@pytest.mark.parametrize("text, code, line, column", [
    ("fn main() -> Void {\n    print(1)\n", "E1102", 3, 1),   # unclosed block
    ("fn main() -> Void {", "E1102", 1, 20),
    ("fn () -> Void {}", "E1101", 1, 4),                       # missing function name
    ("fn main -> Void {}", "E1101", 1, 9),                     # missing '('
    ("fn main( -> Void {}", "E1101", 1, 10),                   # missing ')'
    ("fn main() Void {}", "E1101", 1, 11),                     # missing '->'
    ("fn main() -> {}", "E1101", 1, 14),                       # missing return type
    ("fn main() -> Void", "E1101", 1, 18),                     # missing body
    ("fn main(name) -> Void {}", "E1101", 1, 13),              # parameter without a type
    ("fn main(name:) -> Void {}", "E1101", 1, 14),             # parameter with ':' but no type
    ("fn main(a: Int,) -> Void {}", "E1101", 1, 16),           # trailing comma
    ("fn main(a: Int b: Int) -> Void {}", "E1101", 1, 16),     # missing comma
    ("fn main(1) -> Void {}", "E1101", 1, 9),                  # not a parameter name
    ("fn main() -> Void {\n    requires\n}", "E1101", 2, 13),  # contract without a condition
    ("let x = 1", "E1101", 1, 1),                              # code outside a function
    ("fn main() -> Void {}\n}", "E1101", 2, 1),                # stray closing brace
])
def test_declaration_errors(text, code, line, column):
    errors = errors_of(text)
    assert codes(errors) == [code], [error.label for error in errors]
    assert (errors[0].span.line, errors[0].span.column) == (line, column)


def test_messages_say_what_was_expected():
    (error,) = errors_of(in_main('let = "Hello"'))
    assert error.label == "Expected a variable name after 'let', found '='"
    (error,) = errors_of(in_main("let x = (1 + 2"))
    assert error.label == "Expected ')', found the end of line"
    assert error.notes == ("The '(' was opened at line 2, column 13.",)


def test_unclosed_block_points_back_to_its_opening_brace():
    (error,) = errors_of("fn main() -> Void {\n    print(1)\n")
    assert error.notes == ("The block opened at line 1, column 19 is never closed.",)


def test_parser_recovers_and_reports_several_errors():
    errors = errors_of(in_main("let = 1\nlet ok = 2\nlet y 3\nprint(ok +)\nprint(ok)"))
    assert [(error.code, error.span.line) for error in errors] == [("E1101", 2), ("E1101", 4), ("E1101", 5)]


def test_recovery_continues_after_a_missing_parenthesis():
    errors = errors_of(in_main('print("a"\nlet x = \nprint(x)'))
    assert [(error.code, error.span.line) for error in errors] == [("E1101", 2), ("E1101", 3)]


def test_recovery_continues_with_the_next_function():
    program, errors = parse_text("fn broken( -> Void {\n    print(1)\n}\n\nfn main() -> Void {}\n\nfn () -> Void {}\n")
    assert [(error.code, error.span.line) for error in errors] == [("E1101", 1), ("E1101", 7)]
    assert [function.name for function in program.functions] == ["main"]


def test_deep_nesting_is_rejected_cleanly():
    depth = MAX_NESTING + 5
    assert codes(errors_of(in_main("let x = " + "(" * depth + "1" + ")" * depth))) == ["E1105"]
    assert codes(errors_of(in_main("let x = " + "-" * depth + "1"))) == ["E1105"]
    assert "E1105" in codes(errors_of(in_main("{" * depth + "}" * depth)))


def test_nesting_up_to_the_limit_is_accepted():
    depth = MAX_NESTING - 2
    parse_ok(in_main("let x = " + "(" * depth + "1" + ")" * depth))


def test_long_chains_have_a_limit():
    parse_ok(in_main("let x = " + " + ".join(["1"] * (MAX_EXPRESSION_DEPTH - 1))))
    assert codes(errors_of(in_main("let x = " + " + ".join(["1"] * (MAX_EXPRESSION_DEPTH + 5))))) == ["E1105"]

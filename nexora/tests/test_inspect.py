"""The structured view of a program used by `nex inspect` (schema nexora.inspect/2)."""

import json
from pathlib import Path

from nexora import ast_nodes as ast
from nexora.diagnostics import Source
from nexora.pipeline import analyze

SCHEMA_DOC = Path(__file__).resolve().parents[1] / "docs" / "inspect-schema.md"

PROGRAM = (
    "fn scale(value: Float, factor: Float) -> Float {\n"
    "    requires factor > 0.0\n"
    "    ensures result >= 0.0 or value < 0.0\n"
    "    let scaled: Float = value * factor\n"
    "    if scaled > 100.0 {\n"
    "        return 100.0\n"
    "    } else {\n"
    "        return scaled\n"
    "    }\n"
    "}\n"
    "\n"
    "fn main() -> Void {\n"
    '    let label = "x" + to_text(not true)\n'
    "    print(-scale(2.0, 1.5))\n"
    "}\n"
)

# Every node kind and its fields, in order. This is the contract of schema version 2:
# removing or renaming anything here requires a new schema version.
EXPECTED_FIELDS = {
    "Program": ["kind", "span", "types", "functions", "records"],
    "TypeDecl": ["kind", "span", "name", "name_span", "base", "condition", "message"],
    "RecordDecl": ["kind", "span", "name", "name_span", "fields"],
    "FieldDecl": ["kind", "span", "name", "name_span", "type"],
    "Function": ["kind", "span", "name", "name_span", "params", "return_type", "contracts", "body", "examples"],
    "Example": ["kind", "span", "condition", "message"],
    "Param": ["kind", "span", "name", "name_span", "type"],
    "TypeRef": ["kind", "span", "name", "arguments"],
    "Contract": ["kind", "span", "clause", "condition", "message"],
    "Block": ["kind", "span", "statements"],
    "Let": ["kind", "span", "name", "name_span", "declared_type", "value"],
    "Assign": ["kind", "span", "name", "name_span", "value"],
    "FieldAssign": ["kind", "span", "target", "name", "name_span", "value"],
    "Return": ["kind", "span", "value"],
    "If": ["kind", "span", "condition", "then_block", "else_branch"],
    "ExprStatement": ["kind", "span", "expression"],
    "IntLiteral": ["kind", "span", "value", "type"],
    "FloatLiteral": ["kind", "span", "value", "type"],
    "TextLiteral": ["kind", "span", "value", "type"],
    "BoolLiteral": ["kind", "span", "value", "type"],
    "ListLiteral": ["kind", "span", "elements", "type"],
    "Name": ["kind", "span", "name", "type"],
    "Unary": ["kind", "span", "operator", "operand", "type"],
    "Binary": ["kind", "span", "operator", "operator_span", "left", "right", "type"],
    "Group": ["kind", "span", "expression", "type"],
    "Call": ["kind", "span", "callee", "callee_span", "arguments", "qualifier", "type"],
    "RecordConstruction": ["kind", "span", "name", "name_span", "fields", "type"],
    "FieldInitializer": ["kind", "span", "name", "name_span", "value"],
    "FieldAccess": ["kind", "span", "target", "name", "name_span", "type"],
}


def inspect(text: str) -> dict:
    analysis = analyze(Source("test.nex", text))
    return json.loads(json.dumps(ast.to_dict(analysis.program, analysis.types)))


def walk(node):
    if isinstance(node, dict):
        if "kind" in node:
            yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def test_function_signature_and_contracts():
    scale = inspect(PROGRAM)["functions"][0]
    assert scale["name"] == "scale"
    assert [(p["name"], p["type"]["name"]) for p in scale["params"]] == [("value", "Float"), ("factor", "Float")]
    assert scale["return_type"]["name"] == "Float"
    assert [c["clause"] for c in scale["contracts"]] == ["requires", "ensures"]
    assert scale["contracts"][0]["condition"]["type"] == "Bool"
    assert scale["contracts"][0]["span"] == {"line": 2, "column": 5, "end_line": 2, "end_column": 26}


def test_statements_and_expressions_carry_kinds_types_and_positions():
    scale, main = inspect(PROGRAM)["functions"]
    let, branch = scale["body"]["statements"]
    assert (let["kind"], let["name"], let["declared_type"]["name"]) == ("Let", "scaled", "Float")
    assert let["value"] == {
        "kind": "Binary",
        "span": {"line": 4, "column": 25, "end_line": 4, "end_column": 39},
        "operator": "*",
        "operator_span": {"line": 4, "column": 31, "end_line": 4, "end_column": 32},
        "left": {"kind": "Name", "span": {"line": 4, "column": 25, "end_line": 4, "end_column": 30},
                 "name": "value", "type": "Float"},
        "right": {"kind": "Name", "span": {"line": 4, "column": 33, "end_line": 4, "end_column": 39},
                  "name": "factor", "type": "Float"},
        "type": "Float",
    }
    assert branch["kind"] == "If" and branch["condition"]["type"] == "Bool"
    assert branch["then_block"]["statements"][0]["kind"] == "Return"
    assert branch["else_branch"]["kind"] == "Block"

    label, call = main["body"]["statements"]
    assert label["declared_type"] is None and label["value"]["type"] == "Text"
    assert call["expression"]["callee"] == "print" and call["expression"]["type"] == "Void"
    assert call["expression"]["arguments"][0]["kind"] == "Unary"


def test_every_node_has_exactly_the_documented_fields():
    # A program that uses every node kind except Assign and FieldAssign (which are
    # always an error).
    seen = {}
    refined = 'type Small = Int where value < 10, "Small numbers only"\n'
    records = (
        "type Point = { x: Int, y: Int }\n"
        "fn origin() -> Point {\n"
        "    let p = Point(x: 0, y: 0)\n"
        "    return Point(x: p.x, y: p.y)\n"
        "}\n"
    )
    extra = (
        'fn extra(n: Small) -> Int {\n    example extra(1) == 2, "One more"\n'
        "    let xs: List[Int] = [1, 2]\n    return (n) + 1\n}\n"
    )
    for node in walk(inspect(refined + records + PROGRAM + "\n" + extra)):
        seen.setdefault(node["kind"], list(node))
    assert_fields(seen)
    assert set(seen) == set(EXPECTED_FIELDS) - {"Assign", "FieldAssign"}

    assign = inspect("fn main() -> Void {\n    let x = 1\n    x = 2\n}\n")["functions"][0]["body"]["statements"][1]
    assert list(assign) == EXPECTED_FIELDS["Assign"]

    field_assign = inspect(
        "type Point = { x: Int }\nfn main() -> Void {\n    let p = Point(x: 1)\n    p.x = 2\n}\n"
    )["functions"][0]["body"]["statements"][1]
    assert list(field_assign) == EXPECTED_FIELDS["FieldAssign"]


def assert_fields(seen: dict) -> None:
    for kind, names in seen.items():
        assert names == EXPECTED_FIELDS[kind], kind


def test_every_expression_of_a_valid_program_has_a_type():
    expression_kinds = {
        "IntLiteral", "FloatLiteral", "TextLiteral", "BoolLiteral", "ListLiteral", "Name", "Unary", "Binary",
        "Group", "Call",
    }
    for node in walk(inspect(PROGRAM)):
        if node["kind"] in expression_kinds:
            assert node["type"] in ("Int", "Float", "Bool", "Text", "Void"), node


def test_an_expression_that_could_not_be_typed_has_a_null_type():
    statements = inspect('fn main() -> Void {\n    let x = 1 + "a"\n    let y = missing\n}\n')["functions"][0]["body"]["statements"]
    assert statements[0]["value"]["type"] is None
    assert statements[0]["value"]["left"]["type"] == "Int"
    assert statements[1]["value"]["type"] is None


def test_spans_point_at_the_source_text():
    lines = PROGRAM.split("\n")
    for node in walk(inspect(PROGRAM)):
        span = node["span"]
        assert 1 <= span["line"] <= span["end_line"] <= len(lines)
        if node["kind"] == "Name":
            assert lines[span["line"] - 1][span["column"] - 1:span["end_column"] - 1] == node["name"]


def test_output_is_deterministic():
    assert json.dumps(inspect(PROGRAM)) == json.dumps(inspect(PROGRAM))


def test_the_schema_document_describes_every_node_kind_and_field():
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    assert "nexora.inspect/2" in text
    for kind, names in EXPECTED_FIELDS.items():
        assert f"`{kind}`" in text, kind
        for name in names:
            assert f"`{name}`" in text, (kind, name)


def test_refined_types_appear_in_the_tree_with_their_names():
    text = ('type Percent = Int where value >= 0 and value <= 100, "From 0 to 100"\n\n'
            "fn main() -> Void {\n    let n = 40\n    let p = Percent(n)\n    print(p + 1)\n}\n")
    program = inspect(text)
    (declaration,) = program["types"]
    assert (declaration["name"], declaration["base"]["name"], declaration["message"]) == ("Percent", "Int", "From 0 to 100")
    assert declaration["condition"]["type"] == "Bool"
    assert declaration["condition"]["left"]["left"] == {
        "kind": "Name", "span": {"line": 1, "column": 26, "end_line": 1, "end_column": 31}, "name": "value", "type": "Int",
    }
    _, let_p, call = program["functions"][0]["body"]["statements"]
    assert (let_p["value"]["kind"], let_p["value"]["callee"], let_p["value"]["type"]) == ("Call", "Percent", "Percent")
    # Arithmetic on a refined value gives its base type.
    assert call["expression"]["arguments"][0]["type"] == "Int"


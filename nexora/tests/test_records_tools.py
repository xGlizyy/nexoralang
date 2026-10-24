"""Las herramientas con registros: el árbol de `nex inspect` y el resumen de `nex context`.

Comprueba los campos nuevos que la decisión 0014 añade a los documentos (sección 6).
"""

from __future__ import annotations

from nexora import tooling
from nexora.diagnostics import Source
from nexora.pipeline import analyze

POINT = "type Point = { x: Int, y: Int }\n"


def test_the_tree_has_the_record_declaration():
    document = tooling.inspect_source(POINT + "fn main() {\n}\n")
    (record,) = document["program"]["records"]
    assert record["kind"] == "RecordDecl"
    assert record["name"] == "Point"
    assert [(field["name"], field["type"]["name"]) for field in record["fields"]] == [("x", "Int"), ("y", "Int")]


def test_the_tree_has_the_construction_and_the_access():
    document = tooling.inspect_source(
        POINT + "fn main() {\n    let p = Point(x: 1, y: 2)\n    print(p.x)\n}\n"
    )
    statements = document["program"]["functions"][0]["body"]["statements"]
    construction = statements[0]["value"]
    assert construction["kind"] == "RecordConstruction"
    assert construction["name"] == "Point"
    assert construction["type"] == "Point"
    assert [field["name"] for field in construction["fields"]] == ["x", "y"]
    access = statements[1]["expression"]["arguments"][0]
    assert access["kind"] == "FieldAccess"
    assert access["name"] == "x"
    assert access["type"] == "Int"
    assert access["target"]["kind"] == "Name"


def test_the_tree_of_a_program_without_records_has_an_empty_list():
    document = tooling.inspect_source("fn main() {\n}\n")
    assert document["program"]["records"] == []


def test_the_context_lists_the_records():
    document = tooling.get_context(POINT + "fn main() {\n    let p = Point(x: 1, y: 2)\n}\n")
    (record,) = document["records"]
    assert record["name"] == "Point"
    assert record["valid"] is True
    assert record["reason"] is None
    assert record["line"] == 1
    assert [(field["name"], field["type"]) for field in record["fields"]] == [("x", "Int"), ("y", "Int")]


def test_the_context_of_a_program_without_records_has_an_empty_list():
    document = tooling.get_context("fn main() {\n}\n")
    assert document["records"] == []


def test_the_context_says_that_a_record_that_cannot_be_used_is_not_valid():
    document = tooling.get_context("type A = { a: A }\nfn main() {\n}\n")
    (record,) = document["records"]
    assert record["valid"] is False
    assert record["reason"] is not None


def test_the_types_of_the_context_are_only_the_refined_ones():
    document = tooling.get_context(
        "type Small = Int where value < 10\n" + POINT + "fn main() {\n}\n"
    )
    assert [kind["name"] for kind in document["types"]] == ["Small"]
    assert [record["name"] for record in document["records"]] == ["Point"]


def test_the_features_of_the_context_say_that_the_program_uses_records():
    document = tooling.get_context(POINT + "fn main() {\n}\n")
    assert "records" in document["features"]


def test_the_features_of_a_program_without_records_do_not_say_it():
    document = tooling.get_context("fn main() {\n}\n")
    assert "records" not in document["features"]


def test_the_text_of_the_context_shows_the_records():
    text = tooling.render_context(tooling.get_context(POINT + "fn main() {\n}\n"))
    assert "Records (1):" in text
    assert "type Point = { x: Int, y: Int }" in text


def test_the_documents_of_a_program_with_records_hold_up():
    text = POINT + "fn main() {\n    let p = Point(x: 1, y: 2)\n    print(p.x)\n}\n"
    analysis = analyze(Source("test.nex", text))
    assert analysis.ok
    for document in (tooling.check_source(text), tooling.inspect_source(text),
                     tooling.get_symbols(text), tooling.get_context(text)):
        assert document["schema"].startswith("nexora.")

"""D01/I2: brackets and the syntax of list types, `List[T]`.

I2 builds the syntax tree. I3 then resolves `List[T]` in the checker and gives it
values and literals; indexing, the functions of `List` and `for` remain absent.
"""

from __future__ import annotations

import jsonschema
import pytest

from nexora import schemas, tooling
from nexora.tokens import TokenType as T

from helpers import diagnostics_of, in_main, lex, parse_text


def parsed(text: str):
    program, diagnostics = parse_text(text)
    assert diagnostics == [], [diagnostic.label for diagnostic in diagnostics]
    return program


def test_brackets_are_tokens() -> None:
    tokens, errors = lex("List[Int]")

    assert errors == []
    assert [token.type for token in tokens[:-1]] == [T.IDENT, T.LBRACKET, T.IDENT, T.RBRACKET]
    assert [token.lexeme for token in tokens[:-1]] == ["List", "[", "Int", "]"]


def test_a_list_type_in_a_let_annotation_is_built() -> None:
    program = parsed(in_main("let xs: List[Int] = 1"))

    declared = program.functions[0].body.statements[0].declared_type

    assert declared is not None
    assert declared.name == "List"
    assert [argument.name for argument in declared.arguments] == ["Int"]
    assert declared.span.end_column - declared.span.column == len("List[Int]")


def test_a_nested_list_type_in_a_var_annotation_is_built() -> None:
    program = parsed(in_main("var xs: List[List[Text]] = 1"))

    declared = program.functions[0].body.statements[0].declared_type

    assert declared is not None
    assert declared.name == "List"
    (inner,) = declared.arguments
    assert inner.name == "List"
    assert [argument.name for argument in inner.arguments] == ["Text"]


def test_list_types_in_parameters_and_return_type() -> None:
    program = parsed("fn copy(xs: List[Int]) -> List[List[Int]] {\n    return xs\n}\n")

    function = program.functions[0]
    (parameter,) = function.params
    assert parameter.type.name == "List"
    assert [argument.name for argument in parameter.type.arguments] == ["Int"]
    assert function.return_type.name == "List"
    assert [argument.name for argument in function.return_type.arguments] == ["List"]


def test_a_plain_type_has_no_arguments() -> None:
    program = parsed('fn f(x: Int) -> Text {\n    return ""\n}\n')

    assert program.functions[0].params[0].type.arguments == ()
    assert program.functions[0].return_type.arguments == ()


def test_inspect_exposes_the_type_arguments() -> None:
    document = tooling.inspect_source(in_main("let xs: List[List[Int]] = 1"))
    declared = document["program"]["functions"][0]["body"]["statements"][0]["declared_type"]

    assert list(declared) == ["kind", "span", "name", "arguments"]
    assert declared["name"] == "List"
    (inner,) = declared["arguments"]
    assert (inner["name"], inner["arguments"][0]["name"]) == ("List", "Int")
    assert inner["arguments"][0]["arguments"] == []

    jsonschema.validate(document, schemas.all_schemas()["nexora-inspect.schema.json"])


def test_inspect_keeps_an_empty_arguments_list_for_a_plain_type() -> None:
    document = tooling.inspect_source("fn f(x: Int) -> Void {\n}\n")
    reference = document["program"]["functions"][0]["params"][0]["type"]

    assert list(reference) == ["kind", "span", "name", "arguments"]
    assert reference["arguments"] == []


def test_the_inspect_schema_defines_the_type_arguments() -> None:
    definition = schemas.all_schemas()["nexora-inspect.schema.json"]["$defs"]["TypeRef"]

    assert definition["required"] == ["kind", "span", "name", "arguments"]
    assert definition["properties"]["arguments"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/TypeRef"},
    }


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("fn f(xs: List[]) -> Void {\n}\n", "needs a type argument"),
        ("fn f(xs: List[Int, Text]) -> Void {\n}\n", "exactly one type argument"),
        ("fn f(xs: List[Void]) -> Void {\n}\n", "Void cannot be an element"),
        ("fn f(xs: List[Option[Int]]) -> Void {\n}\n", "cannot take type arguments"),
        ("fn f(xs: Option[Int]) -> Void {\n}\n", "cannot take type arguments"),
        ("fn f(xs: Result[Int, Text]) -> Void {\n}\n", "cannot take type arguments"),
        ("fn f(xs: Foo[Int]) -> Void {\n}\n", "cannot take type arguments"),
        ("fn f(xs: Int[Text]) -> Void {\n}\n", "cannot take type arguments"),
        ("fn f(xs: List[Int) -> Void {\n}\n", "']' to close the type arguments"),
        ("fn f(xs: List[, Int]) -> Void {\n}\n", "Expected a type argument"),
        ("fn f(xs: List[Int,]) -> Void {\n}\n", "Expected a type argument"),
        ("fn f(xs: List[Int][Text]) -> Void {\n}\n", "Expected ')'"),
    ],
)
def test_malformed_list_types_are_syntax_errors(text: str, label: str) -> None:
    _, diagnostics = parse_text(text)

    assert [diagnostic.code for diagnostic in diagnostics] == ["E1101"]
    assert label in diagnostics[0].label


@pytest.mark.parametrize(
    "text",
    [
        in_main("let xs: List = 1"),
        in_main("var xs: List = 1"),
        "fn f(xs: List) -> Void {\n}\n\nfn main() -> Void {\n}\n",
        "fn f() -> List {\n    return 1\n}\n\nfn main() -> Void {\n}\n",
    ],
)
def test_the_bare_list_constructor_is_rejected_in_every_type_context(text: str) -> None:
    _, syntax = parse_text(text)
    assert syntax == []

    diagnostics = diagnostics_of(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2012"]
    assert diagnostics[0].label == "'List' is not a type"


def test_an_unknown_element_name_parses_but_the_checker_rejects_it() -> None:
    text = in_main("let xs: List[Missing] = 1")

    program, syntax = parse_text(text)
    declared = program.functions[0].body.statements[0].declared_type
    assert syntax == []
    assert declared is not None
    assert [argument.name for argument in declared.arguments] == ["Missing"]
    diagnostics = diagnostics_of(text)
    assert [diagnostic.code for diagnostic in diagnostics] == ["E2012"]
    assert diagnostics[0].label == "'Missing' is not a type"


def test_a_refined_type_named_list_does_not_hide_the_list_constructor() -> None:
    text = (
        "type List = Int where value > 0\n\n"
        "fn f(xs: List[Int]) -> Void {\n}\n\n"
        "fn main() -> Void {\n    let n: List = 1\n}\n"
    )

    diagnostics = diagnostics_of(text)

    assert diagnostics == ()


def test_a_refined_type_cannot_refine_a_list() -> None:
    text = (
        "type NonEmpty = List[Int] where value == value\n\n"
        "fn main() -> Void {\n}\n"
    )

    diagnostics = diagnostics_of(text)

    assert [diagnostic.code for diagnostic in diagnostics] == ["E2016"]
    assert "cannot refine a list type" in diagnostics[0].label


def test_type_nesting_uses_the_parser_limit() -> None:
    name = "List[" * 64 + "Int" + "]" * 64
    _, diagnostics = parse_text(f"fn f(x: {name}) -> Void {{\n}}\n")
    assert diagnostics == []

    too_deep = "List[" * 65 + "Int" + "]" * 65
    _, diagnostics = parse_text(f"fn f(x: {too_deep}) -> Void {{\n}}\n")
    assert [diagnostic.code for diagnostic in diagnostics] == ["E1105"]

"""Closed enums, pattern matching and compile-time exhaustiveness."""

import pytest

from helpers import check_codes, diagnostics_of, run_text, with_main
from nexora.tooling import get_context


def test_enum_constructor_match_and_payload_binding():
    source = with_main(
        "type Shape = enum { Circle(radius: Float), Square(side: Float) }\n"
        "fn area(shape: Shape) gives Float {\n"
        "    return match shape {\n"
        "        Shape.Circle(radius) => radius * radius\n"
        "        Shape.Square(side) => side * side\n"
        "    }\n"
        "}",
        "let shape = Shape.Circle(3.0)\nprint(area(shape))",
    )
    assert run_text(source) == "9.0\n"


def test_recursive_enum_payload_types_are_supported():
    source = with_main(
        "type Chain = enum { End, Link(next: Chain) }\n"
        "fn length(chain: Chain) gives Int {\n"
        "    return match chain {\n"
        "        End => 0\n"
        "        Link(next) => 1\n"
        "    }\n"
        "}",
        "print(length(Chain.Link(Chain.End())))",
    )
    assert run_text(source) == "1\n"


def test_nested_option_bool_patterns_are_checked_exhaustively():
    source = with_main(
        "fn describe(value: Option[Bool]) gives Int {\n"
        "    return match value {\n"
        "        None => 0\n"
        "        Some(true) => 1\n"
        "        Some(false) => 2\n"
        "    }\n"
        "}",
        "print(describe(Some(true)))",
    )
    assert run_text(source) == "1\n"


def test_missing_nested_constructor_pattern_has_witness():
    source = (
        "fn f(value: Option[Bool]) gives Int {\n"
        "    return match value {\n"
        "        None => 0\n"
        "        Some(true) => 1\n"
        "    }\n"
        "}\nfn main() {}"
    )
    (diagnostic,) = diagnostics_of(source)
    assert diagnostic.code == "E2032"
    assert "Some(false)" in diagnostic.label


def test_option_result_and_if_let_bind_payloads():
    source = with_main(
        "fn value(outcome: Result[Int, Text]) gives Int {\n"
        "    if let Ok(number) = outcome {\n"
        "        return number\n"
        "    } else {\n"
        "        return 0\n"
        "    }\n"
        "}",
        "print(value(Ok(8)))\nprint(value(Err(\"bad\")))",
    )
    assert run_text(source) == "8\n0\n"


@pytest.mark.parametrize("expression", [
    "match color { Red => 1 }",
    "match flag { true => 1 }",
    "match value { Some(_) => 1 }",
])
def test_non_exhaustive_closed_matches_are_rejected(expression):
    types = "type Color = enum { Red, Blue }\n"
    args = {"color": "Color", "flag": "Bool", "value": "Option[Int]"}
    name = next(key for key in args if key in expression)
    source = types + f"fn f({name}: {args[name]}) gives Int {{\n    return {expression}\n}}\nfn main() {{}}"
    assert "E2032" in check_codes(source)


def test_wildcard_makes_open_domain_match_exhaustive_and_later_arm_unreachable():
    source = "fn f(value: Text) gives Int {\n    return match value {\n        _ => 0\n        \"x\" => 1\n    }\n}\nfn main() {}"
    assert check_codes(source) == ["E2034"]


def test_context_reports_enumerations_and_pattern_matching_features():
    source = with_main("type State = enum { Ready, Busy }", "print(match State.Ready() { Ready => 1 Busy => 0 })")
    context = get_context(source)
    assert context["ok"]
    assert {"enumerations", "pattern_matching"}.issubset(context["features"])


def test_duplicate_enum_variant_and_bad_payload_arity_are_reported():
    duplicate = "type Color = enum { Red, Red }\nfn main() {}"
    assert check_codes(duplicate) == ["E2016"]
    bad_call = "type Color = enum { Rgb(red: Int, green: Int, blue: Int) }\nfn main() { let c = Color.Rgb(1) }"
    assert "E2035" in check_codes(bad_call)


def test_unknown_variant_and_wrong_pattern_arity_are_rejected():
    unknown = "type Color = enum { Red, Blue }\nfn f(c: Color) gives Int { return match c { Green => 0 _ => 1 } }\nfn main() {}"
    assert "E2033" in check_codes(unknown)
    wrong_arity = "fn f(value: Option[Int]) gives Int { return match value { Some => 1 None => 0 } }\nfn main() {}"
    assert "E2033" in check_codes(wrong_arity)


def test_variant_payload_constructor_and_nested_unreachable_arm():
    wrong_type = "type Item = enum { Count(value: Int) }\nfn main() { let item = Item.Count(\"x\") }"
    assert "E2011" in check_codes(wrong_type)
    nested_unreachable = (
        "fn f(value: Option[Bool]) gives Int {\n"
        "    return match value { None => 0 Some(_) => 1 Some(true) => 2 }\n"
        "}\nfn main() {}"
    )
    assert "E2034" in check_codes(nested_unreachable)\n
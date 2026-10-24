"""Operations on texts: functions that belong to a type and declare their requirements (decision 0011).

The numbers in brackets are the regression tests listed in the decision.
"""

import json
import random
import sys
from decimal import Decimal, getcontext
from pathlib import Path

import jsonschema
import pytest

from helpers import check_codes, diagnostics_of, in_main, lex, run_failure, run_text, with_main
from nexora import api, ast_nodes as ast, cli, prelude, schemas, tooling
from nexora.checker import BUILTINS, TYPE_FUNCTIONS
from nexora.diagnostics import Source
from nexora.interpreter import unparse
from nexora.pipeline import analyze
from nexora.tokens import TokenType
from nexora.values import INT_MAX, INT_MIN

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = schemas.all_schemas()


def lit(text: str) -> str:
    """A NEXORA text literal for `text`."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return '"' + escaped.replace("{", "\\{") + '"'


def value_of(expression: str) -> str:
    """What `print(expression)` writes, without the line break."""
    return run_text(in_main(f"print({expression})")).removesuffix("\n")


def failure_of(expression: str):
    return run_failure(in_main(f"print({expression})"))[1]


FAMILY = "\U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466"
E_ACUTE_COMBINED = "e\u0301"


# Semantics [1-5]

@pytest.mark.parametrize("expression, expected", [
    ('Text.length("")', "0"),
    ('Text.length("año")', "3"),
    (f"Text.length({lit(E_ACUTE_COMBINED)})", "2"),
    (f"Text.length({lit(FAMILY)})", "7"),
    ('Text.contains("hello", "ell")', "true"),
    ('Text.contains("hello", "")', "true"),
    ('Text.contains("", "")', "true"),
    ('Text.contains("", "a")', "false"),
    ('Text.contains("Hello", "hello")', "false"),
    ('Text.starts_with("hello", "he")', "true"),
    ('Text.starts_with("hello", "")', "true"),
    ('Text.starts_with("he", "hello")', "false"),
    ('Text.ends_with("hello", "lo")', "true"),
    ('Text.ends_with("hello", "")', "true"),
    ('Text.ends_with("", "a")', "false"),
])
def test_length_and_searching(expression, expected):  # [1]
    assert value_of(expression) == expected


@pytest.mark.parametrize("expression, expected", [
    ('Text.slice("hello", 1, 3)', "el"),
    ('Text.slice("hello", 0, 5)', "hello"),
    ('Text.slice("hello", 2, 2)', ""),
    ('Text.slice("hello", 5, 5)', ""),
    ('Text.slice("", 0, 0)', ""),
    ('Text.slice("año", 1, 2)', "ñ"),
])
def test_slice(expression, expected):  # [2]
    assert value_of(expression) == expected


@pytest.mark.parametrize("arguments, condition", [
    ('"hello", -1, 2', "start >= 0"),
    ('"hello", 3, 1', "start <= end"),
    ('"hello", 0, 6', "end <= Text.length(text)"),
    ('"hello", 6, 6', "end <= Text.length(text)"),
    ('"", 0, 1', "end <= Text.length(text)"),
    ('"hello", -3, -1', "start >= 0"),
    ('"abc", -1, 9', "start >= 0"),          # several broken: the first one written
])
def test_slice_outside_its_limits_is_e4001(arguments, condition):  # [2], [6]
    error = failure_of(f"Text.slice({arguments})")
    assert error.code == "E4001"
    assert error.notes[0] == f"The condition of the built-in function is false: needs {condition}"
    assert error.hint is None


@pytest.mark.parametrize("text", ["año", FAMILY, E_ACUTE_COMBINED + "x", "", "日本語テキスト"])
def test_the_equivalences_of_slice_hold_for_every_cut(text):  # [2]
    n = len(text)
    lines = []
    for a in range(n + 1):
        for b in range(a, n + 1):
            lines.append(f"print(Text.length(Text.slice(t, {a}, {b})) == {b - a})")
        lines.append(f"print(Text.slice(t, 0, {a}) + Text.slice(t, {a}, Text.length(t)) == t)")
        for p in {text[:a], text[a:]}:
            m = len(p)
            lines.append(f"print(Text.starts_with(t, {lit(p)}) == ({m} <= {n} and Text.slice(t, 0, {m}) == {lit(p)}))")
            lines.append(f"print(Text.ends_with(t, {lit(p)}) == ({m} <= {n} and Text.slice(t, {n - m}, {n}) == {lit(p)}))")
    output = run_text(in_main(f"let t = {lit(text)}\n" + "\n".join(lines)))
    assert set(output.split()) == {"true"}


@pytest.mark.parametrize("expression, expected", [
    ('"ab" < "abc"', "true"),
    ('"" < "a"', "true"),
    ('"Z" < "a"', "true"),
    ('"z" < "é"', "true"),
    ('"10" < "9"', "true"),
    (f'"é" == {lit(E_ACUTE_COMBINED)}', "false"),
    ('"abc" <= "abc"', "true"),
    ('"b" > "abc"', "true"),
    ('"abc" >= "abd"', "false"),
])
def test_texts_are_ordered_by_code_point(expression, expected):  # [3]
    assert value_of(expression) == expected


def test_a_text_and_another_type_cannot_be_ordered():  # [3]
    (error,) = diagnostics_of(in_main('let x = "1" < 2'))
    assert error.code == "E2011"
    assert "Convert one side" in error.hint and "Int.parse" in error.hint


def test_a_refined_text_is_ordered_as_its_base():  # [3]
    text = 'type Name = Text where value != ""\n' + in_main('let a: Name = "Ana"\nprint(a < "Zoe")\nprint("Zoe" < a)')
    assert run_text(text) == "true\nfalse\n"


INT_CASES = [
    ("0", 0), ("42", 42), ("-7", -7), ("007", 7), ("0000000000000000000000000042", 42), ("-0", 0),
    (str(INT_MAX), INT_MAX), (str(INT_MIN), INT_MIN),
    (str(INT_MAX + 1), None), (str(INT_MIN - 1), None), ("99999999999999999999", None),
    ("+5", None), (" 5", None), ("5 ", None), ("5\n", None), ("", None), ("-", None),
    ("1_000", None), ("1,000", None), ("٣", None), ("１", None), ("0x10", None),
    ("1.5", None), ("1e3", None),
]
FLOAT_CASES = [
    ("1.5", 1.5), ("-0.25", -0.25), ("0.0", 0.0), ("-0.0", -0.0), ("1e3", 1000.0), ("1e+16", 1e16),
    ("2.5E-3", 0.0025), ("1", None), (".5", None), ("5.", None), ("1e", None), ("1e+", None),
    ("+1.5", None), ("1,5", None), (" 1.5", None), ("inf", None), ("Infinity", None), ("nan", None),
    ("NaN", None), ("1e309", None), ("1e-400", 0.0), ("-1e-400", -0.0), ("5e-324", 5e-324),
    ("2.4703282292062328e-324", 5e-324), ("2.4703282292062327e-324", 0.0),
    ("1.7976931348623157e308", 1.7976931348623157e308), ("1.7976931348623158e308", 1.7976931348623157e308),
    ("1.7976931348623159e308", None), ("1_000.0", None), ("0x1p3", None),
]


@pytest.mark.parametrize("text, value", INT_CASES)
def test_the_grammar_of_an_int(text, value):  # [4]
    assert prelude.can_parse_int(text) is (value is not None)
    assert value_of(f"Int.can_parse({lit(text)})") == ("true" if value is not None else "false")
    if value is not None:
        assert value_of(f"Int.parse({lit(text)})") == str(value)


@pytest.mark.parametrize("text, value", FLOAT_CASES)
def test_the_grammar_of_a_float(text, value):  # [4], [5]
    assert prelude.can_parse_float(text) is (value is not None)
    if value is not None:
        parsed = prelude.parse_float(text)
        assert parsed == value and str(parsed).startswith("-") == str(value).startswith("-")


MILLION = 1_000_000


@pytest.mark.parametrize("text, as_int, as_float", [
    ("9" * MILLION, False, False),                  # far outside both ranges
    ("0" * MILLION + "42", True, False),            # a small value behind many zeros
    ("1" * MILLION + "x", False, False),            # not a number, found only at the end
    ("1" * MILLION + ".5", False, False),           # an enormous mantissa: infinite
    ("0." + "0" * MILLION + "1", False, True),      # a tiny value: rounds to 0.0
    ("1e" + "9" * MILLION, False, False),           # an enormous exponent: infinite
    ("1e-" + "9" * MILLION, False, True),           # an enormous negative exponent: 0.0
], ids=["nines", "zeros", "letter", "mantissa", "tiny", "exponent", "negative-exponent"])
def test_enormous_texts_get_an_answer_and_never_an_internal_error(text, as_int, as_float):  # [4]
    # Converted naively, more than 4300 digits would raise ValueError in Python (decision 0011, 6.4).
    assert (prelude.can_parse_int(text), prelude.can_parse_float(text)) == (as_int, as_float)
    if as_int:
        assert prelude.parse_int(text) == 42
    if as_float:
        assert prelude.parse_float(text) == 0.0


def test_an_enormous_text_through_the_language():  # [4]
    digits = "0" * 100_000 + "7"
    assert value_of(f'Int.parse("{digits}") + Text.length("{digits}")') == str(7 + 100_001)
    assert value_of(f'Int.can_parse("{"9" * 100_000}")') == "false"


def test_the_midpoints_of_the_float_limits():  # [5]
    getcontext().prec = 1200
    half_of_smallest = Decimal(1) / Decimal(2 ** 1075)
    assert prelude.parse_float(str(half_of_smallest).replace("E", "e")) == 0.0
    assert prelude.parse_float(str(half_of_smallest + Decimal("1e-1100")).replace("E", "e")) == 5e-324
    midpoint = Decimal(2 ** 1024) - Decimal(2 ** 970)
    assert not prelude.can_parse_float(f"{midpoint}.0")
    assert prelude.parse_float(f"{midpoint - 1}.0") == 1.7976931348623157e308


def test_float_conversion_is_correctly_rounded_here():  # [5]
    assert sys.float_repr_style == "short"


def test_round_trips():  # [5]
    for n in (0, 1, -1, INT_MAX, INT_MIN, 42, -9223372036854775807):
        assert value_of(f"Int.parse(to_text({n if n != INT_MIN else '-9223372036854775807 - 1'}))") == str(n)
    generator = random.Random(11)
    floats = [0.0, -0.0, 5e-324, 1.7976931348623157e308, 1e16, 1e-5, 0.1]
    while len(floats) < 3000:
        x = generator.uniform(-1.0, 1.0) * 10.0 ** generator.randint(-320, 307)
        floats.append(x)
    for x in floats:
        written = repr(x)                    # what to_text writes for a Float
        assert prelude.can_parse_float(written) and prelude.parse_float(written) == x, written
    program = in_main("\n".join(f"print(Float.parse(to_text({x!r})) == {x!r})" for x in (1.5, 0.1, 123.0)))
    assert run_text(program) == "true\n" * 3


# Requirements [6-10]

def test_the_e4001_of_a_built_in_function():  # [6]
    text = with_main("fn shorten(word: Text) gives Text {\n    return Text.slice(word, 2, 9)\n}", 'print(shorten("abc"))')
    _, error = run_failure(text)
    assert (error.code, error.category, error.label) == (
        "E4001", "contract", "This call breaks a 'needs' condition of 'Text.slice'")
    assert error.notes == (
        "The condition of the built-in function is false: needs end <= Text.length(text)",
        "Reason: A slice cannot end after the last character",
        'It was called with: text = "abc", start = 2, end = 9',
        "In 'shorten', called at line 6, column 11.",
    )
    assert (error.span.line, error.span.column, error.span.end_column) == (2, 12, 34)


@pytest.mark.parametrize("call, hint", [
    ('Int.parse("12a")', "Check the text first with Int.can_parse(...), and call Int.parse only when it is true."),
    ('Int.parse("1.5")', "Check the text first with Int.can_parse(...), and call Int.parse only when it is true."),
    ('Int.parse("99999999999999999999")', f"Int holds whole numbers from {INT_MIN} to {INT_MAX}."),
    ('Float.parse("1")', "This text is a whole number: read it with to_float(Int.parse(...))."),
    ('Float.parse("abc")', "Check the text first with Float.can_parse(...), and call Float.parse only when it is true."),
    ('Float.parse("1e309")', "The number is too large for a Float."),
])
def test_the_hints_of_reading_a_number(call, hint):  # [6]
    error = failure_of(call)
    assert error.code == "E4001" and error.hint == hint


def test_an_int_out_of_range_is_never_an_overflow():  # [6]
    error = failure_of(f'Int.parse("{INT_MAX + 1}")')
    assert error.code == "E4001" and error.notes[1] == (
        "Reason: Only a whole number within the range of Int can be read as an Int")


def test_an_error_in_an_argument_comes_before_any_requirement():  # [7]
    assert failure_of('Text.slice("abc", 1 / 0, 9)').code == "E3001"


def test_and_and_or_do_not_check_what_they_do_not_evaluate():  # [8]
    assert value_of('Int.can_parse("x") and Int.parse("x") > 0') == "false"
    assert value_of('Text.length("") == 0 or Text.slice("", 0, 1) == ""') == "true"


@pytest.mark.parametrize("name", sorted(prelude.CONTRACTS))
def test_the_built_in_contracts_are_valid_nexora_that_cannot_fail(name):  # [9]
    signature = BUILTINS[name]
    # A parametric contract is probed with a concrete instance of its type variables.
    concrete = {
        "List.get": ("xs: List[Int], i: Int", "Int"),
    }.get(name)
    if concrete is None:
        params = ", ".join(f"{param}: {kind}" for param, kind in signature.params)
        return_type = signature.return_type
    else:
        params, return_type = concrete
    some_value = {"Int": "0", "Float": "0.0", "Text": '""', "Bool": "true"}[return_type]
    for contract in prelude.CONTRACTS[name]:
        # The clause, checked by the real checker in a function with the same parameters and result.
        program = (f"fn probe({params}) gives {return_type}\n    {contract.clause} {contract.source}\n{{\n"
                   f"    return {some_value}\n}}\n") + in_main("")
        assert check_codes(program) == [], (name, contract.source)
        assert unparse(contract.condition) == contract.source
        # Only functions that have an answer for any text or any list.
        called = {node.callee for node in _walk(contract.condition) if isinstance(node, ast.Call)}
        assert called <= {"Text.length", "Int.can_parse", "Float.can_parse", "List.length"}
        assert not any(isinstance(node, ast.Binary) and node.operator == "/" for node in _walk(contract.condition))


def _walk(node):
    yield node
    for child in (getattr(node, name, None) for name in ("left", "right", "operand", "expression")):
        if child is not None:
            yield from _walk(child)
    for argument in getattr(node, "arguments", ()):
        yield from _walk(argument)


def test_the_ensures_hold_in_every_case_of_the_tests():  # [9]
    texts = ["", "a", "año", FAMILY, E_ACUTE_COMBINED, "hello", "0" * 1000]
    for text in texts:
        assert prelude.IMPLEMENTATIONS["Text.length"](text) >= 0
        for a in range(len(text) + 1):
            for b in range(a, min(len(text), a + 8) + 1):
                assert len(prelude.IMPLEMENTATIONS["Text.slice"](text, a, b)) == b - a


def test_each_interface(capsys, tmp_path):  # [10]
    program = in_main('print("before")\nprint(Int.parse("x"))')
    path = tmp_path / "p.nex"
    path.write_text(program, encoding="utf-8")
    assert cli.main(["run", str(path)]) == 5
    assert "contract error[E4001]" in capsys.readouterr().err
    assert cli.main(["run", str(path), "--format", "json"]) == 5
    document = json.loads(capsys.readouterr().err)
    jsonschema.validate(document, SCHEMAS["nexora-diagnostics.schema.json"])
    assert document["diagnostics"][0]["hint"].startswith("Check the text first with Int.can_parse")
    result = api.run_source(program)
    assert (result["status"], result["output"]) == ("contract_violation", "before\n")
    examples = 'fn f(t: Text) gives Int\n    example f("x") == 1\n    example f("2") == 2\n{\n    return Int.parse(t)\n}\n'
    report = api.test_source(examples)
    assert [example["status"] for example in report["examples"]] == ["error", "passed"]
    assert report["examples"][0]["diagnostic"]["code"] == "E4001"


def test_a_refinement_that_breaks_a_built_in_requirement():  # [10]
    declaration = 'type Short = Text where Text.slice(value, 0, 2) != "xx"\n'
    _, error = run_failure(declaration + in_main('let s = Short(to_text(1))\nprint(s)'))
    assert error.code == "E4001" and error.notes[0].startswith("While checking that a value is a valid Short")
    (constant,) = diagnostics_of(declaration + in_main('let s: Short = "a"'))
    assert constant.code == "E2017" and "cannot be checked" in constant.label


def test_a_built_in_requirement_inside_a_contract_of_the_program():  # [10]
    text = with_main('fn f(t: Text) gives Int\n    needs Int.parse(t) > 0\n{\n    return 1\n}', 'print(f("x"))')
    assert run_failure(text)[1].code == "E4001"


# Qualified calls [11-19]

def test_qualified_calls_in_every_position():  # [11]
    text = (
        'type Code = Text where Text.length(value) == 3, "Three characters"\n'
        'fn f(t: Text) gives Int\n'
        '    needs Text.length(t) > 0\n'
        '    promises result == Text.length(t)\n'
        '    example f(Text.slice("abcd", 0, 2)) == 2\n'
        '{\n'
        '    var i = 0\n'
        '    while i < Text.length(t)\n'
        '        keeps i <= Text.length(t)\n'
        '        shrinks Text.length(t) - i\n'
        '    {\n'
        '        i = i + 1\n'
        '    }\n'
        '    return Text.length(Text.slice(t, 0, i))\n'
        '}\n'
    ) + in_main('let c: Code = "NEX"\nprint(f(c) + Int.parse(to_text(Text.length(c))))')
    assert run_text(text) == "6\n"
    assert api.test_source(text)["status"] == "passed"


@pytest.mark.parametrize("call, label, hint, note", [
    ("Texto.length(t)", "There is no type named 'Texto'", "Did you mean 'Text'?", None),
    # `geometry.area(t)`: a name in lower case before the '.' can only be a module, so it
    # is not this error any more but E2027. It is asserted in tests/test_modules.py.
    ("Percent.parse(t)", "'Percent' has no functions of its own",
     "A value of Percent can be passed to the functions of its base type, Int.", None),
    ("Bool.parse(t)", "'Bool' has no function named 'parse'", None, "Bool has no functions yet."),
    ("print.x(t)", "'print' is a function, not a type", None, None),
    ("Text.lenght(t)", "'Text' has no function named 'lenght'", "Did you mean 'Text.length'?",
     "The functions of Text: contains, ends_with, length, slice, starts_with."),
    ("Int.length(t)", "'Int' has no function named 'length'", None, "The functions of Int: can_parse, parse."),
])
def test_unknown_qualified_calls(call, label, hint, note):  # [12], [13]
    text = "type Percent = Int where value >= 0\n" + in_main(f'let t = "x"\nlet n = {call}')
    (error,) = diagnostics_of(text)
    assert (error.code, error.label, error.hint) == ("E2008", label, hint)
    assert error.notes == ((note,) if note else ())


@pytest.mark.parametrize("call, hint", [
    ("length(t)", "Did you mean 'List.length' or 'Text.length'?"),
    ("parse(t)", "Did you mean 'Float.parse' or 'Int.parse'?"),
    ("lenght(t)", "Did you mean 'List.length' or 'Text.length'?"),
    ("to_txt(1)", "Did you mean 'to_text'?"),
])
def test_an_unqualified_name_suggests_the_function_of_a_type(call, hint):  # [13]
    (error,) = diagnostics_of(in_main(f'let t = "x"\nlet n = {call}'))
    assert (error.code, error.hint) == ("E2008", hint)


@pytest.mark.parametrize("body, label", [
    ("let f = Text.length", "Expected '(' to call 'Text.length'"),
    ('let n = Text.("x")', "Expected the name of a function after 'Text.'"),
    ("let n = Text.\nprint(1)", "Expected the name of a function after 'Text.'"),
    ('let n = Text . length("x")', "Write 'Text.length' without spaces around the '.'"),
    ('print(Text\n.length("x"))', "Write 'Text.length' without spaces around the '.'"),
    ('let n = Text.length.x("x")', "Expected '(' after 'Text.length', found '.'"),
    ('let n = .length("x")', "Expected a value or an expression, found '.'"),
    ("let n = 1.length", "Expected the end of the line after this statement, found '.'"),
    ("let n = .5", "Expected a value or an expression, found '.'"),
    ("let n = 1.5.2", "Expected the end of the line after this statement, found '.'"),
    ('let n = Text.length("x").y', "Expected the end of the line after this statement, found '.'"),
])
def test_syntax_errors_with_the_dot(body, label):  # [14]
    errors = diagnostics_of(in_main(body))
    assert errors[0].code == "E1101" and errors[0].label == label


def test_the_end_of_a_line_before_the_dot_ends_the_statement():  # [14]
    errors = diagnostics_of("fn main() {\n    let n = Text\n    .length(\"x\")\n}\n")
    assert [e.label for e in errors if e.code == "E1101"] == ["Expected a value or an expression, found '.'"]


def test_a_program_cannot_declare_a_function_of_a_type():  # [14]
    (error,) = diagnostics_of("fn Text.length(t: Text) gives Int {\n    return 0\n}\n" + in_main(""))
    assert error.code == "E1101" and error.hint.startswith("Only the language defines functions of a type")


def test_spaces_before_the_parenthesis_are_allowed():  # [14]
    assert value_of('Text.length ("abc")') == "3"


@pytest.mark.parametrize("declaration, hint", [
    ('let name = "abc"', "Call the function of its type: Text.length(name)"),
    ("let name = 3", None),
])
def test_a_value_before_the_dot(declaration, hint):  # [15]
    (error,) = diagnostics_of(in_main(f"{declaration}\nlet n = name.length()"))
    assert error.code == "E2008" and error.label == "'name' is a variable: values have no functions of their own"
    assert error.hint == hint


def test_common_names_stay_free():  # [16]
    text = with_main(
        "fn size(length: Int, slice: Text, contains: Bool) gives Int {\n    return length + Text.length(slice)\n}",
        'let length = Text.length("abcd")\nvar contains = Text.contains("ab", "b")\nprint(size(length, "xy", contains))',
    )
    assert run_text(text) == "6\n"


def test_variables_named_like_the_types_stay_valid():  # [17]
    text = with_main(
        "fn twice(Text: Int) gives Int {\n    return Text * 2\n}",
        'let Text = 1\nlet Int = "abc"\nprint(Text.length(Int) + twice(Text))',
    )
    assert run_text(text) == "5\n"


OLD_PROGRAMS = sorted(path for path in (ROOT / "examples").rglob("*.nex")
                       if "modules" not in path.parts
                       and path.name not in ("texts.nex", "parse_number.nex", "lists.nex", "records.nex",
                                             "option_result.nex"))


@pytest.mark.parametrize("path", OLD_PROGRAMS, ids=lambda path: path.name)
def test_programs_of_0_5_1_have_no_dot_and_no_qualified_call(path):  # [18]
    text = path.read_text(encoding="utf-8")
    tokens, _ = lex(text)
    assert TokenType.DOT not in {token.type for token in tokens}
    document = tooling.inspect_source(text, path.name)
    calls = [node for node in _nodes(document) if node.get("kind") == "Call"]
    assert all(call["qualifier"] is None and "." not in call["callee"] for call in calls)


# Tools [20-21]

def _nodes(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nodes(item)


def _schema_of_0_5_1() -> dict:
    path = Path(__file__).parent / "golden" / "schemas" / "nexora-inspect-0.5.1.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_inspect_has_a_qualifier_in_every_call():  # [20]
    text = in_main('let s = "abc"\nprint(Text.length(s))')
    document = tooling.inspect_source(text)
    calls = {node["callee"]: node for node in _nodes(document) if node.get("kind") == "Call"}
    assert list(calls["print"]) == ["kind", "span", "callee", "callee_span", "arguments", "qualifier", "type"]
    assert calls["print"]["qualifier"] is None
    length = calls["Text.length"]
    assert (length["qualifier"], length["type"]) == ("Text", "Int")
    assert (length["callee_span"]["column"], length["callee_span"]["end_column"]) == (11, 22)
    jsonschema.validate(document, SCHEMAS["nexora-inspect.schema.json"])
    # `nexora.inspect/3` (decision 0019, 8.8) is not a document of the schema of 0.5.1 any more.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, _schema_of_0_5_1())


def test_a_consumer_of_0_5_1_never_takes_a_qualified_call_for_a_name_of_the_program():  # [20]
    text = with_main("fn size(length: Int) gives Int {\n    return length\n}", 'let name = "abc"\nprint(size(Text.length(name)))')
    document = tooling.inspect_source(text)
    names = {node.get("name") for node in _nodes(document) if node.get("kind") in ("Param", "Let", "Var", "Function")}
    old_builtins = {"print", "to_text", "to_float", "to_int"}
    for call in (node for node in _nodes(document) if node.get("kind") == "Call"):
        if call["callee"] not in names and call["callee"] not in old_builtins:
            assert call["callee"] == "Text.length"     # "unknown" for that consumer, never 'length'


def test_symbols_describe_the_functions_of_the_types():  # [21]
    document = tooling.get_symbols(in_main("print(1)"))
    jsonschema.validate(document, SCHEMAS["nexora-symbols.schema.json"])
    builtins = {entry["name"]: entry for entry in document["builtins"]}
    assert set(builtins) == set(BUILTINS)
    slice_ = builtins["Text.slice"]
    assert slice_["signature"] == "fn Text.slice(text: Text, start: Int, end: Int) gives Text"
    assert [(c["clause"], c["condition"], c["checked_at_run_time"]) for c in slice_["contracts"]] == [
        ("needs", "start >= 0", True), ("needs", "start <= end", True),
        ("needs", "end <= Text.length(text)", True), ("promises", "Text.length(result) == end - start", False),
    ]
    assert builtins["print"]["contracts"] == [] and builtins["Text.contains"]["contracts"] == []
    assert {name.split(".")[0] for name in BUILTINS if "." in name} == set(TYPE_FUNCTIONS)


def test_context_names_the_functions_of_the_types_and_their_requirements():  # [21]
    text = with_main('fn first(t: Text) gives Text {\n    return Text.slice(t, 0, 1)\n}', 'print(first("ab") < "b")')
    document = tooling.get_context(text)
    jsonschema.validate(document, SCHEMAS["nexora-context.schema.json"])
    first = next(f for f in document["functions"] if f["name"] == "first")
    assert first["builtins_called"] == ["Text.slice"] and first["calls"] == []
    assert "text_operations" in document["features"]
    rendered = tooling.render_context(document)
    assert "      built-ins: Text.slice\n          Text.slice needs start >= 0\n" in rendered
    assert "              reason: A slice cannot end after the last character" in rendered
    assert "text_operations" not in tooling.get_context(in_main("print(1 < 2)"))["features"]
    ordering = tooling.get_context('type Name = Text where value != ""\n' + in_main('let a: Name = "x"\nprint(a < "y")'))
    assert "text_operations" in ordering["features"]


def test_the_capabilities_list_the_functions_with_their_contracts():  # [21]
    document = tooling.get_capabilities()
    entries = {entry["name"]: entry for entry in document["language"]["builtins"]}
    assert entries["Int.parse"]["contracts"][0]["condition"] == "Int.can_parse(text)"
    jsonschema.validate(document, SCHEMAS["nexora-capabilities.schema.json"])


def test_the_checker_knows_every_implementation():
    # Every function of a type is implemented: the pure ones in the prelude, and the three that
    # can fail in the interpreter, which needs the position of the argument to say where the
    # variant was wrong.
    failing = {"Option.value", "Result.value", "Result.error"}
    of_a_type = {name for name in BUILTINS if "." in name}
    assert of_a_type - failing == set(prelude.IMPLEMENTATIONS)
    assert failing <= of_a_type
    assert set(prelude.CONTRACTS) <= set(prelude.IMPLEMENTATIONS)
    assert analyze(Source("t.nex", in_main("print(1)"))).ok


def test_the_defensive_paths_of_the_prelude():
    # The interpreter only calls these once their 'needs' hold; called without, they refuse.
    with pytest.raises(ValueError):
        prelude.parse_int("12a")
    with pytest.raises(ValueError):
        prelude.parse_float("1")
    # A built-in condition that is not valid NEXORA is a defect, found when the module loads.
    with pytest.raises(ValueError):
        prelude._contract("needs", "start >=", "broken")
    with pytest.raises(ValueError):
        prelude._contract("needs", "start ` 0", "broken")
    with pytest.raises(ValueError):
        prelude._contract("needs", "start >= 0 0", "broken")

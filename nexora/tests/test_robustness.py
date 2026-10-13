"""Malformed, truncated, huge and deeply nested input never makes NEXORA fail on its own.

Whatever the input, the toolchain either accepts the program or returns diagnostics. A Python
exception escaping from `analyze` would be an internal error (exit code 70): a defect.

Includes the regression tests for the defects found while auditing the project.
"""

import random
import re
from pathlib import Path

import pytest

from nexora import ast_nodes as ast
from nexora import cli
from nexora.diagnostics import MAX_DIAGNOSTICS, NexoraRuntimeError, Source, render
from nexora.interpreter import MAX_CALL_DEPTH, run
from nexora.pipeline import analyze

from helpers import check_codes, codes, in_main, lex, run_failure, run_text, with_main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
VALID_EXAMPLES = sorted(EXAMPLES.glob("*.nex"))


def survives(text: str) -> None:
    """Runs every stage on `text`. Fails if anything but a NEXORA diagnostic comes out."""
    source = Source("fuzz.nex", text)
    analysis = analyze(source)
    for diagnostic in analysis.diagnostics:
        render(diagnostic, source)
        diagnostic.to_dict(source.name)
        assert diagnostic.span is None or (diagnostic.span.line >= 1 and diagnostic.span.column >= 1)
    if analysis.program is not None:
        ast.to_dict(analysis.program, analysis.types)
    if analysis.checked is not None:
        try:
            run(analysis.checked, lambda text: None)
        except NexoraRuntimeError as error:
            assert error.diagnostic.category in ("runtime", "contract")
            render(error.diagnostic, source)


# Regressions: defects found during the phase 3 audit

@pytest.mark.parametrize("digits", [20, 4300, 4301, 5000, 50_000])
def test_regression_very_long_integer_literal(digits):
    # Python refuses to convert digit strings longer than 4300 characters and raised ValueError
    # inside the lexer, which surfaced as an internal error.
    assert check_codes(in_main("print(" + "9" * digits + ")")) == ["E1004"]


def test_regression_long_literals_that_are_valid_still_work():
    assert run_text(in_main("print(9223372036854775807)")) == "9223372036854775807\n"
    assert run_text(in_main("print(0." + "1" * 5000 + ")")) == "0.1111111111111111\n"
    assert check_codes(in_main("print(" + "9" * 5000 + ".5)")) == ["E1004"]


def test_regression_a_binary_file_does_not_produce_one_error_per_byte():
    _, errors = lex("\x00\x01\x02\x03" * 5000)
    assert len(errors) == MAX_DIAGNOSTICS
    assert set(codes(errors)) == {"E1001"}


def test_regression_error_count_is_capped_in_every_stage():
    lexical = in_main("\n".join("let x = @" for _ in range(500)))
    syntax = in_main("\n".join("let = 1" for _ in range(500)))
    semantic = in_main("\n".join("print(missing)" for _ in range(500)))
    duplicates = "\n".join("fn same() -> Void {}" for _ in range(500)) + "\nfn main() -> Void {}\n"
    for text in (lexical, syntax, semantic, duplicates):
        assert len(check_codes(text)) == MAX_DIAGNOSTICS


def test_regression_the_cli_says_when_it_stopped_at_the_limit(tmp_path, capsys):
    path = tmp_path / "many.nex"
    path.write_text(in_main("\n".join("print(missing)" for _ in range(500))), encoding="utf-8")
    assert cli.main(["check", str(path)]) == 1
    error = capsys.readouterr().err
    assert f"{MAX_DIAGNOSTICS} errors (stopped at the limit of {MAX_DIAGNOSTICS}; there may be more)" in error
    assert error.count("error[E2005]") == MAX_DIAGNOSTICS


def test_regression_fewer_errors_than_the_limit_are_all_reported():
    assert len(check_codes(in_main("\n".join("print(missing)" for _ in range(MAX_DIAGNOSTICS - 1))))) == MAX_DIAGNOSTICS - 1


def test_regression_stack_exhaustion_is_not_described_as_a_thousand_calls():
    # Recursion through a deeply nested expression runs out of Python stack well before the limit
    # of nested calls. The message used to claim that "more than 1000 calls" had been nested.
    nested = "(" * 50 + "deep(n - 1)" + ")" * 50
    function = f"fn deep(n: Int) -> Int {{\n    if n == 0 {{\n        return 0\n    }}\n    return {nested} + 1\n}}"
    _, error = run_failure(with_main(function, f"print(deep({MAX_CALL_DEPTH - 100}))"))
    assert error.code == "E3004"
    assert "ran out of stack space after" in error.label
    assert str(MAX_CALL_DEPTH) not in error.label
    # The same function works when the recursion is shallow.
    assert run_text(with_main(function, "print(deep(20))")) == "20\n"


def test_regression_contract_field_does_not_overwrite_the_node_kind():
    # In the JSON form, the clause name of a contract used to replace the node's own "kind".
    analysis = analyze(Source("t.nex", "fn main() -> Void {\n    requires true\n}\n"))
    contract = ast.to_dict(analysis.program, analysis.types)["functions"][0]["contracts"][0]
    assert (contract["kind"], contract["clause"]) == ("Contract", "requires")


# Size and depth

def test_large_program():
    lines = 20_000
    assert run_text(in_main("\n".join(f"print({index})" for index in range(lines)))).count("\n") == lines


def test_many_functions_and_many_variables():
    functions = "\n".join(f"fn f{index}(a: Int) -> Int {{\n    return a + {index}\n}}" for index in range(2000))
    assert run_text(with_main(functions, "print(f1999(1))")) == "2000\n"
    body = "\n".join(f"let v{index} = {index}" for index in range(5000)) + "\nprint(v4999)"
    assert run_text(in_main(body)) == "4999\n"


def test_very_long_line_and_very_long_text():
    assert run_text(in_main('print("' + "a" * 500_000 + '")')) == "a" * 500_000 + "\n"
    assert check_codes('fn main() -> Void {\n    print("' + "a" * 500_000) == ["E1002"]


@pytest.mark.parametrize("text", [
    "(" * 100_000,
    "(" * 50_000 + "1" + ")" * 50_000,
    "-" * 100_000 + "1",
    "not " * 50_000 + "true",
], ids=["open-parentheses", "balanced-parentheses", "unary-minus", "not"])
def test_absurdly_deep_expressions_are_rejected_not_crashed(text):
    assert "E1105" in check_codes(in_main(f"let x = {text}"))


def test_absurdly_deep_blocks_are_rejected_not_crashed():
    assert "E1105" in check_codes(in_main("{" * 100_000 + "}" * 100_000))
    assert "E1105" in check_codes(in_main("{" * 100_000))
    chain = "if false {\n}" + " else if false {\n}" * 500
    assert "E1105" in check_codes(in_main(chain))


def test_very_wide_expressions_are_rejected_not_crashed():
    assert check_codes(in_main("print(" + " + ".join(["1"] * 50_000) + ")")) == ["E1105"]
    assert check_codes(in_main("print(" + " and ".join(["true"] * 50_000) + ")")) == ["E1105"]


def test_call_with_thousands_of_arguments():
    function = "fn one(a: Int) -> Int {\n    return a\n}"
    assert check_codes(with_main(function, "print(one(" + ", ".join(["1"] * 5000) + "))")) == ["E2009"]


def test_unbounded_and_mutual_recursion_end_with_a_diagnostic():
    mutual = "fn a(n: Int) -> Int {\n    return b(n)\n}\nfn b(n: Int) -> Int {\n    return a(n)\n}"
    assert run_failure(with_main(mutual, "print(a(1))"))[1].code == "E3004"
    in_contract = "fn f(n: Int) -> Int {\n    requires f(n) > 0\n    return n\n}"
    assert run_failure(with_main(in_contract, "print(f(1))"))[1].code == "E3004"


# Malformed input

@pytest.mark.parametrize("text", [
    "", " ", "\n", "\t\r\n", "\x00", "﻿", "}", "{", "(", ")", '"', "\\", "fn", "fn main", "fn main(",
    "fn main()", "fn main() ->", "fn main() -> Void", "fn main() -> Void {", "//", "// only a comment",
    "fn fn fn", "let let let", "= = =", "-> -> ->", "requires", "ensures result", "else", "return",
    'fn main() -> Void { print("', "fn main() -> Void {\n    let x = 1 +\n", "fn main() -> Void { if }",
    "fn main() -> Void { if true { } else }", "fn main() -> Void { return return }",
    "fn f(a: Int, a: Int, a: Int) -> Int { return a }", "fn main(a: Void) -> Void {}",
    "fn result() -> Int {\n    ensures result == result\n    return 1\n}\nfn main() -> Void {}",
    "\U0001F600", "fn main() -> Void { print(\"\U0001F600\") }", "fn main() -> Void {\r    print(1)\r}\r",
], ids=lambda text: f"{len(text)}-chars")
def test_odd_inputs_never_crash(text):
    survives(text)


@pytest.mark.parametrize("path", VALID_EXAMPLES, ids=lambda path: path.name)
def test_every_truncation_of_a_valid_program_is_handled(path):
    # Cut each example at every character: unfinished code must always produce diagnostics.
    text = path.read_text(encoding="utf-8")
    for end in range(len(text)):
        survives(text[:end])


@pytest.mark.parametrize("path", VALID_EXAMPLES, ids=lambda path: path.name)
def test_every_single_deletion_in_a_valid_program_is_handled(path):
    tokens = re.findall(r"\s+|\w+|[^\w\s]", path.read_text(encoding="utf-8"))
    for index in range(len(tokens)):
        survives("".join(tokens[:index] + tokens[index + 1:]))


PIECES = [
    "fn", "main", "f", "g", "(", ")", "->", "Void", "Int", "Float", "Bool", "Text", "{", "}", "let", "x", "y", "n",
    "print", "to_text", "to_int", "to_float", "=", "+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and",
    "or", "not", "return", "if", "else", "requires", "ensures", "result", "1", "0", "2.5", "0.0", '"s"', "true",
    "false", "\n", "\n", "\n", " ", ",", ":", "//c", "var", "while", '"open', "@", ";", "!", "9223372036854775807",
]


def test_random_token_sequences_never_crash():
    generator = random.Random(20261014)
    for _ in range(3000):
        length = generator.randint(0, 50)
        survives("".join(generator.choice(PIECES) + generator.choice(["", " "]) for _ in range(length)))


def test_random_mutations_of_valid_programs_never_crash():
    generator = random.Random(1014)
    sources = [re.findall(r"\s+|\w+|[^\w\s]+", path.read_text(encoding="utf-8")) for path in VALID_EXAMPLES]
    for _ in range(1500):
        tokens = list(generator.choice(sources))
        for _ in range(generator.randint(1, 3)):
            position = generator.randrange(len(tokens))
            action = generator.random()
            if action < 0.35:
                del tokens[position]
            elif action < 0.7:
                tokens.insert(position, generator.choice(PIECES))
            elif action < 0.9:
                tokens[position] = generator.choice(PIECES)
            else:
                other = generator.randrange(len(tokens))
                tokens[position], tokens[other] = tokens[other], tokens[position]
        survives("".join(tokens))


def test_random_bytes_through_the_command_line(tmp_path, capsys):
    # The file goes through the real reading path: bytes that are not UTF-8 are a file error,
    # and anything that does decode is handled by the lexer.
    generator = random.Random(7)
    for index in range(40):
        path = tmp_path / f"noise{index}.nex"
        path.write_bytes(bytes(generator.randrange(256) for _ in range(generator.randint(0, 400))))
        for command in ("check", "inspect", "run"):
            assert cli.main([command, str(path)]) in (0, 1, 4), (index, command)
            captured = capsys.readouterr()
            assert "internal error" not in captured.err and "Traceback" not in captured.err

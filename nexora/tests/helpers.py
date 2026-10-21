"""Shared helpers for the test suite."""

from __future__ import annotations

from nexora import ast_nodes as ast
from nexora.diagnostics import Diagnostic, NexoraRuntimeError, Source
from nexora.interpreter import run
from nexora.lexer import tokenize
from nexora.parser import parse
from nexora.pipeline import analyze


def lex(text: str):
    return tokenize(Source("test.nex", text))


def parse_text(text: str) -> tuple[ast.Program, list[Diagnostic]]:
    tokens, errors = lex(text)
    assert errors == [], f"unexpected lexical errors: {errors}"
    return parse(tokens)


def in_main(body: str) -> str:
    """Wraps statements in a main function, one per line."""
    lines = "\n".join(f"    {line}" for line in body.strip().splitlines())
    return f"fn main() -> Void {{\n{lines}\n}}\n"


def with_main(functions: str, body: str) -> str:
    """Function declarations followed by a main function with the given statements."""
    return functions.strip() + "\n\n" + in_main(body)


def codes(diagnostics) -> list[str]:
    return [diagnostic.code for diagnostic in diagnostics]


def diagnostics_of(text: str) -> tuple[Diagnostic, ...]:
    return analyze(Source("test.nex", text)).diagnostics


def check_codes(text: str) -> list[str]:
    return codes(diagnostics_of(text))


def run_text(text: str) -> str:
    """Analyses and runs a program, returning what it printed. Fails if it is not valid."""
    analysis = analyze(Source("test.nex", text))
    assert analysis.ok, f"program is not valid: {[(d.code, d.label) for d in analysis.diagnostics]}"
    output: list[str] = []
    run(analysis.checked, output.append)
    return "".join(output)


def run_failure(text: str) -> tuple[str, Diagnostic]:
    """Runs a valid program that fails at run time. Returns its output so far and the error."""
    analysis = analyze(Source("test.nex", text))
    assert analysis.ok, f"program is not valid: {[(d.code, d.label) for d in analysis.diagnostics]}"
    output: list[str] = []
    try:
        run(analysis.checked, output.append)
    except NexoraRuntimeError as error:
        return "".join(output), error.diagnostic
    raise AssertionError("the program was expected to fail at run time")


def run_with_host(text: str, host) -> str:
    """Analyses and runs a program with a host, returning what it printed."""
    analysis = analyze(Source("test.nex", text))
    assert analysis.ok, f"program is not valid: {[(d.code, d.label) for d in analysis.diagnostics]}"
    output: list[str] = []
    run(analysis.checked, output.append, host=host)
    return "".join(output)


def run_failure_with_host(text: str, host) -> tuple[str, Diagnostic]:
    """Runs a valid program with a host that fails at run time."""
    analysis = analyze(Source("test.nex", text))
    assert analysis.ok, f"program is not valid: {[(d.code, d.label) for d in analysis.diagnostics]}"
    output: list[str] = []
    try:
        run(analysis.checked, output.append, host=host)
    except NexoraRuntimeError as error:
        return "".join(output), error.diagnostic
    raise AssertionError("the program was expected to fail at run time")

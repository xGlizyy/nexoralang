"""Connects the stages: source text -> tokens -> AST -> static checks.

    1. lexical analysis    lexer.py
    2. syntax analysis     parser.py
    3. static analysis     checker.py   (names, scopes, types)
    4. execution           interpreter.py, only through `nex run`

Every command of the CLI goes through `analyze`, so they all see the same program.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast
from .checker import CheckedProgram, check
from .diagnostics import Diagnostic, Source
from .lexer import tokenize
from .parser import parse
from .tokens import Token


@dataclass(frozen=True)
class Analysis:
    """Result of analysing a program without running it."""

    source: Source
    diagnostics: tuple[Diagnostic, ...]
    # The syntax tree, available whenever the text has no lexical errors. With syntax errors
    # it is partial (see `complete`).
    program: ast.Program | None = None
    # Types of the expressions the checker could type: id(node) -> type.
    types: dict[int, str] | None = None
    # Set only when there are no diagnostics: the one thing the interpreter accepts.
    checked: CheckedProgram | None = None
    # What the checker learned (symbols, references, calls), available whenever there is a
    # tree, with or without errors. For tools; never for running.
    facts: CheckedProgram | None = None
    # The tokens, available when the text has no lexical errors.
    tokens: tuple[Token, ...] | None = None
    # True when the tree covers the whole file. False when there is no tree, or when syntax
    # errors left out the statements and functions that have them.
    complete: bool = False

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def analyze(source: Source) -> Analysis:
    """Lexes, parses and checks a program. Nothing in it is executed.

    The errors of each stage are reported only if the previous one found none, so one
    mistake is not reported again in a different form by a later stage.
    """
    tokens, diagnostics = tokenize(source)
    if diagnostics:
        return Analysis(source, tuple(diagnostics))

    program, diagnostics = parse(tokens)
    if diagnostics:
        # The tree is partial. The checker still runs over it, for what it can tell about the
        # code that did parse, but its errors are dropped: on a tree with pieces missing they
        # would describe the gaps, not the program.
        facts, _ = check(program)
        return Analysis(source, tuple(diagnostics), program, facts.types, None, facts, tuple(tokens))

    checked, diagnostics = check(program)
    runnable = None if diagnostics else checked
    return Analysis(source, tuple(diagnostics), program, checked.types, runnable, checked, tuple(tokens), True)

"""Connects the stages: source text -> tokens -> AST -> static checks.

    1. lexical analysis    lexer.py
    2. syntax analysis     parser.py
    3. static analysis     checker.py   (names, scopes, types)
    4. execution           interpreter.py, only through `nex run`

Every command of the CLI goes through `analyze`, so they all see the same program. A
program that imports modules is checked as one: the modules are read and checked with it
(decision 0018), through the `read` the caller gives for the imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast
from .checker import CheckedProgram
from .diagnostics import Diagnostic, Source
from .modules import Project, Reader, load
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
    # The program with the modules it imports, each with its own text and errors
    # (decision 0018). A program without imports has one module: itself.
    project: Project | None = None

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def analyze(source: Source, *, require_main: bool = True, read: Reader | None = None) -> Analysis:
    """Lexes, parses and checks a program, and the modules it imports. Nothing is executed.

    `require_main=False` drops the one rule that only matters for running a program, that it has a
    'main' (E2001). Only `nex test` uses it: it evaluates examples and never runs 'main'.

    `read` is how the imports are read, given by whoever knows about the file system: the CLI
    gives it, and a caller that only has text (the playground, the MCP server) does not, so its
    programs cannot import anything: an import then reports E0001, because there is no file
    beside it to read.

    The errors of each stage are reported only if the previous one found none, so one
    mistake is not reported again in a different form by a later stage.
    """
    project = load(source, read=read, require_main=require_main)
    entry = project.entry
    facts = project.facts
    if entry.program is None:
        # A lexical error: there are no tokens, so there is nothing for the rest to see.
        return Analysis(entry.source, project.diagnostics, project=project)
    if not entry.complete:
        # The tree is partial. The checker still ran over it, for what it can tell about the
        # code that did parse, but its errors are dropped: on a tree with pieces missing they
        # would describe the gaps, not the program.
        return Analysis(entry.source, project.diagnostics, entry.program,
                        facts.types if facts else None, None, facts, entry.tokens, False, project)
    return Analysis(entry.source, project.diagnostics, entry.program, project.types,
                    project.checked, facts, entry.tokens, True, project)

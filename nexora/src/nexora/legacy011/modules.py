"""The modules a program imports: reading them, and the order they are checked in (decision 0018).

One file is one module. A module is read relative to the file that imports it, each file
is read once however many modules import it, and the modules are checked in the order
they depend on each other: a module is always checked after the ones it imports, so the
names it uses already exist when its body is checked.

Nothing here executes the program: a module is part of the program, and the interpreter
only accepts a program that has been checked (decision 0002).

Nothing here touches the file system either. The stages of the language never import
`os` or `pathlib` (tests/test_security.py), so the loader asks the caller to read an
import and only decides what to do with the answer: the CLI resolves the path and reads
the file, and whoever sends the program as text (the playground, the MCP server) has no
file to read, so its programs cannot import anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from . import ast_nodes as ast
from .checker import CheckedProgram, Checker
from .diagnostics import Diagnostic, Source
from .lexer import tokenize
from .parser import parse
from .tokens import Token

# What a caller that can read files gives back for one import: the file it resolved to
# (a key the loader can compare with others), the namespace that file binds, and its text.
Answer = tuple[str, str, Source]

# How the caller reads an import: given the import and the file that has it, as the program
# writes them, it answers with the text of the module or with the error of not finding it.
Reader = Callable[[ast.ImportDecl, str], Answer | Diagnostic]


@dataclass(frozen=True)
class Module:
    """One file of a project: its namespace, its text and what the first two stages said."""

    # The namespace the module is bound to: the file name without its extension.
    name: str
    # The file it came from, as a report shows it: the path of the program, or the path
    # the import writes.
    path: str
    source: Source
    # The syntax tree, available whenever the text has no lexical errors.
    program: ast.Program | None
    # The errors of this file: the ones of the lexer and of the parser, plus the ones the
    # checker reported while checking this module.
    diagnostics: tuple[Diagnostic, ...]
    tokens: tuple[Token, ...] | None
    # True when the tree covers the whole file.
    complete: bool = False

    @property
    def imports(self) -> tuple[ast.ImportDecl, ...]:
        return self.program.imports if self.program is not None else ()

    @property
    def ok(self) -> bool:
        return not self.diagnostics


@dataclass(frozen=True)
class Project:
    """A program and the modules it imports, checked as one analysis (decision 0018)."""

    entry: Module
    # Every file of the project in the order they are checked: the imports of a module
    # come before it, and the entry is the last one.
    modules: tuple[Module, ...]
    # Set only when no module has any error: the one thing the interpreter accepts.
    checked: CheckedProgram | None
    # What the checker learned (symbols, references, calls), with or without errors.
    facts: CheckedProgram | None
    # Types of the expressions the checker could type: id(node) -> type.
    types: dict[int, str] | None

    @property
    def ok(self) -> bool:
        return self.checked is not None

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for module in self.modules for diagnostic in module.diagnostics)

    def reports(self) -> tuple[tuple[Diagnostic, Source], ...]:
        """Every diagnostic with the file it belongs to, in the order they were found."""
        return tuple((diagnostic, module.source)
                     for module in self.modules for diagnostic in module.diagnostics)

    def module(self, name: str) -> Module | None:
        """The module bound to a namespace, when this project has one."""
        for candidate in self.modules:
            if candidate.name == name:
                return candidate
        return None


def load(source: Source, *, read: Reader | None = None, require_main: bool = True) -> Project:
    """Reads a program and every module it imports, and checks them all.

    `read` is how the imports are read, given by whoever knows about the file system.
    Without it the program is only text (the playground, the MCP server, an editor buffer)
    and it cannot import anything: an import then reports E0001, because there is no file
    beside it to read.

    The diagnostics come in the order they were found, each one beside the file it belongs
    to, so a report can render every error with the file that has it.
    """
    loader = _Loader(read, require_main)
    entry = loader.read(source, source.name)
    checked, facts = loader.check()
    return Project(entry, tuple(loader.modules), checked, facts, facts.types if facts else None)


class _Loader:
    """Follows the imports of a project and checks its files in dependency order.

    Every file is kept once, however many import it: it is parsed, checked and declared
    once, with the module it declares. The errors of the loading itself (a file that
    cannot be read, a cycle, two files with one name) are reported on the file that has
    the import (decision 0018).
    """

    def __init__(self, read: Reader | None, require_main: bool) -> None:
        self._read_import = read
        self._require_main = require_main
        self._checker = Checker()
        # The functions of every module, qualified with the module that declares them.
        self._declared: dict[str, ast.Function] = {}
        # The namespace each module binds, and the file that binds it.
        self._names: dict[str, str] = {}
        # The path each file is shown with in a report, which is not always its key: a caller
        # that reads files may key them by where they are on the machine.
        self._shown: dict[str, str] = {}
        # The files already read, so one file is read once however many import it.
        self._read: dict[str, Module] = {}
        # The files being read, so an import that meets one of them is a cycle.
        self._stack: list[str] = []
        # The errors of the loading itself, reported on the file that imports.
        self._pending: list[Diagnostic] = []
        # True when the imports could not be read as a whole (a cycle, two modules with one
        # name, a file that cannot be read): the program cannot be assembled, so what the
        # analysis would say about its bodies would be noise on top of the error that
        # caused it. With no reader at all, nothing can be imported, and it is also broken.
        self._broken = False
        # The modules in the order they are checked: the imports of a module first.
        self.modules: list[Module] = []

    def read(self, source: Source, path: str) -> Module:
        """Reads one file and, before it, the modules it imports."""
        if path in self._read:
            return self._read[path]
        module = self._parse(source, path)
        if module.program is not None:
            self._stack.append(path)
            self._imports(module, path)
            self._stack.pop()
        if self._pending:
            module = replace(module, diagnostics=module.diagnostics + tuple(self._pending))
            self._pending = []
        self.modules.append(module)
        self._read[path] = module
        return module

    def check(self) -> tuple[CheckedProgram | None, CheckedProgram | None]:
        """Checks every module that parsed, in the order they were read.

        When the entry file has syntax errors the tree is partial, and what the checker
        says about it would describe the gaps instead of the program: its errors are
        dropped, and only what it learned is kept, for the tools (as it has always been
        for a program without modules). The same happens when the imports could not be
        read as a whole (a cycle, two modules with one name, a file that cannot be read):
        the program cannot be assembled, so what the analysis would say about its bodies
        would be noise on top of the error that caused it.
        """
        checker = Checker(modules=tuple(self._names))
        entry = self.modules[-1] if self.modules else None
        broken = (entry is None or entry.program is None or not entry.complete or self._broken)
        facts: CheckedProgram | None = None
        reported = 0
        for index, module in enumerate(self.modules):
            if module.program is None:
                continue
            # Every module declares its names qualified with itself, so two modules can
            # declare the same name without the analysis confusing them (decision 0018, 5).
            checker.prefix = "" if module is entry else f"{module.name}."
            checker.require_main = self._require_main and index == len(self.modules) - 1
            facts, diagnostics = checker.check(module.program, self._declared)
            if diagnostics[reported:] and not broken:
                module = replace(module, diagnostics=module.diagnostics + tuple(diagnostics[reported:]))
                self.modules[index] = module
            reported = len(diagnostics)
        checked = facts if facts is not None and not broken and not reported else None
        return checked, facts

    # Reading one file

    def _parse(self, source: Source, path: str) -> Module:
        name = _namespace_of(source.name, path)
        tokens, lexed = tokenize(source)
        if lexed:
            return Module(name, path, source, None, tuple(lexed), None)
        program, parsed = parse(tokens)
        return Module(name, path, source, program, tuple(parsed), tuple(tokens), not parsed)

    def _imports(self, module: Module, path: str) -> None:
        """Reads the modules the file imports, before the file itself is checked."""
        for declaration in module.imports:
            if self._read_import is None:
                self._broken = True
                self._pending.append(Diagnostic(
                    "E0001",
                    "This program imports modules, and they cannot be read here",
                    declaration.path_span,
                    hint="An import names a file relative to the file that has it: run the "
                         "program as 'nex run programa.nex', with the files beside it.",
                ))
                continue
            answer = self._read_import(declaration, path)
            if isinstance(answer, Diagnostic):
                # The program is missing a part of itself: nothing else can be said about
                # it until the file is found.
                self._broken = True
                self._pending.append(answer)
                continue
            key, name, source = answer
            if key in self._stack:
                self._circular(declaration, key)
                continue
            known = self._names.get(name)
            if known is not None and known != key:
                self._clash(declaration, name, known, source.name)
                continue
            self._names[name] = key
            self._shown[key] = source.name
            self.read(source, key)

    # Errors of the loading itself, reported on the file that imports.

    def _circular(self, declaration: ast.ImportDecl, key: str) -> None:
        self._broken = True
        chain = [*self._stack, key]
        self._pending.append(Diagnostic(
            "E2029",
            "The modules import each other: " + " -> ".join(_leaf(item) for item in chain),
            declaration.path_span,
            hint="A module cannot be its own ancestor. Move what the two share into a third "
                 "module that both of them import.",
        ))

    def _clash(self, declaration: ast.ImportDecl, name: str, known: str, shown: str) -> None:
        self._broken = True
        self._pending.append(Diagnostic(
            "E2030",
            f"Two modules are both called '{name}'",
            declaration.path_span,
            hint=f"A module takes its name from its file, and two files cannot share one. "
                 f"Rename one of them: {self._shown.get(known, known)} or {shown}.",
        ))


def _namespace_of(source_name: str, path: str) -> str:
    """The namespace a module binds: the name of its file, without its extension."""
    # The path the caller resolved is the real one; the source name is what was asked for.
    return path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0] or source_name


def _leaf(path: str) -> str:
    """The name of a file, without the directories in front of it."""
    return path.replace("\\", "/").rsplit("/", 1)[-1]

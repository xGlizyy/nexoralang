"""The host of a program that runs on the machine of whoever started it.

This is the only module of the language that touches the file system: the interpreter asks
the host, and the host decides with the three rules of decision 0015 — what the program
declared, what the user allowed, and what the environment permits. The interpreter never
imports this module, so the stages of the language stay away from the operating system
(tests/test_security.py).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from .capabilities import READ, WRITE, Capabilities, Grants, NotAllowed, is_inside


def read_standard_input() -> str:
    """One line of the standard input, without its terminator.

    Raises EOFError when the input has ended: the program has to know that there is
    nothing more to read (decision 0015, 7).
    """
    line = sys.stdin.readline()
    if line == "":
        raise EOFError("the standard input ended")
    return line.removesuffix("\n").removesuffix("\r")


# The defaults of the host: nothing allowed, nothing declared.
NO_GRANTS = Grants()
NO_CAPABILITIES = Capabilities()


class LocalHost:
    """What a program may do besides computing: its arguments, its input and its files.

    `arguments` are the ones the program was run with. `read_line` reads the standard
    input. `grants` are the paths the user allowed, `declarations` the ones the program
    declared, and `files_allowed` whether this environment admits files at all.
    """

    def __init__(self, *, arguments: tuple[str, ...] = (),
                 read_line: Callable[[], str] | None = None,
                 grants: Grants = NO_GRANTS, declarations: Capabilities = NO_CAPABILITIES,
                 files_allowed: bool = True) -> None:
        self._arguments = arguments
        self._read_line = read_line if read_line is not None else read_standard_input
        self._grants = grants
        self._declarations = declarations
        self._files_allowed = files_allowed

    def arguments(self) -> tuple[str, ...]:
        """The arguments the program was run with."""
        return self._arguments

    def read_line(self) -> str:
        """One line of the standard input, without its terminator."""
        return self._read_line()

    def read_file(self, path: str) -> str:
        """The contents of a file the program is allowed to read."""
        return Path(self._allowed(path, READ)).read_text(encoding="utf-8")

    def write_file(self, path: str, text: str) -> None:
        """Writes a file the program is allowed to write."""
        Path(self._allowed(path, WRITE)).write_text(text, encoding="utf-8")

    def _allowed(self, path: str, capability: str) -> str:
        """The path the program may use, after checking the three rules.

        The paths are compared once resolved, so that a `..` that leaves the scope and a
        symbolic link that points outside it do not slip through (decision 0015, 4).
        """
        if not self._files_allowed:
            raise NotAllowed(f"this environment does not allow files, so '{path}' cannot be used")
        target = _resolve(path)
        if not any(is_inside(_resolve(scope), target) for scope in self._declarations.of(capability)):
            raise NotAllowed(f"this program does not declare that it needs to {capability} '{path}'")
        if not any(is_inside(_resolve(grant), target) for grant in self._grants.of(capability)):
            raise NotAllowed(f"'{path}' is not among the paths the user allowed to {capability}")
        return target


def _resolve(path: str) -> str:
    """The path as the file system sees it: absolute, with the symbolic links followed.

    A path that does not exist yet is resolved over the part that does, so that a file
    that is going to be created is checked in the place it will live.
    """
    return os.path.realpath(path)

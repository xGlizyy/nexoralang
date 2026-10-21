"""La entrada estándar: `input()` lee una línea (decisión 0015, 7).

La entrada estándar está permitida por defecto: es la forma normal de dar datos a un
programa de consola, con el teclado o con una tubería.
"""

from __future__ import annotations

import pytest

from nexora.host import LocalHost
from helpers import run_failure_with_host, run_with_host

PROGRAM = """
fn main() -> Void {
    let first = input()
    let second = input()
    print(first)
    print(second)
}
"""


def host_with(*lines: str) -> LocalHost:
    """A host whose standard input is these lines, one after the other."""
    pending = list(lines)

    def read_line() -> str:
        if not pending:
            raise EOFError("the standard input ended")
        return pending.pop(0)

    return LocalHost(read_line=read_line)


def test_one_line():
    program = """
fn main() -> Void {
    print(input())
}
"""
    assert run_with_host(program, host_with("hola")) == "hola\n"


def test_several_lines_are_read_in_order():
    assert run_with_host(PROGRAM, host_with("uno", "dos")) == "uno\ndos\n"


def test_an_empty_line_is_an_empty_text():
    program = """
fn main() -> Void {
    let line = input()
    print(line == "")
}
"""
    assert run_with_host(program, host_with("")) == "true\n"


def test_a_line_keeps_its_spaces():
    program = """
fn main() -> Void {
    print(input())
}
"""
    assert run_with_host(program, host_with("  con espacios  ")) == "  con espacios  \n"


def test_a_line_may_have_unicode():
    program = """
fn main() -> Void {
    print(input())
}
"""
    assert run_with_host(program, host_with("ñandú 日本語 🎉")) == "ñandú 日本語 🎉\n"


def test_the_end_of_the_input_stops_the_program():
    output, error = run_failure_with_host(PROGRAM, host_with("uno"))
    assert output == ""
    assert error.code == "E3009"
    assert "no more input" in error.label.lower()


def test_the_end_of_the_input_is_reported_even_with_nothing_read():
    program = """
fn main() -> Void {
    print(input())
}
"""
    output, error = run_failure_with_host(program, host_with())
    assert error.code == "E3009"


def test_a_program_that_never_reads_does_not_need_the_input():
    program = """
fn main() -> Void {
    print("sin entrada")
}
"""
    assert run_with_host(program, host_with()) == "sin entrada\n"


def test_without_a_host_there_is_no_input():
    # A program that runs with no host at all: the input is empty (decision 0015, 6).
    program = """
fn main() -> Void {
    print(input())
}
"""
    output, error = run_failure_with_host(program, None)
    assert error.code == "E3009"


@pytest.mark.parametrize("line", ["", " ", "a", "ñ", "🎉"])
def test_every_line_is_read_whole(line):
    program = """
fn main() -> Void {
    print(input())
}
"""
    assert run_with_host(program, host_with(line)) == f"{line}\n"

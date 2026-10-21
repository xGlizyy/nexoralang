"""Los argumentos con los que se ejecuta un programa (decisión 0015, 8).

`args()` devuelve los argumentos que quien ejecuta el programa escribió tras `--`. No
necesitan ninguna declaración: no dan acceso a nada que el ejecutor no haya dado ya.
"""

from __future__ import annotations

import pytest

from nexora.capabilities import Grants
from nexora.host import LocalHost
from helpers import run_with_host

PROGRAM = """
fn main() -> Void {
    let names = args()
    print(names)
    print(names == [])
}
"""


def host_with(*arguments: str) -> LocalHost:
    """A host that gives the program these arguments and nothing else."""
    return LocalHost(arguments=arguments, grants=Grants())


def test_a_program_without_arguments_gets_an_empty_list():
    assert run_with_host(PROGRAM, host_with()) == "[]\ntrue\n"


def test_one_argument():
    assert run_with_host(PROGRAM, host_with("uno")) == "[uno]\nfalse\n"


def test_several_arguments_keep_their_order():
    assert run_with_host(PROGRAM, host_with("uno", "dos", "tres")) == "[uno, dos, tres]\nfalse\n"


def test_an_argument_may_have_spaces():
    assert run_with_host(PROGRAM, host_with("dos tres")) == "[dos tres]\nfalse\n"


def test_an_argument_may_be_empty():
    assert run_with_host(PROGRAM, host_with("")) == "[]\nfalse\n"


def test_an_argument_may_have_unicode():
    assert run_with_host(PROGRAM, host_with("ñandú", "日本語", "emoji 🎉")) == "[ñandú, 日本語, emoji 🎉]\nfalse\n"


def test_the_arguments_can_be_read_more_than_once():
    program = """
fn main() -> Void {
    print(args())
    print(args())
}
"""
    assert run_with_host(program, host_with("uno")) == "[uno]\n[uno]\n"


def test_the_arguments_can_be_walked():
    program = """
fn main() -> Void {
    var total = 0
    for name in args() {
        invariant total >= 0, "The total never goes down"
        total = total + Text.length(name)
    }
    print(total)
}
"""
    assert run_with_host(program, host_with("uno", "dos")) == "6\n"


@pytest.mark.parametrize("arguments", [
    ("",),
    ("con espacios",),
    ("ñ",),
])
def test_every_argument_is_a_text(arguments):
    program = """
fn main() -> Void {
    var total = 0
    for name in args() {
        invariant total >= 0, "The total never goes down"
        total = total + Text.length(name)
    }
    print(total)
}
"""
    expected = "".join(f"{len(name)}\n" for name in arguments)
    assert run_with_host(program, host_with(*arguments)) == expected

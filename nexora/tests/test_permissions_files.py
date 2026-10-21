"""Los archivos y los permisos (decisión 0015, 3 y 4).

La capacidad efectiva es la intersección de tres cosas: lo que declara el programa, lo
que concede quien lo ejecuta y lo que permite el entorno. Aquí se comprueba que ninguna
de las tres basta sola, y que las rutas se confinan sobre la ruta resuelta: un `..` o un
enlace simbólico que salen del ámbito concedido no sirven de nada.
"""

from __future__ import annotations

import os

import pytest

from nexora.capabilities import Capabilities, Grants
from nexora.host import LocalHost
from helpers import run_failure_with_host, run_with_host

READ_PROGRAM = """
uses read "datos/entradas.txt"

fn main() -> Void {
    print(read_file("datos/entradas.txt"))
}
"""

WRITE_PROGRAM = """
uses write "datos/salida.txt"

fn main() -> Void {
    write_file("datos/salida.txt", "escrito")
    print("hecho")
}
"""


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """A directory with the files of the tests, which is also the working directory."""
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "entradas.txt").write_text("contenido\n", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("secreto\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def host(*, read=(), write=(), declarations=None, files_allowed=True) -> LocalHost:
    """A host with these grants and these declarations."""
    return LocalHost(
        grants=Grants(read=read, write=write),
        declarations=declarations if declarations is not None else Capabilities(
            read=("datos/entradas.txt",), write=("datos/salida.txt",),
        ),
        files_allowed=files_allowed,
    )


# Declared, granted and allowed

def test_a_file_is_read_when_it_is_declared_and_granted(scope):
    assert run_with_host(READ_PROGRAM, host(read=("datos",))) == "contenido\n\n"


def test_a_file_is_written_when_it_is_declared_and_granted(scope):
    assert run_with_host(WRITE_PROGRAM, host(write=("datos",))) == "hecho\n"
    assert (scope / "datos" / "salida.txt").read_text(encoding="utf-8") == "escrito"


# The three rules, one by one

def test_declaring_is_not_granting(scope):
    output, error = run_failure_with_host(READ_PROGRAM, host())
    assert error.code == "E3008"
    assert "does not declare" in error.label or "not among the paths" in error.label


def test_granting_is_not_declaring(scope):
    program = """
fn main() -> Void {
    print(read_file("datos/entradas.txt"))
}
"""
    # The program has no declaration: the analysis stops it before it runs.
    from helpers import check_codes
    assert check_codes(program) == ["E2026"]


def test_the_environment_always_wins(scope):
    output, error = run_failure_with_host(READ_PROGRAM, host(read=("datos",), files_allowed=False))
    assert error.code == "E3008"
    assert "environment" in error.label


# Reading and writing are independent

def test_reading_is_not_writing(scope):
    output, error = run_failure_with_host(WRITE_PROGRAM, host(read=("datos",)))
    assert error.code == "E3008"


def test_writing_is_not_reading(scope):
    output, error = run_failure_with_host(READ_PROGRAM, host(write=("datos",)))
    assert error.code == "E3008"


def test_a_file_can_be_written_without_being_read(scope):
    program = """
uses write "datos/salida.txt"

fn main() -> Void {
    write_file("datos/salida.txt", "escrito")
    print("hecho")
}
"""
    assert run_with_host(program, host(write=("datos",))) == "hecho\n"


# The confinement of the paths

def test_a_path_outside_the_granted_scope_is_denied(scope):
    program = """
uses read "secreto.txt"

fn main() -> Void {
    print(read_file("secreto.txt"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("secreto.txt",))))
    assert error.code == "E3008"


def test_a_path_that_starts_the_same_is_not_inside(scope):
    # 'datos2' is not inside 'datos'.
    (scope / "datos2").mkdir()
    (scope / "datos2" / "entradas.txt").write_text("otro\n", encoding="utf-8")
    program = """
uses read "datos2/entradas.txt"

fn main() -> Void {
    print(read_file("datos2/entradas.txt"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos2/entradas.txt",))))
    assert error.code == "E3008"


def test_a_dot_dot_that_leaves_the_scope_is_denied(scope):
    program = """
uses read "datos/../secreto.txt"

fn main() -> Void {
    print(read_file("datos/../secreto.txt"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos/../secreto.txt",))))
    assert error.code == "E3008"


def test_a_dot_dot_inside_the_scope_is_allowed(scope):
    program = """
uses read "datos/entradas.txt"

fn main() -> Void {
    print(read_file("datos/./entradas.txt"))
}
"""
    assert run_with_host(program, host(read=("datos",))) == "contenido\n\n"


def test_an_absolute_path_is_allowed_when_the_scope_resolves_to_it(scope):
    # The scope is relative and the path absolute: they are compared once resolved, so
    # the file is inside the scope the user allowed.
    path = scope / "datos" / "entradas.txt"
    program = f"""
uses read "{path.as_posix()}"

fn main() -> Void {{
    print(read_file("{path.as_posix()}"))
}}
"""
    assert run_with_host(program, host(read=("datos",), declarations=Capabilities(read=(path.as_posix(),)))) == "contenido\n\n"


def test_an_absolute_path_outside_the_scope_is_denied(scope):
    outside = scope.parent / "fuera.txt"
    outside.write_text("fuera\n", encoding="utf-8")
    program = f"""
uses read "{outside.as_posix()}"

fn main() -> Void {{
    print(read_file("{outside.as_posix()}"))
}}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=(outside.as_posix(),))))
    assert error.code == "E3008"


def test_an_absolute_path_is_allowed_when_it_is_granted(scope):
    path = scope / "datos" / "entradas.txt"
    program = f"""
uses read "{path.as_posix()}"

fn main() -> Void {{
    print(read_file("{path.as_posix()}"))
}}
"""
    assert run_with_host(program, host(read=(str(path),), declarations=Capabilities(read=(path.as_posix(),)))) == "contenido\n\n"


def test_a_symbolic_link_that_leaves_the_scope_is_denied(scope):
    link = scope / "datos" / "enlace.txt"
    try:
        link.symlink_to(scope / "secreto.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this system does not allow symbolic links")
    program = """
uses read "datos/enlace.txt"

fn main() -> Void {
    print(read_file("datos/enlace.txt"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos/enlace.txt",))))
    assert error.code == "E3008"


def test_a_symbolic_link_inside_the_scope_is_allowed(scope):
    link = scope / "datos" / "copia.txt"
    try:
        link.symlink_to(scope / "datos" / "entradas.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this system does not allow symbolic links")
    program = """
uses read "datos/copia.txt"

fn main() -> Void {
    print(read_file("datos/copia.txt"))
}
"""
    assert run_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos/copia.txt",)))) == "contenido\n\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows joins the directories; on the other systems the symbolic "
                                             "link test covers the same case")
def test_a_directory_junction_that_leaves_the_scope_is_denied(scope):
    # On Windows a symbolic link needs privileges, but a junction does not: the path is
    # resolved the same way and the escape has to be denied too.
    outside = scope.parent / "fuera-del-ambito"
    outside.mkdir(exist_ok=True)
    (outside / "secreto.txt").write_text("secreto\n", encoding="utf-8")
    try:
        (scope / "datos" / "enlace").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system does not allow junctions")
    program = """
uses read "datos/enlace/secreto.txt"

fn main() -> Void {
    print(read_file("datos/enlace/secreto.txt"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos/enlace/secreto.txt",))))
    assert error.code == "E3008"


# The errors of the file system

def test_a_file_that_does_not_exist_is_a_file_error(scope):
    program = """
uses read "datos/ausente.txt"

fn main() -> Void {
    print(read_file("datos/ausente.txt"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos/ausente.txt",))))
    assert error.code == "E3010"


def test_a_file_that_is_not_text_is_a_file_error(scope):
    (scope / "datos" / "binario.bin").write_bytes(b"\xff\xfe\x00")
    program = """
uses read "datos/binario.bin"

fn main() -> Void {
    print(read_file("datos/binario.bin"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos/binario.bin",))))
    assert error.code == "E3010"


def test_a_directory_cannot_be_read_as_a_file(scope):
    program = """
uses read "datos"

fn main() -> Void {
    print(read_file("datos"))
}
"""
    output, error = run_failure_with_host(program, host(read=("datos",), declarations=Capabilities(read=("datos",))))
    assert error.code == "E3010"


# The environment

def test_without_a_host_no_file_is_ever_read(scope):
    output, error = run_failure_with_host(READ_PROGRAM, None)
    assert error.code == "E3008"


def test_an_environment_without_files_denies_everything(scope):
    output, error = run_failure_with_host(READ_PROGRAM, host(read=("datos",), files_allowed=False))
    assert error.code == "E3008"

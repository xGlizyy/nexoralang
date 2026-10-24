"""Lo que el análisis estático detecta de los permisos (decisión 0015, 5).

El análisis puede avisar de una declaración que falta. Es una ayuda, no la seguridad: el
intérprete comprueba los permisos en cada acceso, y un programa sin declaración que
`nex check` no ve (porque la ruta se calcula) se detiene al ejecutarse.
"""

from __future__ import annotations

from helpers import check_codes, diagnostics_of

READ = 'print(read_file("datos/entradas.txt"))'
WRITE = 'write_file("datos/salida.txt", "texto")'


def test_reading_without_a_declaration_is_an_error():
    (error,) = diagnostics_of(f"fn main() {{\n    {READ}\n}}\n")
    assert error.code == "E2026"
    assert "does not declare" in error.label


def test_writing_without_a_declaration_is_an_error():
    (error,) = diagnostics_of(f"fn main() {{\n    {WRITE}\n}}\n")
    assert error.code == "E2026"


def test_a_declaration_that_covers_the_path_is_enough():
    text = 'uses read "datos/entradas.txt"\n\nfn main() {\n    ' + READ + "\n}\n"
    assert check_codes(text) == []


def test_a_declaration_of_a_directory_covers_the_files_inside_it():
    text = 'uses read "datos"\n\nfn main() {\n    ' + READ + "\n}\n"
    assert check_codes(text) == []


def test_a_declaration_of_another_path_is_not_enough():
    text = 'uses read "datos/otro.txt"\n\nfn main() {\n    ' + READ + "\n}\n"
    assert check_codes(text) == ["E2026"]


def test_reading_and_writing_need_their_own_declaration():
    text = 'uses read "datos/entradas.txt"\n\nfn main() {\n    ' + WRITE + "\n}\n"
    assert check_codes(text) == ["E2026"]


def test_a_declaration_of_read_does_not_cover_a_write():
    text = 'uses read "datos/salida.txt"\n\nfn main() {\n    ' + WRITE + "\n}\n"
    assert check_codes(text) == ["E2026"]


def test_a_path_that_is_computed_is_left_to_the_interpreter():
    # The analysis cannot know what the path will be: only the interpreter can.
    text = """
fn main() {
    let name = "datos/entradas.txt"
    print(read_file(name))
}
"""
    assert check_codes(text) == []


def test_the_arguments_and_the_input_need_no_declaration():
    text = """
fn main() {
    print(args())
    print(input())
}
"""
    assert check_codes(text) == []


def test_the_error_points_at_the_path():
    (error,) = diagnostics_of(f"fn main() {{\n    {READ}\n}}\n")
    assert error.span.line == 2
    assert error.span.column == 21
    assert 'uses read "datos/entradas.txt"' in (error.hint or "")


def test_a_declaration_may_be_repeated():
    text = ('uses read "datos/entradas.txt"\n'
            'uses read "datos/entradas.txt"\n'
            '\n'
            'fn main() {\n'
            '    ' + READ + "\n}\n")
    assert check_codes(text) == []


def test_a_declaration_of_another_capability_does_not_help():
    text = 'uses write "datos/entradas.txt"\n\nfn main() {\n    ' + READ + "\n}\n"
    assert check_codes(text) == ["E2026"]

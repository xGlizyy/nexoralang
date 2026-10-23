"""The grammar of modules: where an import goes, what `pub` accepts, how a name is qualified.

Each test looks at one part of the grammar of section 3 of the specification (decision
0018). Only the form is checked here: whether an imported file exists, whether a module
has a public name and whether a qualified name resolves is decided when the program is
analysed, and it is asserted in tests/test_modules.py.
"""

from helpers import diagnostics_of, parse_text, with_main

IMPORT = 'import "app/models.nex"\n'


# Where an import goes

def test_an_import_is_kept_with_its_path_and_its_position():
    program, errors = parse_text(IMPORT + "\nfn main() -> Void { print(1) }\n")
    assert errors == []
    (imported,) = program.imports
    assert imported.path == "app/models.nex"
    assert (imported.path_span.line, imported.path_span.column) == (1, 8)


def test_a_program_can_import_several_modules():
    program, errors = parse_text('import "a.nex"\nimport "b.nex"\n\nfn main() -> Void { print(1) }\n')
    assert errors == []
    assert [imported.path for imported in program.imports] == ["a.nex", "b.nex"]


def test_the_imports_come_before_a_function():
    (error,) = diagnostics_of('fn main() -> Void { print(1) }\n\nimport "a.nex"\n')
    assert (error.code, error.label) == ("E1101", "The imports of a program come before its other declarations")


def test_the_imports_come_before_the_capabilities():
    # `uses` is also a declaration of the file, and the imports come first (decision 0018, 1).
    (error,) = diagnostics_of('uses read "datos.txt"\nimport "a.nex"\n\nfn main() -> Void { print(1) }\n')
    assert (error.code, error.label) == ("E1101", "The imports of a program come before its other declarations")


def test_the_imports_come_before_the_other_imports_that_follow_a_declaration():
    program, errors = parse_text('import "a.nex"\nfn f() -> Int { return 1 }\nimport "b.nex"\n')
    # The first import was in its place and is kept; the parser then reports the one that
    # is not, and what follows it is not parsed.
    assert [error.code for error in errors] == ["E1101"]
    assert [imported.path for imported in program.imports] == ["a.nex"]


# What an import path has to be

def test_the_path_of_an_import_is_a_text():
    (error,) = diagnostics_of("import app/models.nex\nfn main() -> Void { print(1) }\n")
    assert error.code == "E1101"
    assert "the path of the module after 'import'" in error.label


def test_the_path_of_an_import_ends_in_nex():
    (error,) = diagnostics_of('import "app/models.txt"\nfn main() -> Void { print(1) }\n')
    assert error.code == "E1101"
    assert "has to end in '.nex'" in error.label


def test_the_suffix_of_an_import_is_the_last_part_of_the_path():
    (error,) = diagnostics_of('import "app/models.nex.bak"\nfn main() -> Void { print(1) }\n')
    assert error.code == "E1101"
    assert "has to end in '.nex'" in error.label


# What `pub` accepts

def test_a_function_is_public_with_pub():
    program, errors = parse_text("pub fn f() -> Int { return 1 }\nfn main() -> Void { print(f()) }\n")
    assert errors == []
    assert [function.public for function in program.functions] == [True, False]


def test_a_refined_type_is_public_with_pub():
    program, errors = parse_text("pub type Percent = Int where value >= 0\nfn main() -> Void { print(1) }\n")
    assert errors == []
    assert program.types[0].public is True


def test_a_record_is_public_with_pub():
    program, errors = parse_text("pub type Point = { x: Int }\nfn main() -> Void { print(1) }\n")
    assert errors == []
    assert program.records[0].public is True


def test_pub_only_marks_a_function_or_a_type():
    (error,) = diagnostics_of("pub let n = 1\nfn main() -> Void { print(1) }\n")
    assert (error.code, error.label) == ("E1101", "Expected 'fn' or 'type' after 'pub', found 'let'")


def test_pub_goes_before_the_declaration_not_inside_it():
    (error,) = diagnostics_of("fn pub() -> Int { return 1 }\nfn main() -> Void { print(1) }\n")
    assert error.code == "E1101"
    assert "Expected a function name after 'fn', found 'pub'" in error.label


def test_pub_cannot_be_used_inside_a_function():
    (error,) = diagnostics_of("fn main() -> Void { pub let n = 1 }\n")
    assert error.code == "E1101"
    assert "found 'pub'" in error.label


def test_import_cannot_be_used_as_a_name():
    # Both are keywords now, so they are not available for a name (decision 0018, 6).
    (error,) = diagnostics_of("fn main() -> Void { let import = 1 }\n")
    assert error.code == "E1101"
    assert "found 'import'" in error.label


# How a qualified name is written

def test_a_type_of_another_module_keeps_its_module():
    program, errors = parse_text(with_main("", "let p: models.Point = point()"))
    assert errors == []
    annotation = program.functions[0].body.statements[0].declared_type
    assert (annotation.qualifier, annotation.name) == ("models", "Point")


def test_a_construction_of_another_module_keeps_its_module():
    program, errors = parse_text(with_main("", "let p = models.Point(x: 1)"))
    assert errors == []
    construction = program.functions[0].body.statements[0].value
    assert (construction.qualifier, construction.name) == ("models", "Point")


def test_a_call_of_another_module_keeps_its_module():
    program, errors = parse_text(with_main("", "let n = models.area(p)"))
    assert errors == []
    call = program.functions[0].body.statements[0].value
    assert (call.qualifier, call.callee) == ("models", "models.area")


def test_the_dot_of_a_type_goes_stuck_to_the_names():
    (error,) = diagnostics_of(with_main("", "let p: models . Point = point()"))
    assert error.code == "E1101"
    assert "without spaces around the '.'" in error.label

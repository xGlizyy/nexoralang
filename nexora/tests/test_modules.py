"""Programs of several files: how they are read, how their names are resolved, and what each
tool says about them (decision 0018).

The loading and the names are tested with texts in memory, so a reader gives every file
without touching the disk; what a person sees is tested with the real command, writing
real files, because that is where the paths are resolved.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import parse_text
from nexora import api, cli
from nexora.diagnostics import Diagnostic, Source
from nexora.pipeline import analyze

ROOT = Path(__file__).resolve().parents[1]

MODELS = """\
pub type Point = { x: Int, y: Int }

pub fn area(p: Point) gives Int {
    return p.x * p.y
}

fn scale(p: Point, factor: Int) gives Point {
    return Point(x: p.x * factor, y: p.y * factor)
}

pub fn double(p: Point) gives Point {
    return scale(p, 2)
}
"""

ENTRY = """\
import "app/models.nex"

fn main() {
    let p: models.Point = models.Point(x: 3, y: 4)
    print(models.area(p))
    print(models.double(p))
}
"""

ENTRY_OUTPUT = "12\nmodels.Point(x: 6, y: 8)\n"


@pytest.fixture
def files(tmp_path):
    """Writes the files of a program and returns `write(text, name) -> path`."""
    def write(text: str, name: str) -> str:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)
    return write


def nex(*arguments: str) -> subprocess.CompletedProcess:
    """Runs the real command in a separate process, as a user would."""
    return subprocess.run(
        [sys.executable, "-m", "nexora", *arguments],
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
    )


def reader(files: dict[str, str], reads: list[str] | None = None):
    """A `Reader` over texts in memory: what the CLI does with the file system (decision 0018).

    The keys are the paths as they are written in the import, so the loading of a program
    can be followed without resolving anything against a directory.
    """
    def read(declaration, importing_file: str):
        if reads is not None:
            reads.append(declaration.path)
        text = files.get(declaration.path)
        if text is None:
            return Diagnostic(
                "E0001", f"No such file or directory: {declaration.path}", declaration.path_span,
                hint='An import names a file relative to the file that has it: '
                     'import "app/models.nex".',
            )
        name = Path(declaration.path).stem
        return declaration.path, name, Source(declaration.path, text)
    return read


def load(texts: dict[str, str], entry: str, reads: list[str] | None = None):
    """Analyses `texts[entry]` with the files it imports, and returns the analysis."""
    return analyze(Source(entry, texts[entry]), read=reader(texts, reads))


def codes_of(analysis) -> list[str]:
    return [diagnostic.code for diagnostic in analysis.diagnostics]


# The program as a whole

def test_a_program_runs_with_the_modules_it_imports(files, capsys):
    path = files(ENTRY, "main.nex")
    files(MODELS, "app/models.nex")

    assert cli.main(["run", path]) == 0
    assert capsys.readouterr().out == ENTRY_OUTPUT


def test_public_module_enum_constructor_and_match_are_qualified():
    texts = {
        "main.nex": (
            'import "models.nex"\n'
            'fn main() {\n'
            '    let state: models.State = models.State.Ready()\n'
            '    print(match state { models.State.Ready => 1 models.State.Busy => 0 })\n'
            '}\n'
        ),
        "models.nex": (
            'pub type State = enum { Ready, Busy }\n'
            'pub fn next(state: State) gives State {\n'
            '    return match state { Ready => State.Busy() Busy => State.Ready() }\n'
            '}\n'
        ),
    }
    analysis = load(texts, "main.nex")
    assert analysis.ok, [(diagnostic.code, diagnostic.label) for diagnostic in analysis.diagnostics]
    output = []
    from nexora.interpreter import run
    run(analysis.checked, output.append)
    assert "".join(output) == "1\n"


def test_the_names_of_a_module_are_visible_without_pub_in_the_file_that_runs(files, capsys):
    # Nothing of the entry file is marked with `pub`: the file that runs is its own module,
    # and what it declares is its own (decision 0018, 3).
    path = files(
        'import "app/models.nex"\n'
        '\n'
        'fn main() {\n'
        '    print(plain())\n'
        '}\n'
        '\n'
        'fn plain() gives Int {\n'
        '    return models.area(models.Point(x: 1, y: 5)) + 1\n'
        '}\n',
        "main.nex",
    )
    files(MODELS, "app/models.nex")

    assert cli.main(["run", path]) == 0
    assert capsys.readouterr().out == "6\n"


def test_every_file_is_kept_once_however_many_import_it():
    texts = {
        "main.nex": 'import "a.nex"\nimport "b.nex"\n\nfn main() { print(1) }\n',
        # Inside a module, the functions of another module are written with it in front.
        "a.nex": 'import "shared.nex"\npub fn a() gives Int { return shared.shared() }\n',
        "b.nex": 'import "shared.nex"\npub fn b() gives Int { return shared.shared() }\n',
        "shared.nex": "pub fn shared() gives Int { return 7 }\n",
    }
    reads: list[str] = []

    analysis = load(texts, "main.nex", reads)

    assert analysis.ok, analysis.diagnostics
    # Every import is followed, in depth-first order; the loader asks the reader for
    # `shared.nex` from each of the two files that import it.
    assert reads == ["a.nex", "shared.nex", "b.nex", "shared.nex"]
    # And every file is kept once: it is parsed, checked and declared once, in dependency
    # order, so what a module uses already exists when its body is checked.
    assert [module.name for module in analysis.project.modules] == ["shared", "a", "b", "main"]


def test_an_import_names_a_file_relative_to_the_file_that_has_it(tmp_path, capsys):
    # The command is run from another directory: what matters is where the file is.
    program = tmp_path / "app" / "main.nex"
    program.parent.mkdir(parents=True)
    program.write_text('import "models.nex"\n\nfn main() { print(models.n()) }\n',
                       encoding="utf-8")
    (program.parent / "models.nex").write_text("pub fn n() gives Int { return 3 }\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "nexora", "run", str(program)],
        capture_output=True, encoding="utf-8", cwd=ROOT,
    )

    assert (result.returncode, result.stdout) == (0, "3\n")


def test_the_command_reads_a_file_once_however_many_import_it(files):
    # The answer is remembered with the path it was resolved to, so a file several files
    # import is read from disk once (decision 0018, 1).
    first = files('import "shared.nex"\n', "main.nex")
    second = files('import "shared.nex"\n', "other.nex")
    elsewhere = files('import "shared.nex"\n', "app/second.nex")
    files("pub fn shared() gives Int { return 7 }\n", "shared.nex")
    files("pub fn shared() gives Int { return 8 }\n", "app/shared.nex")
    program, _ = parse_text('import "shared.nex"\n')
    read = cli._module_reader(Source(first, ""))

    # The two files that name it from the same directory reach the same file, and it is
    # read once; a file with the same name in another directory is another module, and is
    # read there.
    assert read(program.imports[0], first) is read(program.imports[0], second)
    nested = read(program.imports[0], elsewhere)
    assert nested is not read(program.imports[0], first)
    # The text is kept as it is on disk: on Windows the file has '\r\n'.
    assert nested[2].text.replace("\r\n", "\n") == "pub fn shared() gives Int { return 8 }\n"


def test_a_module_that_imports_the_program_is_a_cycle_at_the_first_step(tmp_path):
    # The program is known by the path it was given, and an import that reaches it answers
    # with that same path: the cycle is found when the module imports the program, and the
    # program is never read a second time (decision 0018, 4).
    (tmp_path / "a.nex").write_text('import "b.nex"\n\nfn main() { print(b.n()) }\n',
                                    encoding="utf-8")
    (tmp_path / "b.nex").write_text('import "a.nex"\n\npub fn n() gives Int { return 3 }\n',
                                    encoding="utf-8")

    result = subprocess.run([sys.executable, "-m", "nexora", "check", "a.nex"],
                            capture_output=True, encoding="utf-8", cwd=tmp_path)

    assert result.returncode == 1
    assert result.stderr.count("error[E2029]") == 1
    assert "--> b.nex:1:8" in result.stderr
    assert "a.nex -> b.nex -> a.nex\n" in result.stderr


def test_a_module_is_shown_relative_to_the_program_and_never_with_the_machine_path(tmp_path):
    # The absolute path is only how the reader tells two files apart: what a report and a
    # document show is the path of the program joined with the path of the import, with '/'
    # on every system, so the same program says the same thing on any machine (decision 0018, 1).
    for name, text in {
        "app/main.nex": 'import "lib/m.nex"\nimport "nope.nex"\n\nfn main() { print(m.n()) }\n',
        "app/lib/m.nex": 'import "../../shared/k.nex"\n\npub fn n() gives Int { return k.z() }\n',
        "shared/k.nex": "pub fn z() gives Int { return bad }\n",
    }.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")

    result = subprocess.run([sys.executable, "-m", "nexora", "check", "app/main.nex"],
                            capture_output=True, encoding="utf-8", cwd=tmp_path)

    assert result.returncode == 1
    assert "No such file or directory: app/nope.nex" in result.stderr
    assert str(tmp_path) not in result.stderr

    (tmp_path / "app/main.nex").write_text('import "lib/m.nex"\n\nfn main() { print(m.n()) }\n',
                                           encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "nexora", "check", "app/main.nex"],
                            capture_output=True, encoding="utf-8", cwd=tmp_path)
    assert "--> shared/k.nex:1:31" in result.stderr
    assert str(tmp_path) not in result.stderr

    (tmp_path / "shared/k.nex").write_text("pub fn z() gives Int { return 1 }\n", encoding="utf-8")
    for command in ("context", "symbols"):
        result = subprocess.run([sys.executable, "-m", "nexora", command, "--format", "json", "app/main.nex"],
                                capture_output=True, encoding="utf-8", cwd=tmp_path)
        document = json.loads(result.stdout)
        entries = document["functions"] if command == "context" else document["symbols"]
        assert {entry["file"] for entry in entries} == {"app/main.nex", "app/lib/m.nex", "shared/k.nex"}, command


def test_two_modules_with_one_name_are_shown_with_their_paths(tmp_path):
    for name in ("x/m.nex", "y/m.nex"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("pub fn n() gives Int { return 1 }\n", encoding="utf-8")
    (tmp_path / "main.nex").write_text('import "x/m.nex"\nimport "y/m.nex"\n\nfn main() { print(1) }\n',
                                       encoding="utf-8")

    result = subprocess.run([sys.executable, "-m", "nexora", "check", "main.nex"],
                            capture_output=True, encoding="utf-8", cwd=tmp_path)

    assert "error[E2030]" in result.stderr
    assert "Rename one of them: x/m.nex or y/m.nex." in result.stderr


# Files that cannot be read, and imports that cannot be followed

def test_a_file_that_cannot_be_read_is_reported_on_the_import(files, capsys):
    path = files('import "app/missing.nex"\n\nfn main() { print(1) }\n', "main.nex")

    assert cli.main(["check", path]) == 1
    output = capsys.readouterr().err
    assert "error[E0001]" in output
    assert "main.nex:1:8" in output
    assert 'import "app/models.nex"' in output


def test_a_cycle_between_the_modules_is_reported_once():
    texts = {
        "main.nex": 'import "a.nex"\n\nfn main() { print(1) }\n',
        "a.nex": 'import "b.nex"\npub fn a() gives Int { return b() }\n',
        "b.nex": 'import "a.nex"\npub fn b() gives Int { return a() }\n',
    }

    analysis = load(texts, "main.nex")

    (diagnostic,) = analysis.diagnostics
    assert diagnostic.code == "E2029"
    assert diagnostic.label == ("The modules import each other: "
                                "main.nex -> a.nex -> b.nex -> a.nex")
    # Nothing else is said: the program cannot be assembled, so what the analysis would
    # say about the bodies of the modules would be noise on top of this error.
    assert analysis.checked is None


def test_two_files_with_one_name_cannot_both_be_a_module():
    texts = {
        "main.nex": 'import "app/models.nex"\n'
                    'import "other/models.nex"\n'
                    '\n'
                    'fn main() { print(1) }\n',
        "app/models.nex": "pub fn one() gives Int { return 1 }\n",
        "other/models.nex": "pub fn two() gives Int { return 2 }\n",
    }

    analysis = load(texts, "main.nex")

    (diagnostic,) = analysis.diagnostics
    assert diagnostic.code == "E2030"
    assert diagnostic.label == "Two modules are both called 'models'"
    # The hint has to name the two files: their names alone are the same.
    assert "app/models.nex" in diagnostic.hint and "other/models.nex" in diagnostic.hint


# What a module makes visible

def test_a_name_that_a_module_does_not_make_public_cannot_be_used(files, capsys):
    path = files(
        'import "app/models.nex"\n\nfn main() { print(models.scale(p, 1)) }\n',
        "main.nex",
    )
    files(MODELS, "app/models.nex")

    assert cli.main(["check", path]) == 1
    output = capsys.readouterr().err
    assert "error[E2028]" in output
    assert "'models.scale' is private" in output
    assert "pub fn scale" in output


def test_a_module_the_program_does_not_import_is_reported():
    analysis = analyze(Source("test.nex",
                              'import "app/models.nex"\n'
                              '\n'
                              'fn main() { print(other.area()) }\n'),
                       read=reader({"app/models.nex": MODELS}))

    (diagnostic,) = analysis.diagnostics
    assert (diagnostic.code, diagnostic.label) == ("E2027", "There is no module named 'other'")
    assert "The modules this program imports are: models." in diagnostic.hint


def test_a_program_with_no_imports_says_so_when_a_module_is_used():
    (diagnostic,) = analyze(Source("test.nex",
                                   "fn main() { print(models.area()) }\n")).diagnostics

    assert diagnostic.code == "E2027"
    assert "This program imports no modules." in diagnostic.hint


def test_a_function_a_module_does_not_have_lists_the_public_ones():
    analysis = analyze(Source("test.nex",
                              'import "app/models.nex"\n'
                              '\n'
                              'fn main() { print(models.perimeter()) }\n'),
                       read=reader({"app/models.nex": MODELS}))

    (diagnostic,) = analysis.diagnostics
    assert (diagnostic.code, diagnostic.label) == (
        "E2008", "The module 'models' has no function named 'perimeter'")
    assert "area, double" in diagnostic.notes[0]


def test_a_record_a_module_does_not_have_lists_the_public_ones():
    analysis = analyze(Source("test.nex",
                              'import "app/models.nex"\n'
                              '\n'
                              'fn main() { print(models.Segment(x: 1, y: 2)) }\n'),
                       read=reader({"app/models.nex": MODELS}))

    (diagnostic,) = analysis.diagnostics
    assert (diagnostic.code, diagnostic.label) == (
        "E2023", "The module 'models' has no record named 'Segment'")
    # The hint names the record that is there, and the note lists all of them.
    assert diagnostic.notes == ("The records 'models' makes public: Point.",)


def test_a_type_a_module_does_not_have_suggests_the_right_name():
    analysis = analyze(Source("test.nex",
                              'import "app/models.nex"\n'
                              '\n'
                              'fn main() { let p: models.Otro = 1 }\n'),
                       read=reader({"app/models.nex": MODELS}))

    (diagnostic,) = analysis.diagnostics
    assert (diagnostic.code, diagnostic.label) == ("E2012", "'models.Otro' is not a type")
    assert diagnostic.hint == "Did you mean 'models.Point'?"


def test_a_name_in_lower_case_before_the_dot_can_only_be_a_module():
    # A type starts with a capital letter, so this is not a type that does not exist.
    (diagnostic,) = analyze(Source(
        "test.nex", 'import "app/models.nex"\n\nfn main() { print(geometry.area()) }\n'
    ), read=reader({"app/models.nex": MODELS})).diagnostics

    assert (diagnostic.code, diagnostic.label) == ("E2027", "There is no module named 'geometry'")


def test_a_built_in_type_belongs_to_no_module(files, capsys):
    path = files(
        'import "app/box.nex"\n'
        '\n'
        'fn main() {\n'
        '    let b = box.of(1)\n'
        '    print(box.first(b))\n'
        '}\n',
        "main.nex",
    )
    files("pub type Box = { items: List[Int] }\n"
          "\n"
          "pub fn of(item: Int) gives Box { return Box(items: [item]) }\n"
          "\n"
          "pub fn first(b: Box) gives Int { return List.get(b.items, 0) }\n",
          "app/box.nex")

    assert cli.main(["run", path]) == 0
    assert capsys.readouterr().out == "1\n"


def test_a_built_in_type_cannot_be_written_with_its_module():
    (diagnostic,) = analyze(Source("test.nex",
                                  'import "app/models.nex"\n'
                                  '\n'
                                  'fn main() { let x: models.Int = 1 }\n'),
                            read=reader({"app/models.nex": MODELS})).diagnostics

    assert (diagnostic.code, diagnostic.label) == ("E2012", "'models.Int' is not a type")
    assert diagnostic.hint == ("'Int' is a built-in type: it belongs to no module. "
                               "Write it as 'Int'.")


def test_two_records_with_one_name_in_two_modules_are_different_types():
    texts = {
        "main.nex": 'import "a.nex"\n'
                    'import "b.nex"\n'
                    '\n'
                    'fn main() {\n'
                    '    let one: a.Point = a.Point(x: 1)\n'
                    '    let two: b.Point = b.Point(x: 1)\n'
                    '    print(one == two)\n'
                    '}\n',
        "a.nex": "pub type Point = { x: Int }\n",
        "b.nex": "pub type Point = { x: Int }\n",
    }

    analysis = load(texts, "main.nex")

    (diagnostic,) = analysis.diagnostics
    assert diagnostic.code == "E2011"
    assert "a.Point" in diagnostic.label and "b.Point" in diagnostic.label


# The file that is given to the command

def test_a_module_by_itself_is_a_program_that_needs_a_main(files, capsys):
    path = files(MODELS, "app/models.nex")

    assert cli.main(["check", path]) == 1
    assert "error[E2001]" in capsys.readouterr().err


def test_nex_test_evaluates_the_examples_of_the_file_it_is_given(files, capsys):
    # The example of the module would fail: it is not part of the program that is tested,
    # and the report cannot locate it in the text of the file that was given.
    files(MODELS + "\nfn internal() gives Int\n    example internal() == 0\n{\n    return 1\n}\n",
          "app/models.nex")
    path = files(
        'import "app/models.nex"\n'
        '\n'
        'fn main() { print(models.area(models.Point(x: 1, y: 2))) }\n'
        '\n'
        'fn twice(x: Int) gives Int\n'
        '    example twice(models.area(models.Point(x: 2, y: 3))) == 12\n'
        '{\n'
        '    return x * 2\n'
        '}\n',
        "main.nex",
    )

    assert cli.main(["test", path]) == 0
    output = capsys.readouterr().out
    assert "twice   1 passed" in output
    assert "internal" not in output


def test_the_examples_of_a_module_are_evaluated_when_it_is_the_file_given(files, capsys):
    path = files(MODELS + "\nfn internal() gives Int\n    example internal() == 2\n{\n    return 2\n}\n",
                 "app/models.nex")

    assert cli.main(["test", path]) == 0
    assert "internal   1 passed" in capsys.readouterr().out


# What each tool knows about a program of several files

def test_every_diagnostic_is_shown_with_the_file_that_has_it(files, capsys):
    # The error is in the module, not in the file that was given to the command.
    path = files('import "app/models.nex"\n\nfn main() { print(models.point()) }\n',
                 "main.nex")
    files("pub fn point() gives Int {\n    let wrong: Int = \"text\"\n    return 1\n}\n",
          "app/models.nex")

    assert cli.main(["check", path, "--format", "json"]) == 1
    document = json.loads(capsys.readouterr().out)

    assert document["file"] == path
    assert document["diagnostics"][0]["file"].endswith("models.nex")


def test_inspect_of_the_program_shows_the_import_and_the_qualified_names(files, capsys):
    path = files(ENTRY, "main.nex")
    files(MODELS, "app/models.nex")

    assert cli.main(["inspect", path]) == 0
    document = json.loads(capsys.readouterr().out)

    (imported,) = document["program"]["imports"]
    assert (imported["kind"], imported["path"]) == ("ImportDecl", "app/models.nex")
    main = document["program"]["functions"][0]
    assert main["public"] is False
    annotation = main["body"]["statements"][0]["declared_type"]
    assert (annotation["qualifier"], annotation["name"]) == ("models", "Point")


# The API and the commands

def test_the_api_reads_no_files():
    # The API receives the program as text and never touches the file system, so an import
    # cannot be followed there: there is no file beside the text (decision 0018, 1).
    report = api.check_source(ENTRY)

    assert report["status"] == "invalid"
    assert [diagnostic["code"] for diagnostic in report["diagnostics"]] == ["E0001"]


def test_an_analysis_without_a_reader_reports_the_import():
    analysis = analyze(Source("program.nex", ENTRY))

    assert codes_of(analysis) == ["E0001"]
    assert analysis.project.modules[0].name == "program"

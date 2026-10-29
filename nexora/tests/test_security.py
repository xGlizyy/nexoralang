"""What a NEXORA program is able to do, and what the implementation relies on.

These tests check concrete, limited properties. They do not show that NEXORA is safe to run on
untrusted code in general; SECURITY.md describes what is and is not covered.
"""

import ast as python_ast
from pathlib import Path

import pytest

from nexora import cli
from nexora.checker import BUILTINS
from nexora.diagnostics import Source
from nexora.pipeline import analyze

from helpers import check_codes, in_main

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "nexora"
MODULES = sorted(PACKAGE.glob("*.py"))

# Standard-library modules the language core is allowed to import, and nothing else.
ALLOWED_IMPORTS = {
    "__future__", "argparse", "contextlib", "dataclasses", "difflib", "enum", "errno", "io", "json", "math", "os", "pathlib", "posixpath",
    "re", "sys", "typing", "collections.abc", "time", "resource", "signal", "types", "subprocess",
    "threading", "shutil", "urllib.error", "urllib.parse", "urllib.request",
}
# The one module that may import something else: the optional MCP server needs the MCP SDK.
OPTIONAL_IMPORTS = {"mcp_server.py": {"mcp.server", "mcp.server.mcpserver.exceptions", "mcp.types"}}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "input", "globals", "locals", "setattr"}


def python_tree(path: Path) -> python_ast.Module:
    return python_ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# The implementation

@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_no_module_evaluates_python_code_or_opens_files_by_itself(path):
    # Found by parsing the source, so a mention in a comment or a string does not count.
    calls = {
        node.func.id
        for node in python_ast.walk(python_tree(path))
        if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Name)
    }
    assert calls & FORBIDDEN_CALLS == set()


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_modules_only_import_the_standard_library_modules_on_the_list(path):
    imported = set()
    for node in python_ast.walk(python_tree(path)):
        if isinstance(node, python_ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, python_ast.ImportFrom) and node.level == 0:
            imported.add(node.module)
    allowed = ALLOWED_IMPORTS | OPTIONAL_IMPORTS.get(path.name, set())
    assert imported <= allowed, imported - allowed


def test_only_entrypoints_touch_the_operating_system():
    # Reading files belongs to entry points, not the language stages. The LSP only reads imports
    # relative to an open document so its analysis matches the CLI.
    for path in MODULES:
        # worker.py is the other entry point: it reads its request from standard input.
        # host.py is the only module that gives a program local files, network access and
        # subprocesses, behind an explicit declaration, a CLI grant and an environment switch.
        # migrate_files.py is the only module that writes files, for `nex migrate --write`.
        if path.name in ("cli.py", "__main__.py", "worker.py", "host.py", "migrate_files.py", "lsp.py"):
            continue
        names = set()
        for node in python_ast.walk(python_tree(path)):
            if isinstance(node, python_ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, python_ast.ImportFrom) and node.level == 0:
                names.add(node.module.split(".")[0])
        forbidden = {"os", "pathlib", "subprocess", "socket", "shutil", "io"}
        if path.name == "tooling.py":
            # It locates the specification that ships with the project; the next test pins that down.
            forbidden -= {"pathlib"}
        assert names & forbidden == set(), path.name


def test_the_language_server_only_reads_files_for_declared_imports():
    tree = python_tree(PACKAGE / "lsp.py")
    reads = [python_ast.unparse(node.func) for node in python_ast.walk(tree)
             if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Attribute)
             and node.func.attr in ("read_text", "read_bytes", "write_text", "write_bytes", "unlink", "mkdir")]
    assert reads == ["path.read_text"]


def test_the_tooling_reads_one_fixed_file_and_nothing_else():
    tree = python_tree(PACKAGE / "tooling.py")
    reads = [python_ast.unparse(node.func) for node in python_ast.walk(tree)
             if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Attribute)
             and node.func.attr in ("read_text", "read_bytes", "open", "iterdir", "glob", "rglob", "write_text")]
    assert reads == ["_SPEC_PATH.read_text"]
    # The path is built from the location of the package, never from an argument.
    source = (PACKAGE / "tooling.py").read_text(encoding="utf-8")
    assert '_SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "language-spec.md"' in source
    assert source.count("Path(") == 1


def test_the_only_file_access_is_reading_the_program():
    tree = python_tree(PACKAGE / "cli.py")
    attributes = {node.attr for node in python_ast.walk(tree) if isinstance(node, python_ast.Attribute)}
    assert "read_bytes" in attributes
    assert attributes & {"write_text", "write_bytes", "unlink", "mkdir", "rmdir", "rename", "system", "popen"} == set()
    # `nex migrate --write` writes through migrate_files.py, never by itself: cli.py asks the
    # operating system for nothing that changes a file.
    os_calls = {node.func.attr for node in python_ast.walk(tree)
                if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Attribute)
                and isinstance(node.func.value, python_ast.Name) and node.func.value.id == "os"}
    # (It opens os.devnull, which changes no file; that is not on the list.)
    assert os_calls & {"write", "replace", "rename", "remove", "unlink", "chmod", "mkdir", "rmdir"} == set()


# The one module that writes files: migrate_files.py (decision 0019, G7)

# What it may ask the operating system: open, read, write and close a file, read and copy its
# permission bits, replace one file by another, remove a file, and draw a random name.
WRITER_OS_CALLS = {"open", "read", "write", "close", "stat", "chmod", "replace", "remove", "urandom"}


def test_the_writer_only_asks_the_system_for_its_few_operations_and_only_inside_files():
    tree = python_tree(PACKAGE / "migrate_files.py")
    found = {}
    for klass in [node for node in tree.body if isinstance(node, python_ast.ClassDef)]:
        for node in python_ast.walk(klass):
            if (isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Attribute)
                    and isinstance(node.func.value, python_ast.Name) and node.func.value.id == "os"):
                found.setdefault(klass.name, set()).add(node.func.attr)
    assert set(found) == {"Files"}
    assert found["Files"] <= WRITER_OS_CALLS
    # Outside the class `Files`, no function calls the operating system directly.
    outside = [node for node in tree.body if not isinstance(node, python_ast.ClassDef)]
    for top in outside:
        for node in python_ast.walk(top):
            if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Attribute):
                assert not (isinstance(node.func.value, python_ast.Name) and node.func.value.id == "os"), \
                    python_ast.unparse(node)


def test_only_the_cli_uses_the_writer():
    for path in MODULES:
        if path.name in ("cli.py", "migrate_files.py"):
            continue
        for node in python_ast.walk(python_tree(path)):
            if isinstance(node, python_ast.ImportFrom):
                module = node.module or ""
                assert "migrate_files" not in module and "migrate_files" not in {a.name for a in node.names}, path.name
            elif isinstance(node, python_ast.Import):
                assert not any("migrate_files" in alias.name for alias in node.names), path.name


def test_the_writer_only_writes_nex_files(tmp_path):
    from nexora.migrate_files import Planned, write_all

    other = tmp_path / "secrets.env"
    other.write_text("TOKEN=1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        write_all([Planned(str(other), other.read_bytes(), b"")])
    assert other.read_text(encoding="utf-8") == "TOKEN=1\n"


def test_the_package_has_no_runtime_dependencies():
    import tomllib

    project = tomllib.loads((PACKAGE.parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == []


# The language

def test_the_built_in_functions_are_exactly_the_documented_ones():
    assert set(BUILTINS) == {
        "print", "to_text", "to_float", "to_int",
        # The functions of a type (decision 0011): pure, they only read their arguments.
        "Text.length", "Text.slice", "Text.contains", "Text.starts_with", "Text.ends_with",
        "Int.can_parse", "Int.parse", "Float.can_parse", "Float.parse",
        # The functions of List (D08): immutable, they build a new value or read one.
        "List.length", "List.get", "List.append", "List.concat", "List.contains",
        # The constructors of Option and Result, and their inspection (decision 0016).
        "Some", "Ok", "Err",
        "Option.is_some", "Option.is_none", "Option.value_or", "Option.value",
        "Result.is_ok", "Result.is_err", "Result.value_or", "Result.value", "Result.error",
        # The input and the files (decision 0015). The arguments and the standard input
        # need no declaration; the files do.
        "args", "input", "read_file", "write_file",
        # The opt-in host operations (decision 0020).
        "Net.get", "Process.run",
    }


@pytest.mark.parametrize("name", [
    "eval", "exec", "open", "__import__", "system", "getattr", "compile", "exit", "import_module",
])
def test_python_functions_do_not_exist_in_nexora(name):
    assert check_codes(in_main(f'{name}("x")')) == ["E2008"]


@pytest.mark.parametrize("statement", [
    'import os',                                # reserved word
    'let x = __import__("os").system("echo hi")',   # no attribute access in the language
    'let x = os.system("echo hi")',
    'let x = lambda: 1',
    'exec("print(1)")',
    'let x = `echo hi`',
    'let x = $(echo hi)',
    'let x = {"a": 1}',
    'let x = "a" % 1',
    'let x = print.__class__',
])
def test_python_and_shell_constructs_are_rejected_before_anything_runs(statement):
    analysis = analyze(Source("t.nex", in_main(statement)))
    assert not analysis.ok and analysis.checked is None
    assert {d.category for d in analysis.diagnostics} <= {"lexical", "syntax", "semantic", "type"}


def test_text_is_data_and_is_never_interpreted(capsys, tmp_path):
    # Text that looks like code, format strings or escape sequences is printed as it is.
    path = tmp_path / "data.nex"
    path.write_text(
        'fn main() {\n'
        '    print("__import__(\'os\').system(\'echo hacked\')")\n'
        '    print("%s %d \\{0} $(whoami) `id`")\n'
        '    print(to_text(1) + "; rm -rf /")\n'
        '}\n',
        encoding="utf-8",
    )
    assert cli.main(["run", str(path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "__import__('os').system('echo hacked')",
        "%s %d {0} $(whoami) `id`",
        "1; rm -rf /",
    ]


def test_a_program_cannot_reach_the_variables_of_the_interpreter():
    for name in ("self", "sys", "os", "__builtins__", "__name__", "environment", "checked"):
        assert check_codes(in_main(f"print({name})")) == ["E2005"], name


def test_running_a_program_creates_no_files(tmp_path, monkeypatch, capsys):
    path = tmp_path / "program.nex"
    path.write_text('fn main() {\n    print("x")\n}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for command in ("run", "check", "inspect"):
        assert cli.main([command, "program.nex"]) == 0
    capsys.readouterr()
    assert [entry.name for entry in tmp_path.iterdir()] == ["program.nex"]


# check and inspect never execute

SIDE_EFFECTS = (
    "fn loud(n: Int) gives Int\n"
    "    needs n > 0\n"
    "{\n"
    "    print(\"RAN\")\n"
    "    return n / 0\n"
    "}\n"
    "fn forever(n: Int) gives Int {\n"
    "    return forever(n + 1)\n"
    "}\n"
    "fn main() {\n"
    "    print(\"RAN\")\n"
    "    print(loud(1))\n"
    "    print(forever(0))\n"
    "}\n"
)


@pytest.mark.parametrize("command", [["check"], ["check", "--format", "json"], ["inspect"]])
def test_static_commands_do_not_run_the_program(command, tmp_path, capsys, monkeypatch):
    # The program prints, divides by zero and recurses forever. None of it may happen.
    def forbidden(*arguments):
        raise AssertionError("the interpreter must not be started")
    monkeypatch.setattr(cli, "run", forbidden)
    path = tmp_path / "effects.nex"
    path.write_text(SIDE_EFFECTS, encoding="utf-8")
    assert cli.main([command[0], str(path), *command[1:]]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "RAN\n" not in captured.out and "E3" not in captured.out

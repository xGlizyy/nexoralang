"""`nex migrate` (decision 0019, 8.2 and 8.7.1), tested at the command line: T5, T6, T7 and T9 of 8.9.

The routes, the refusals and the exit codes are tested through `cli.main`, as `nex` runs them. The
injected failures of T9 use the interface of 8.9.2, given to the command by the tests only. The
interruptions at the end of this file are real: a `nex migrate --write` process receives SIGINT.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from nexora import cli, migrate
from test_migrate_files import Faulty

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "migration" / "corpus011"

VERIFIED = "structure verified; text outside the edits verified; behaviour not checked by this command"

OLD_DOUBLE = "fn double(n: Int) -> Int {\n    requires n >= 0\n    return n * 2\n}\n"
NEW_DOUBLE = "fn double(n: Int) gives Int\n    needs n >= 0\n{\n    return n * 2\n}\n"
OLD_MAIN = 'import "lib/double.nex"\n\nfn main() -> Void {\n    print(double.double(2))\n}\n'
OLD_LIB = "pub " + OLD_DOUBLE
NEW_LIB = "pub " + NEW_DOUBLE


def write(directory: Path, files: dict[str, str | bytes]) -> None:
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_bytes(text.encode("utf-8"))


def snapshot(directory: Path) -> dict[str, bytes]:
    """Every file under `directory`, temporary files included."""
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def nex(arguments: list[str], directory: Path, monkeypatch, capsys) -> tuple[int, str, str]:
    monkeypatch.chdir(directory)
    capsys.readouterr()
    code = cli.main(arguments)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def migrate_with(files, path: str, directory: Path, monkeypatch, capsys) -> tuple[int, str, str]:
    """`nex migrate path --write` with the file operations of 8.9.2 replaced by `files`."""
    monkeypatch.chdir(directory)
    monkeypatch.setattr(cli.migrate_files, "Files", lambda: files)
    capsys.readouterr()
    code = cli.main(["migrate", path, "--write"])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# T6: one program per row of 8.2

def test_route_migrate_shows_the_text_and_the_edits_and_writes_nothing(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"double.nex": OLD_DOUBLE})
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "double.nex"], tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert out.startswith("--- double.nex: 4 edits\n  1:19  E1  '->' -> 'gives'\n")
    assert NEW_DOUBLE in out and VERIFIED in out and "Nothing was written" in out
    assert snapshot(tmp_path) == before


def test_route_migrate_with_write_replaces_every_file_of_the_program(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"main.nex": OLD_MAIN, "lib/double.nex": OLD_LIB})
    code, out, err = nex(["migrate", "main.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert out.splitlines() == ["replaced: lib/double.nex", "replaced: main.nex", VERIFIED]
    assert snapshot(tmp_path) == {
        "lib/double.nex": NEW_LIB.encode(),
        "main.nex": b'import "lib/double.nex"\n\nfn main() {\n    print(double.double(2))\n}\n',
    }
    assert nex(["run", "main.nex"], tmp_path, monkeypatch, capsys)[:2] == (0, "4\n")


def test_route_already_migrated_writes_nothing(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"double.nex": NEW_DOUBLE})
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "double.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert out == "double.nex: the program is already written in the syntax of 0.12; nothing to migrate\n"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("files, markers", [
    # A mixed file: the old arrow and a new clause word.
    ({"main.nex": "fn f(x: Int) -> Int\n    needs x > 0\n{\n    return x\n}\n"},
     ["main.nex: mixed: it has markers of 0.11 and of 0.12"]),
    # A mixed program: the program in 0.12, its module in 0.11.
    ({"main.nex": 'import "lib/double.nex"\n\nfn main() {\n    print(double.double(2))\n}\n',
      "lib/double.nex": OLD_LIB},
     ["lib/double.nex: markers of 0.11", "main.nex: neutral: no marker of either syntax"]),
])
def test_route_refuse_a_program_that_is_neither(files, markers, tmp_path, monkeypatch, capsys):
    write(tmp_path, files)
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "main.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert "passes neither the check of 0.11 nor the check of 0.12; nothing was written" in err
    assert [line.strip() for line in err.splitlines() if line.startswith("  ") and ": " in line][:len(markers)] == markers
    assert "With the front end of 0.11:" in err and "With the front end of 0.12:" in err
    assert snapshot(tmp_path) == before


def test_route_nothing_to_migrate_when_both_read_the_same(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"types.nex": 'type Small = Int where value < 10, "Small"\ntype P = { x: Int }\n'})
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "types.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert out == "types.nex: nothing to migrate: the program reads the same in 0.11 and in 0.12\n"
    assert snapshot(tmp_path) == before


def test_route_nothing_to_migrate_still_refuses_a_module_named_like_a_keyword(tmp_path, monkeypatch, capsys):
    # 8.2.2: it passes both checks, but the module could never be used by its name.
    write(tmp_path, {"types.nex": 'import "m/needs.nex"\ntype P = { x: Int }\n', "m/needs.nex": "type T = { y: Int }\n"})
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "types.nex"], tmp_path, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert "types.nex:1:8: 'needs' is a keyword from 0.12: rename the file 'needs.nex'" in err
    assert snapshot(tmp_path) == before


def test_route_nothing_to_migrate_refuses_trees_that_differ(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"types.nex": "type P = { x: Int }\n"})
    monkeypatch.setattr(cli.migrate, "equivalent", lambda old, new: False)
    code, out, err = nex(["migrate", "types.nex"], tmp_path, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert "0.11 and 0.12 read this file differently; nothing was written" in err


# T5: one program per row of 8.6. Code 1, the message and its position, nothing written.

REFUSALS = {
    "a clause on the line of the brace": (
        "fn f(x: Int) -> Int { requires x > 0\n    return x\n}\n",
        "f.nex:1:23: Put 'requires' on its own line, then run nex migrate again"),
    "the last clause followed by the closing brace": (
        "fn g(x: Int) -> Void { requires x > 0 }\n",
        "f.nex:1:24: Put 'requires' on its own line, then run nex migrate again"),
    "a comment after a brace alone": (
        "fn one() -> Int\n{ // note\n    return 1\n}\n", "f.nex:2:1: Move this comment, then run nex migrate again"),
    "a statement after a brace alone": (
        "fn one() -> Int\n{ return 1\n}\n",
        "f.nex:2:1: Put the first statement on its own line, then run nex migrate again"),
    "a name that becomes a keyword": (
        "fn f() -> Int {\n    let needs = 3\n    return needs\n}\n", "f.nex:2:9: 'needs' is a keyword from 0.12: rename it"),
}


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_each_refusal_names_its_file_and_its_position(name, tmp_path, monkeypatch, capsys):
    text, line = REFUSALS[name]
    write(tmp_path, {"f.nex": text})
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "f.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert line in err.splitlines()
    assert "nothing was written" in err.splitlines()[-1]
    assert snapshot(tmp_path) == before


def test_a_module_named_like_a_keyword_is_refused_in_the_route_migrate(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"main.nex": 'import "m/needs.nex"\nfn main() -> Void {\n    print(1)\n}\n',
                     "m/needs.nex": "type T = Int where value > 0\n"})
    before = snapshot(tmp_path)
    code, _, err = nex(["migrate", "main.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert code == 1
    assert "main.nex:1:8: 'needs' is a keyword from 0.12: rename the file 'needs.nex'" in err
    assert snapshot(tmp_path) == before


def test_a_file_changed_before_the_re_read_is_refused_and_nothing_is_written(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"main.nex": OLD_MAIN, "lib/double.nex": OLD_LIB})
    before = snapshot(tmp_path)
    changed = str((tmp_path / "lib" / "double.nex").resolve())
    code, out, err = migrate_with(Faulty(change=changed, reads_before_change=1), "main.nex", tmp_path,
                                  monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [
        "lib/double.nex: This file changed while it was being migrated: run nex migrate again",
        "error: main.nex: nothing was written",
    ]
    assert snapshot(tmp_path) == before


# 8.7.1: the other exit codes

def test_a_file_that_cannot_be_read_is_code_4(tmp_path, monkeypatch, capsys):
    assert nex(["migrate", "missing.nex"], tmp_path, monkeypatch, capsys)[0] == 4
    write(tmp_path, {"latin.nex": b"fn main() -> Void {\n    print(\"\xe9\")\n}\n"})
    assert nex(["migrate", "latin.nex"], tmp_path, monkeypatch, capsys)[0] == 4


@pytest.mark.parametrize("module, error", [(None, "error[E0001]"), (b"pub fn f() -> Int {\n    return \xe9\n}\n", "error[E0002]")])
def test_a_module_that_cannot_be_read_is_reported_as_by_every_command(module, error, tmp_path, monkeypatch, capsys):
    # 8.7.1 gives code 4 to a file that cannot be read "as for every command": for a module, every
    # command reports E0001 or E0002 and exits with 1. Nothing is written.
    write(tmp_path, {"main.nex": OLD_MAIN, **({"lib/double.nex": module} if module else {})})
    before = snapshot(tmp_path)
    code, out, err = nex(["migrate", "main.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert error in err and "nothing was written" in err
    assert snapshot(tmp_path) == before
    assert nex(["check", "main.nex"], tmp_path, monkeypatch, capsys)[0] == 1


def test_wrong_usage_is_code_2(tmp_path, monkeypatch, capsys):
    write(tmp_path, {"notes.txt": "x"})
    assert nex(["migrate"], tmp_path, monkeypatch, capsys)[0] == 2
    assert nex(["migrate", "notes.txt"], tmp_path, monkeypatch, capsys)[0] == 2
    assert snapshot(tmp_path) == {"notes.txt": b"x"}


@pytest.mark.parametrize("broken, what", [
    ("apply", "a character outside the edits changed (G2)"),
    ("equivalent", "the migrated file is not structurally equivalent (G3)"),
    ("analysis", "the migrated program does not pass the check of 0.12 (G4)"),
])
def test_a_check_that_fails_after_the_edits_is_a_defect_and_nothing_is_written(broken, what, tmp_path,
                                                                                monkeypatch, capsys):
    write(tmp_path, {"double.nex": OLD_DOUBLE})
    before = snapshot(tmp_path)
    if broken == "apply":
        monkeypatch.setattr(cli.migrate, "apply", lambda text, edits: text + "// extra\n")
    elif broken == "equivalent":
        monkeypatch.setattr(cli.migrate, "equivalent", lambda old, new: False)
    else:
        monkeypatch.setattr(cli.migrate, "apply", lambda text, edits: text)
        monkeypatch.setattr(cli.migrate, "kept_outside", lambda text, edits, output: True)
    code, _, err = nex(["migrate", "double.nex", "--write"], tmp_path, monkeypatch, capsys)
    assert code == 70
    assert f"double.nex: {what}. This is a bug in NEXORA; nothing was written." in err
    assert snapshot(tmp_path) == before


def test_a_function_in_a_program_that_passes_both_checks_is_a_defect(tmp_path, monkeypatch, capsys):
    # 8.2.2, premise 3: such a program cannot exist; if the edits found one, it is a bug.
    write(tmp_path, {"types.nex": "type P = { x: Int }\n"})
    real = migrate.plan
    monkeypatch.setattr(cli.migrate, "plan", lambda text, tokens, program: migrate.FilePlan(
        (migrate.Edit(0, 0, "", "E1"),), real(text, tokens, program).refusals))
    assert nex(["migrate", "types.nex"], tmp_path, monkeypatch, capsys)[0] == 70


# The bytes of the files (8.5.1, M10)

def test_line_endings_and_the_byte_order_mark_are_kept(tmp_path, monkeypatch, capsys):
    crlf = OLD_DOUBLE.replace("\n", "\r\n").encode()
    write(tmp_path, {"crlf.nex": crlf, "bom.nex": b"\xef\xbb\xbf" + OLD_DOUBLE.encode()})
    for name in ("crlf.nex", "bom.nex"):
        assert nex(["migrate", name, "--write"], tmp_path, monkeypatch, capsys)[0] == 0
    assert (tmp_path / "crlf.nex").read_bytes() == NEW_DOUBLE.replace("\n", "\r\n").encode()
    assert (tmp_path / "bom.nex").read_bytes() == b"\xef\xbb\xbf" + NEW_DOUBLE.encode()


# T7: idempotence and determinism, on the frozen corpus

def corpus_programs() -> list[str]:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["programs"] if isinstance(manifest, dict) else manifest
    return sorted(entry["path"] for entry in entries if not entry["diagnostics_011"]["without_main"])


def test_the_migrated_corpus_is_already_migrated_and_the_output_is_deterministic(tmp_path, monkeypatch, capsys):
    shutil.copytree(CORPUS, tmp_path / "corpus")
    directory = tmp_path / "corpus"
    programs = corpus_programs()
    assert len(programs) >= 80
    for program in programs:
        first = nex(["migrate", program], directory, monkeypatch, capsys)
        assert first == nex(["migrate", program], directory, monkeypatch, capsys), program   # G6
        code, _, err = nex(["migrate", program, "--write"], directory, monkeypatch, capsys)
        assert (code, err) == (0, ""), (program, err)
    written = snapshot(directory)
    for program in programs:
        code, out, err = nex(["migrate", program, "--write"], directory, monkeypatch, capsys)
        assert (code, err) == (0, ""), program
        assert out == f"{program}: the program is already written in the syntax of 0.12; nothing to migrate\n"
    assert snapshot(directory) == written


# T9: a failed write at each step of G7, for the first, the second and the last file

THREE = {
    "a.nex": 'import "b.nex"\nimport "c.nex"\n\nfn main() -> Void {\n    print(b.f(1) + c.g(2))\n}\n',
    "b.nex": "pub fn f(n: Int) -> Int {\n    requires n > 0\n    return n\n}\n",
    "c.nex": "pub fn g(n: Int) -> Int {\n    ensures result > 0\n    return n\n}\n",
}


@pytest.mark.parametrize("step", ["create", "write", "copy_permissions", "replace"])
@pytest.mark.parametrize("which", [1, 2, 3])
def test_a_failed_write_is_code_4_with_the_three_lists(step, which, tmp_path, monkeypatch, capsys):
    write(tmp_path, THREE)
    before = snapshot(tmp_path)
    code, out, err = migrate_with(Faulty(fail=step, at=which), "a.nex", tmp_path, monkeypatch, capsys)
    names = ["a.nex", "b.nex", "c.nex"]
    assert code == 4
    assert out.splitlines() == [f"replaced: {name}" for name in names[:which - 1]]
    assert err.splitlines() == [
        f"error: a.nex: {names[which - 1]} could not be written; the files already replaced stay replaced",
        f"  replaced: {', '.join(names[:which - 1]) or '(none)'}",
        f"  failed: {names[which - 1]} (No space left on device)",
        f"  not written: {', '.join(names[which:]) or '(none)'}",
    ]
    after = snapshot(tmp_path)
    assert sorted(after) == names                                    # no temporary file is left
    for name in names[:which - 1]:
        assert after[name] != before[name]                           # replaced, not restored
    for name in names[which - 1:]:
        assert after[name] == before[name]                           # untouched


@pytest.mark.parametrize("step", ["create", "write", "copy_permissions", "replace"])
def test_an_injected_interruption_is_code_130_with_the_three_lists(step, tmp_path, monkeypatch, capsys):
    # A KeyboardInterrupt raised by the injection of 8.9.2. The real Ctrl+C is tested below.
    write(tmp_path, THREE)
    code, out, err = migrate_with(Faulty(fail=step, at=2, error=KeyboardInterrupt()), "a.nex", tmp_path,
                                  monkeypatch, capsys)
    assert code == 130
    assert out == "replaced: a.nex\n"
    assert err.splitlines()[1:] == ["  replaced: a.nex", "  failed: b.nex (interrupted)", "  not written: c.nex"]
    assert sorted(snapshot(tmp_path)) == ["a.nex", "b.nex", "c.nex"]


def test_a_temporary_file_that_could_not_be_removed_is_listed(tmp_path, monkeypatch, capsys):
    write(tmp_path, THREE)
    files = Faulty(fail="replace", at=2)
    monkeypatch.setattr(files, "delete", lambda path: (_ for _ in ()).throw(OSError(13, "Permission denied")))
    code, _, err = migrate_with(files, "a.nex", tmp_path, monkeypatch, capsys)
    assert code == 4
    left = [name for name in snapshot(tmp_path) if name.endswith(".tmp")]
    assert len(left) == 1 and left[0].startswith("b.nex.")
    assert err.splitlines()[-1] == (f"  left behind: {left[0]}, a temporary file that could not be removed "
                                    "(Permission denied); it does not end in .nex, so no program reads it")


def test_an_interruption_after_a_rename_lists_that_file_as_replaced(tmp_path, monkeypatch, capsys):
    from test_migrate_files import LateInterrupt

    write(tmp_path, THREE)
    code, out, err = migrate_with(LateInterrupt(at=2), "a.nex", tmp_path, monkeypatch, capsys)
    assert code == 130
    assert out == "replaced: a.nex\nreplaced: b.nex\n"
    assert err.splitlines() == [
        "error: a.nex: interrupted; the files already replaced stay replaced",
        "  replaced: a.nex, b.nex",
        "  not written: c.nex",
    ]
    assert sorted(snapshot(tmp_path)) == ["a.nex", "b.nex", "c.nex"]


# A real interruption: SIGINT to a running `nex migrate --write`

HARNESS = textwrap.dedent('''
    """Runs `nex migrate --write` as `nex` runs it, and pauses it at one step so that the test can
    send a real SIGINT there. The pause is the only thing this script adds: nothing reaches it from
    `nex` itself (decision 0019, 8.9.2)."""
    import pathlib
    import sys
    import time

    sys.path.insert(0, {src!r})
    from nexora import cli, migrate_files

    STEP, AT, MARK = sys.argv[1], int(sys.argv[2]), pathlib.Path(sys.argv[3])

    class Paused(migrate_files.Files):
        count = 0

        def _pause(self, kind):
            if kind == STEP:
                Paused.count += 1
                if Paused.count == AT:
                    MARK.write_text("paused")
                    while True:
                        time.sleep(0.05)

        def read(self, path):
            self._pause("read")
            return super().read(path)

        def replace(self, source, target):
            self._pause("replace")
            super().replace(source, target)

    migrate_files.Files = Paused
    sys.exit(cli.main(["migrate", "a.nex", "--write"]))
''')

posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows cannot deliver a Ctrl+C to one child process without the rest of its console: "
           "CTRL_C_EVENT is not received by a separate process group. Run on Linux or macOS.",
)


def interrupt(step: str, at: int, tmp_path: Path) -> subprocess.CompletedProcess:
    write(tmp_path, THREE)
    harness = tmp_path.parent / f"{tmp_path.name}-harness.py"
    harness.write_text(HARNESS.format(src=str(ROOT / "src")), encoding="utf-8")
    mark = tmp_path.parent / f"{tmp_path.name}-paused"
    process = subprocess.Popen([sys.executable, str(harness), step, str(at), str(mark)], cwd=tmp_path,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    deadline = time.monotonic() + 60
    while not mark.exists():
        assert process.poll() is None, process.communicate()
        assert time.monotonic() < deadline, "the process never reached the step"
        time.sleep(0.02)
    os.kill(process.pid, signal.SIGINT)
    out, err = process.communicate(timeout=60)
    return subprocess.CompletedProcess(process.args, process.returncode, out, err)


@posix_only
def test_a_real_ctrl_c_while_writing_is_code_130_with_the_three_lists(tmp_path):
    result = interrupt("replace", 2, tmp_path)
    assert result.returncode == 130, result.stderr
    assert result.stdout == "replaced: a.nex\n"
    assert result.stderr.splitlines() == [
        "error: a.nex: b.nex was interrupted; the files already replaced stay replaced",
        "  replaced: a.nex",
        "  failed: b.nex (interrupted)",
        "  not written: c.nex",
    ]
    files = snapshot(tmp_path)
    assert sorted(files) == ["a.nex", "b.nex", "c.nex"]              # its temporary file was removed
    assert files["b.nex"] == THREE["b.nex"].encode() and files["c.nex"] == THREE["c.nex"].encode()


@posix_only
def test_a_real_ctrl_c_before_writing_is_code_130_and_nothing_is_written(tmp_path):
    result = interrupt("read", 2, tmp_path)
    assert result.returncode == 130, result.stderr
    assert result.stderr.strip() == "interrupted: a.nex"
    assert snapshot(tmp_path) == {name: text.encode() for name, text in THREE.items()}

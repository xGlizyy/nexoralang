"""Writing the migrated files (decision 0019, G7), with failures injected (8.9.2, test T9).

`migrate_files.Files` is the one interface every file operation goes through. Here it is
replaced by `Faulty`, which makes the N-th operation of a kind fail, changes a file between the
first read and the re-read, or interrupts at a given step: deterministically, without timing.
"""

import os
import sys

import pytest

from nexora import migrate_files
from nexora.migrate_files import Files, Planned, write_all


class Faulty(Files):
    """`Files`, with one failure injected."""

    def __init__(self, fail: str | None = None, at: int = 1, error: BaseException | None = None,
                 change: str | None = None) -> None:
        self.fail, self.at, self.count = fail, at, 0
        self.error = error or OSError(28, "No space left on device")
        self.change = change
        self.calls: list[tuple[str, str]] = []

    def _step(self, kind: str, path: str) -> None:
        self.calls.append((kind, path))
        if kind == self.fail:
            self.count += 1
            if self.count == self.at:
                raise self.error

    def read(self, path):
        data = super().read(path)
        if self.change and path == self.change:
            data += b"// changed by someone else\n"   # what the re-read finds
        return data

    def create(self, path):
        self._step("create", path)
        super().create(path)

    def write(self, path, data):
        self._step("write", path)
        super().write(path, data)

    def copy_permissions(self, source, target):
        self._step("copy_permissions", target)
        super().copy_permissions(source, target)

    def replace(self, source, target):
        self._step("replace", target)
        super().replace(source, target)


@pytest.fixture
def program(tmp_path):
    """Three files, with their original bytes and the bytes migration would write."""
    planned = []
    for name in ("a.nex", "b.nex", "c.nex"):
        path = tmp_path / name
        path.write_bytes(f"fn {name[0]}() -> Int {{\n    return 1\n}}\n".encode())
        planned.append(Planned(str(path), path.read_bytes(), f"fn {name[0]}() gives Int {{\n    return 1\n}}\n".encode()))
    return tmp_path, planned


def contents(directory) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def test_every_file_is_written_in_the_order_of_its_path(program):
    directory, planned = program
    files = Faulty()
    report = write_all(list(reversed(planned)), files)
    assert report.ok
    assert report.replaced == tuple(item.path for item in planned)
    assert [path for kind, path in files.calls if kind == "replace"] == [item.path for item in planned]
    assert contents(directory) == {os.path.basename(i.path): i.output for i in planned}


def test_the_temporary_files_never_end_in_nex_and_none_is_left(program):
    directory, planned = program
    files = Faulty()
    write_all(planned, files)
    temporaries = [path for kind, path in files.calls if kind == "create"]
    assert temporaries and all(path.endswith(".tmp") and not path.endswith(".nex") for path in temporaries)
    assert all(os.path.dirname(t) == os.path.dirname(p.path) for t, p in zip(temporaries, planned, strict=True))
    assert sorted(contents(directory)) == ["a.nex", "b.nex", "c.nex"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_permission_bits_of_the_original_are_kept(program):
    directory, planned = program
    os.chmod(planned[0].path, 0o640)
    os.chmod(planned[1].path, 0o755)
    write_all(planned, Faulty())
    assert os.stat(planned[0].path).st_mode & 0o7777 == 0o640
    assert os.stat(planned[1].path).st_mode & 0o7777 == 0o755


def test_a_file_changed_before_the_re_read_means_nothing_is_written(program):
    directory, planned = program
    before = contents(directory)
    report = write_all(planned, Faulty(change=planned[1].path))
    assert not report.ok
    assert report.changed == (planned[1].path,)
    assert report.replaced == () and report.failed is None
    assert contents(directory) == before


@pytest.mark.parametrize("step", ["create", "write", "copy_permissions", "replace"])
@pytest.mark.parametrize("which", [1, 2, 3])
def test_the_first_failed_write_stops_and_says_what_happened(program, step, which):
    directory, planned = program
    report = write_all(planned, Faulty(fail=step, at=which))
    paths = [item.path for item in planned]
    assert report.replaced == tuple(paths[:which - 1])
    assert report.failed == (paths[which - 1], "No space left on device")
    assert report.not_written == tuple(paths[which:])
    found = contents(directory)
    for item in planned[:which - 1]:
        assert found[os.path.basename(item.path)] == item.output          # replaced, not restored
    for item in planned[which - 1:]:
        assert found[os.path.basename(item.path)] == item.original        # untouched
    assert sorted(found) == ["a.nex", "b.nex", "c.nex"]                    # no temporary file left


@pytest.mark.parametrize("step", ["create", "write", "copy_permissions", "replace"])
def test_an_interruption_is_handled_as_a_failed_write(program, step):
    directory, planned = program
    report = write_all(planned, Faulty(fail=step, at=2, error=KeyboardInterrupt()))
    paths = [item.path for item in planned]
    assert report.interrupted
    assert report.replaced == (paths[0],)
    assert report.failed == (paths[1], "interrupted")
    assert report.not_written == (paths[2],)
    assert sorted(contents(directory)) == ["a.nex", "b.nex", "c.nex"]


def test_a_temporary_file_that_cannot_be_removed_is_left_without_hiding_the_failure(program, monkeypatch):
    directory, planned = program
    files = Faulty(fail="replace", at=1)
    monkeypatch.setattr(files, "delete", lambda path: (_ for _ in ()).throw(OSError(13, "Permission denied")))
    report = write_all(planned, files)
    assert report.failed == (planned[0].path, "No space left on device")
    left = [name for name in contents(directory) if name.endswith(".tmp")]
    assert len(left) == 1 and not left[0].endswith(".nex")


def test_only_nex_files_are_written(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        write_all([Planned(str(other), b"x", b"y")], Faulty())
    assert other.read_text(encoding="utf-8") == "x"


def test_the_byte_order_mark_goes_back_first():
    text, had_bom = migrate_files.decode(migrate_files.BOM + b"fn main() -> Void {\n}\n")
    assert had_bom and text.startswith("fn main()")
    assert migrate_files.encode("fn main() {\n}\n", had_bom) == migrate_files.BOM + b"fn main() {\n}\n"
    assert migrate_files.encode("x", False) == b"x"

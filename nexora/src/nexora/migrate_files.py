"""Where `nex migrate --write` writes, and the only module of NEXORA that writes files.

Decision 0019, G7. Every file of the program is read again before any is written; if one changed,
nothing is written. Then each file is written to a temporary file beside it, whose name never ends
in `.nex`, which gets the permission bits of the original and replaces it with one rename, in the
order of their paths. On the first failed write, or an interruption, it stops, removes the
temporary file of that file and says which files were replaced, which one failed and which were
not written. Replacing several files is not one transaction: files already replaced stay replaced.

Every operation on files goes through `Files`, one small interface. The tests replace it to make an
operation fail, to change a file between the first read and the re-read, or to interrupt at a given
step (decision 0019, 8.9.2). Nothing else can reach that: it is not an option of `nex`, an
environment variable or a public function.

Only `cli.py` uses this module, and only for `nex migrate --write` (tests/test_security.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

BOM = b"\xef\xbb\xbf"


class Files:
    """The file operations `nex migrate --write` uses, and nothing else."""

    def read(self, path: str) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            chunks = []
            while chunk := os.read(descriptor, 1 << 16):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    def create(self, path: str) -> None:
        """Creates an empty file, only if no file has that name (O_EXCL)."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        os.close(os.open(path, flags, 0o600))

    def write(self, path: str, data: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC | getattr(os, "O_BINARY", 0))
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(descriptor, view):]
        finally:
            os.close(descriptor)

    def copy_permissions(self, source: str, target: str) -> None:
        os.chmod(target, os.stat(source).st_mode & 0o7777)

    def replace(self, source: str, target: str) -> None:
        os.replace(source, target)

    def delete(self, path: str) -> None:
        os.remove(path)

    def temporary_name(self, path: str) -> str:
        """The name of the original, a random part and `.tmp`: never ends in `.nex`."""
        return f"{path}.{os.urandom(4).hex()}.tmp"


@dataclass(frozen=True)
class Planned:
    """One file to write: its path, the bytes that were migrated and the bytes to write."""

    path: str
    original: bytes
    output: bytes


@dataclass(frozen=True)
class Report:
    """What happened when writing. `changed` is set when the re-read found a difference, and then
    nothing was written; otherwise `failed` names the first failed write, if any."""

    replaced: tuple[str, ...] = ()
    failed: tuple[str, str] | None = None        # (path, the error of the system)
    not_written: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    interrupted: bool = False

    @property
    def ok(self) -> bool:
        return not self.changed and self.failed is None and not self.interrupted


def decode(data: bytes) -> tuple[str, bool]:
    """The text of a file as `nex` reads it, and whether it started with a byte-order mark."""
    return data.decode("utf-8-sig"), data.startswith(BOM)


def encode(text: str, had_bom: bool) -> bytes:
    """The bytes to write: the byte-order mark goes back first if the original had one (M10)."""
    return (BOM if had_bom else b"") + text.encode("utf-8")


def write_all(planned: list[Planned], files: Files | None = None) -> Report:
    """Writes the migrated files under G7. It only writes the files it is given."""
    files = files or Files()
    for item in planned:
        if not item.path.endswith(".nex"):
            raise ValueError(f"nex migrate only writes .nex files, not {item.path}")

    # The final re-read: nothing is written if any file changed since it was migrated.
    changed = tuple(item.path for item in planned if files.read(item.path) != item.original)
    if changed:
        return Report(changed=changed, not_written=tuple(sorted(i.path for i in planned)))

    ordered = sorted(planned, key=lambda item: item.path)
    replaced: list[str] = []
    for position, item in enumerate(ordered):
        temporary = files.temporary_name(item.path)
        created = False
        try:
            files.create(temporary)
            created = True
            files.write(temporary, item.output)
            files.copy_permissions(item.path, temporary)
            files.replace(temporary, item.path)
            created = False
            replaced.append(item.path)
        except (OSError, KeyboardInterrupt) as stop:
            if created:
                _remove(files, temporary)
            rest = tuple(other.path for other in ordered[position + 1:])
            if isinstance(stop, KeyboardInterrupt):
                return Report(tuple(replaced), (item.path, "interrupted"), rest, interrupted=True)
            reason = stop.strerror or type(stop).__name__
            return Report(tuple(replaced), (item.path, reason), rest)
    return Report(tuple(replaced))


def _remove(files: Files, temporary: str) -> None:
    """Removes a temporary file after a failure. If even that fails, the file stays: its name does
    not end in `.nex`, so no program imports it (decision 0019, section 11)."""
    try:
        files.delete(temporary)
    except OSError:
        pass

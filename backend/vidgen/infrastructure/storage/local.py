"""Local-disk storage: confined to a root, atomic, never overwrites (ADR-008)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from vidgen.domain.codes import DomainError, FailureCode

CHUNK_BYTES = 1024 * 1024
MAX_COLLISION_ATTEMPTS = 10_000
FIRST_SUFFIX = 2
TEMP_PREFIX = ".tmp-"


class InvalidStorageKeyError(ValueError):
    """A storage key is empty, absolute, contains '..' or NUL, or leaves the root."""


class StorageError(DomainError):
    """The file system refused an operation (disk full, permissions, I/O error)."""

    def __init__(self) -> None:
        super().__init__(FailureCode.STORAGE_ERROR)


class LocalStorage:
    """Stores files below ``root``; keys are '/'-separated relative paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def __repr__(self) -> str:
        return f"LocalStorage(root={str(self._root)!r})"

    def write(self, key: str, data: BinaryIO) -> str:
        """Store ``data`` atomically; on a name clash use ``name-2.ext`` and return that key."""
        target = self._resolve(key)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._temp_file(target.parent) as (temp, handle):
                self._copy(data, handle)
                final = self._publish(temp, target)
        except OSError as exc:
            raise StorageError from exc
        return final.relative_to(self._root).as_posix()

    def open(self, key: str) -> BinaryIO:
        """Open a stored file for streaming reads."""
        return self._resolve(key).open("rb")

    def delete(self, key: str) -> None:
        """Delete a stored file; a missing file is fine."""
        try:
            self._resolve(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError from exc

    def exists(self, key: str) -> bool:
        """True if ``key`` is a stored file."""
        return self._resolve(key).is_file()

    def _resolve(self, key: str) -> Path:
        """Map ``key`` to a path inside the root or raise InvalidStorageKeyError."""
        pure = PurePosixPath(key)
        if not key or "\x00" in key or pure.is_absolute() or ".." in pure.parts:
            raise InvalidStorageKeyError("invalid storage key")
        path = (self._root / key).resolve()  # follows symlinks, so escapes are caught below
        if path == self._root or not path.is_relative_to(self._root):
            raise InvalidStorageKeyError("invalid storage key")
        return path

    @staticmethod
    @contextlib.contextmanager
    def _temp_file(directory: Path) -> Iterator[tuple[Path, BinaryIO]]:
        """Yield (path, handle) of a temp file in ``directory``; always removed afterwards."""
        fd, name = tempfile.mkstemp(dir=directory, prefix=TEMP_PREFIX)
        temp = Path(name)
        try:
            with os.fdopen(fd, "wb") as handle:
                yield temp, handle
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _copy(source: BinaryIO, destination: BinaryIO) -> None:
        """Copy in chunks and flush to disk before the rename."""
        while chunk := source.read(CHUNK_BYTES):
            destination.write(chunk)
        destination.flush()
        os.fsync(destination.fileno())

    @staticmethod
    def _publish(temp: Path, target: Path) -> Path:
        """Hard-link ``temp`` to a free name; link() fails if the name exists, so no overwrite."""
        for attempt in range(MAX_COLLISION_ATTEMPTS):
            name = target if attempt == 0 else _suffixed(target, attempt + FIRST_SUFFIX - 1)
            try:
                os.link(temp, name)
            except FileExistsError:
                continue
            return name
        raise StorageError


def _suffixed(path: Path, number: int) -> Path:
    """``a.mp4`` -> ``a-<number>.mp4``."""
    return path.with_name(f"{path.stem}-{number}{path.suffix}")

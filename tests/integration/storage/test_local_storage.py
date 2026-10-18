"""Local disk storage adapter (AC11 storage part, AC12 disk-full, AC1-E8, ADR-008)."""

from __future__ import annotations

import errno
import io
import os
import threading
import tracemalloc
from collections.abc import Iterator
from pathlib import Path

import pytest

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.storage.local import InvalidStorageKeyError, LocalStorage, StorageError

MB = 1024 * 1024


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """A storage rooted in a fresh directory."""
    root = tmp_path / "media"
    root.mkdir()
    return LocalStorage(root)


def files_under(root: Path) -> list[str]:
    """All regular files below ``root`` (relative, sorted), including temp files."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


class FailingStream(io.RawIOBase):
    """A readable stream that serves some bytes and then raises ``error``."""

    def __init__(self, good_bytes: int, error: BaseException) -> None:
        self._remaining = good_bytes
        self._error = error

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:  # type: ignore[override]
        if self._remaining <= 0:
            raise self._error
        n = min(len(buffer), self._remaining)
        buffer[:n] = b"x" * n
        self._remaining -= n
        return n


class GeneratedStream(io.RawIOBase):
    """Serves ``total`` bytes without ever holding them in memory; runs ``hook`` per read."""

    def __init__(self, total: int, hook: object = None) -> None:
        self._remaining = total
        self._hook = hook

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:  # type: ignore[override]
        if callable(self._hook):
            self._hook()
        n = min(len(buffer), self._remaining)
        buffer[:n] = b"v" * n
        self._remaining -= n
        return n


# ---- positive -------------------------------------------------------------------------


def test_write_returns_the_key_and_stores_the_bytes(storage: LocalStorage, tmp_path: Path) -> None:
    """TT-AC11-P3 (storage side)."""
    key = storage.write("batch1/183866.mp4", io.BytesIO(b"video-bytes"))
    assert key == "batch1/183866.mp4"
    assert (tmp_path / "media" / "batch1" / "183866.mp4").read_bytes() == b"video-bytes"


def test_exists_open_and_delete_work_on_stored_keys(storage: LocalStorage) -> None:
    """TT-AC11-P3."""
    key = storage.write("a/b.bin", io.BytesIO(b"hello"))
    assert storage.exists(key)
    with storage.open(key) as handle:
        assert handle.read() == b"hello"
    storage.delete(key)
    assert not storage.exists(key)


def test_open_supports_chunked_reads(storage: LocalStorage) -> None:
    """Streaming read: the caller can read piece by piece."""
    key = storage.write("big.bin", io.BytesIO(b"0123456789" * 100))
    with storage.open(key) as handle:
        assert handle.read(10) == b"0123456789"
        assert handle.read(5) == b"01234"


def test_unicode_and_spaced_key_names_are_stored(storage: LocalStorage) -> None:
    """TT-AC11-E3."""
    key = storage.write(
        "\u0905\u092d\u093f\u092f\u093e\u0928 2026/\u0930\u093e\u091c.mp4", io.BytesIO(b"x")
    )
    assert storage.exists(key)


def test_delete_of_a_missing_key_is_not_an_error(storage: LocalStorage) -> None:
    """Deleting twice is safe (idempotent cleanup)."""
    storage.delete("never/existed.mp4")


def test_exists_is_false_for_unknown_key(storage: LocalStorage) -> None:
    """TT-AC11-P3."""
    assert not storage.exists("nothing.mp4")


# ---- never overwrite ------------------------------------------------------------------


def test_writing_an_existing_key_never_overwrites(storage: LocalStorage, tmp_path: Path) -> None:
    """TT-AC11-P3: the second file gets a -2 suffix before the extension."""
    first = storage.write("out/a.mp4", io.BytesIO(b"first"))
    second = storage.write("out/a.mp4", io.BytesIO(b"second"))
    third = storage.write("out/a.mp4", io.BytesIO(b"third"))
    assert (first, second, third) == ("out/a.mp4", "out/a-2.mp4", "out/a-3.mp4")
    root = tmp_path / "media"
    assert (root / first).read_bytes() == b"first"
    assert (root / second).read_bytes() == b"second"
    assert (root / third).read_bytes() == b"third"


def test_concurrent_writes_to_the_same_key_all_succeed_with_distinct_keys(
    storage: LocalStorage,
) -> None:
    """TT-AC11-E8: eight threads race for one key; nothing is lost or overwritten."""
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        key = storage.write("race/x.mp4", io.BytesIO(f"data-{i}".encode()))
        with lock:
            results.append(key)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 8
    contents = set()
    for key in results:
        with storage.open(key) as handle:
            contents.add(handle.read())
    assert contents == {f"data-{i}".encode() for i in range(8)}


# ---- path safety ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["../x.mp4", "a/../../x.mp4", "/abs/x.mp4", "", ".", "..", "a/./b/../../../x", "nul\x00.mp4"],
)
def test_unsafe_keys_are_rejected_for_every_operation(storage: LocalStorage, key: str) -> None:
    """TT-AC11-N1: traversal, absolute paths and NUL never reach the file system."""
    with pytest.raises(InvalidStorageKeyError):
        storage.write(key, io.BytesIO(b"x"))
    with pytest.raises(InvalidStorageKeyError):
        storage.exists(key)
    with pytest.raises(InvalidStorageKeyError):
        storage.open(key)
    with pytest.raises(InvalidStorageKeyError):
        storage.delete(key)


def test_traversal_attempt_writes_nothing_outside_the_root(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC11-N1."""
    with pytest.raises(InvalidStorageKeyError):
        storage.write("../escape.mp4", io.BytesIO(b"x"))
    assert not (tmp_path / "escape.mp4").exists()


def test_symlink_inside_root_pointing_outside_is_refused(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC11-N4."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "media" / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidStorageKeyError):
        storage.write("link/x.mp4", io.BytesIO(b"x"))
    assert list(outside.iterdir()) == []


def test_open_of_a_missing_key_raises_file_not_found(storage: LocalStorage) -> None:
    """Missing files are a normal 'not found', not a storage failure."""
    with pytest.raises(FileNotFoundError):
        storage.open("missing.mp4")


# ---- atomicity and failures -----------------------------------------------------------


def test_final_file_does_not_exist_while_the_write_is_in_progress(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC11-E9: data goes to a temp file first and is renamed at the end."""
    final = tmp_path / "media" / "atomic.mp4"
    seen: list[bool] = []
    stream = GeneratedStream(3 * MB, hook=lambda: seen.append(final.exists()))
    storage.write("atomic.mp4", stream)
    assert seen and not any(seen)
    assert final.stat().st_size == 3 * MB


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EACCES, errno.EIO])
def test_os_error_while_writing_becomes_storage_error_and_leaves_nothing(
    storage: LocalStorage, tmp_path: Path, code: int
) -> None:
    """TT-AC1-E8, TT-AC12-N3 (B8): ENOSPC/EACCES/EIO -> STORAGE_ERROR, no partial file."""
    stream = FailingStream(2 * MB, OSError(code, os.strerror(code)))
    with pytest.raises(StorageError) as info:
        storage.write("sub/x.mp4", stream)
    assert info.value.code is FailureCode.STORAGE_ERROR
    assert isinstance(info.value, DomainError)
    assert files_under(tmp_path / "media") == []


def test_non_os_error_during_write_propagates_and_leaves_nothing(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC11-E9: a crash mid-copy leaves no final file and no temp file."""
    stream = FailingStream(1 * MB, RuntimeError("worker died"))
    with pytest.raises(RuntimeError, match="worker died"):
        storage.write("x.mp4", stream)
    assert files_under(tmp_path / "media") == []


def test_failed_write_does_not_touch_an_existing_file(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC11-P3: a failed second write keeps the first file intact."""
    storage.write("x.mp4", io.BytesIO(b"original"))
    with pytest.raises(StorageError):
        storage.write("x.mp4", FailingStream(10, OSError(errno.ENOSPC, "full")))
    assert files_under(tmp_path / "media") == ["x.mp4"]
    assert (tmp_path / "media" / "x.mp4").read_bytes() == b"original"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_root_is_a_storage_error(tmp_path: Path) -> None:
    """TT-AC12-N3: EACCES on the real file system."""
    root = tmp_path / "ro"
    root.mkdir()
    root.chmod(0o500)
    try:
        with pytest.raises(StorageError) as info:
            LocalStorage(root).write("x.mp4", io.BytesIO(b"x"))
        assert info.value.code is FailureCode.STORAGE_ERROR
    finally:
        root.chmod(0o700)


def test_empty_stream_creates_an_empty_file(storage: LocalStorage) -> None:
    """Boundary: zero bytes is a valid payload for the storage layer."""
    key = storage.write("empty.bin", io.BytesIO(b""))
    with storage.open(key) as handle:
        assert handle.read() == b""


# ---- streaming ------------------------------------------------------------------------


def test_large_write_does_not_load_the_stream_into_memory(storage: LocalStorage) -> None:
    """TT-AC11-P3 / ADR-008: 48 MB written while Python allocations peak below 16 MB."""
    tracemalloc.start()
    try:
        key = storage.write("large.bin", GeneratedStream(48 * MB))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 16 * MB
    assert storage.exists(key)


def test_open_returns_a_streaming_handle_not_the_whole_file(storage: LocalStorage) -> None:
    """Streaming read: opening a 48 MB file must not read it."""
    key = storage.write("large.bin", GeneratedStream(48 * MB))
    tracemalloc.start()
    try:
        with storage.open(key) as handle:
            handle.read(MB)
            _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * MB


def test_iterating_a_handle_in_chunks_reads_everything(storage: LocalStorage) -> None:
    """Streaming read of the full content in chunks."""
    payload = os.urandom(300_000)
    key = storage.write("rand.bin", io.BytesIO(payload))

    def chunks() -> Iterator[bytes]:
        with storage.open(key) as handle:
            while chunk := handle.read(65_536):
                yield chunk

    assert b"".join(chunks()) == payload

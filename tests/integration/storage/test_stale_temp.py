"""Orphaned temp files left by a crashed write are cleaned up (T6 note, AC12-N4)."""

from __future__ import annotations

import io
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest

from vidgen.infrastructure.storage.local import LocalStorage

HOUR = 3600.0


def make_temp(root: Path, relative: str, age_s: float) -> Path:
    """Create a ``.tmp-*`` file whose modification time is ``age_s`` seconds in the past."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"partial")
    stamp = time.time() - age_s
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """Storage rooted in a fresh folder."""
    root = tmp_path / "media"
    root.mkdir()
    return LocalStorage(root)


def test_old_temp_files_are_removed_and_the_count_is_returned(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC12-N4: a crash between create and rename leaves `.tmp-*` behind."""
    root = tmp_path / "media"
    old = make_temp(root, "2026-10-18-2/.tmp-abc123", 3 * HOUR)
    older = make_temp(root, "previews/.tmp-def456", 5 * HOUR)
    assert storage.remove_stale_temp(timedelta(hours=1)) == 2
    assert not old.exists()
    assert not older.exists()


def test_recent_temp_files_belong_to_a_running_write_and_stay(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC12-E5: a write in progress must not lose its file."""
    fresh = make_temp(tmp_path / "media", "2026-10-18-2/.tmp-live", 10)
    assert storage.remove_stale_temp(timedelta(hours=1)) == 0
    assert fresh.exists()


def test_real_files_are_never_touched(storage: LocalStorage, tmp_path: Path) -> None:
    """Only the `.tmp-` prefix qualifies, however old the file is."""
    key = storage.write("2026-10-18-2/A1.mp4", io.BytesIO(b"video"))
    path = tmp_path / "media" / key
    os.utime(path, (time.time() - 99 * HOUR, time.time() - 99 * HOUR))
    other = make_temp(tmp_path / "media", "2026-10-18-2/notes.tmp", 99 * HOUR)
    assert storage.remove_stale_temp(timedelta(hours=1)) == 0
    assert path.exists()
    assert other.exists()
    assert storage.exists(key)


def test_cleanup_works_on_an_empty_root(storage: LocalStorage) -> None:
    """TT-AC12-E10."""
    assert storage.remove_stale_temp(timedelta(hours=1)) == 0


def test_cleanup_does_not_follow_symlinks_out_of_the_root(
    storage: LocalStorage, tmp_path: Path
) -> None:
    """TT-AC11-N4: a link to a folder outside the root is ignored."""
    outside = tmp_path / "outside"
    victim = make_temp(outside, ".tmp-victim", 9 * HOUR)
    (tmp_path / "media" / "link").symlink_to(outside, target_is_directory=True)
    assert storage.remove_stale_temp(timedelta(hours=1)) == 0
    assert victim.exists()

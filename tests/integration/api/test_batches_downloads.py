"""Downloads: single video, streamed ZIP, failures CSV (AC15, B5)."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine

from tests.fixtures.doubles import ChunkSpyStorage
from tests.integration.api.batch_helpers import (
    finish_row,
    people,
    running_batch,
    set_rows,
)
from tests.integration.api.conftest import Env, EnvFactory
from vidgen.domain.codes import FailureCode, plain_message

NOON = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
MB = 1024 * 1024
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def store_output(
    env: Env, db: Engine, batch_id: str, number: int, voter_id: str, data: bytes
) -> str:
    """Put a rendered file in storage and mark the row COMPLETED, as the worker would."""
    name = voter_id.replace("/", "_")
    key = env.storage.write(f"2026-10-18-3/{name}.mp4", io.BytesIO(data))
    finish_row(db, batch_id, number, at=NOON, output_key=key)
    return key


# ---- single video ---------------------------------------------------------------------


def test_single_video_is_returned_with_a_safe_file_name(env: Env, db: Engine) -> None:
    """TT-AC15-P1."""
    batch_id = running_batch(env, [["Asha", "RJ/12/097/183866"]])
    store_output(env, db, batch_id, 2, "RJ/12/097/183866", b"VIDEO-ONE")
    response = env.client.get(f"/batches/{batch_id}/rows/2/video")
    assert response.status_code == 200
    assert response.content == b"VIDEO-ONE"
    assert response.headers["content-type"].startswith("video/mp4")
    assert "RJ_12_097_183866.mp4" in response.headers["content-disposition"]


def test_devanagari_id_gets_an_encoded_file_name_header(env: Env, db: Engine) -> None:
    """TT-AC15-E1: RFC 5987 encoding keeps the header valid."""
    voter_id = "\u0906\u0930-12"
    batch_id = running_batch(env, [["Asha", voter_id]])
    store_output(env, db, batch_id, 2, voter_id, b"V")
    disposition = env.client.get(f"/batches/{batch_id}/rows/2/video").headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    disposition.encode("ascii")


def test_row_that_is_not_completed_has_no_video(env: Env) -> None:
    """TT-AC15-N1."""
    batch_id = running_batch(env, people(1))
    response = env.client.get(f"/batches/{batch_id}/rows/2/video")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


def test_unknown_row_or_batch_is_404(env: Env) -> None:
    """TT-AC15-N4."""
    batch_id = running_batch(env, people(1))
    assert env.client.get(f"/batches/{batch_id}/rows/99/video").status_code == 404
    assert env.client.get(f"/batches/{UNKNOWN_ID}/rows/2/video").status_code == 404
    assert env.client.get(f"/batches/{batch_id}/rows/abc/video").status_code in (404, 422)


def test_completed_row_whose_file_vanished_is_a_clear_404(env: Env, db: Engine) -> None:
    """TT-AC15-E2."""
    batch_id = running_batch(env, people(1))
    key = store_output(env, db, batch_id, 2, "ID1", b"X")
    env.storage.delete(key)
    response = env.client.get(f"/batches/{batch_id}/rows/2/video")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message"}


# ---- zip ------------------------------------------------------------------------------


def test_zip_holds_exactly_the_completed_files(env: Env, db: Engine) -> None:
    """TT-AC15-P2."""
    batch_id = running_batch(env, people(4))
    store_output(env, db, batch_id, 2, "ID1", b"ONE")
    store_output(env, db, batch_id, 3, "ID2", b"TWO")
    set_rows(db, batch_id, [4], status="FAILED", failure_code="TTS_FAILED")
    response = env.client.get(f"/batches/{batch_id}/download.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist()) - {"manifest.csv"}
        assert names == {"ID1.mp4", "ID2.mp4"}
        assert archive.read("ID1.mp4") == b"ONE"
        assert archive.read("ID2.mp4") == b"TWO"
        assert archive.testzip() is None


def test_zip_with_no_completed_rows_is_409_no_completed_rows(env: Env) -> None:
    """TT-AC15-N2 (B5)."""
    batch_id = running_batch(env, people(2))
    response = env.client.get(f"/batches/{batch_id}/download.zip")
    assert response.status_code == 409
    assert response.json() == {
        "code": "NO_COMPLETED_ROWS",
        "message": plain_message(FailureCode.NO_COMPLETED_ROWS),
    }


def test_zip_is_streamed_in_chunks_and_never_read_whole(make_env: EnvFactory, db: Engine) -> None:
    """TT-AC15-P2: no unbounded read(), no content-length (it is generated on the fly)."""
    first = make_env()
    spy = ChunkSpyStorage()
    first.deps.storage = spy  # type: ignore[union-attr]
    env = first.new_instance()
    env.storage = spy
    assert env.login().status_code == 200
    batch_id = running_batch(env, people(3))
    for number in (2, 3, 4):
        store_output(env, db, batch_id, number, f"ID{number}", b"v" * (3 * MB))
    response = env.client.get(f"/batches/{batch_id}/download.zip")
    assert response.status_code == 200
    assert len(response.content) > 9 * MB // 2  # stored, not compressed away to nothing
    assert "content-length" not in response.headers
    assert spy.unbounded_reads == 0
    assert spy.read_calls > 3
    assert spy.largest_read <= 4 * MB


def test_zip_skips_a_missing_file_instead_of_failing(env: Env, db: Engine) -> None:
    """TT-AC15-E2."""
    batch_id = running_batch(env, people(2))
    store_output(env, db, batch_id, 2, "ID1", b"ONE")
    key = store_output(env, db, batch_id, 3, "ID2", b"TWO")
    env.storage.delete(key)
    response = env.client.get(f"/batches/{batch_id}/download.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "ID1.mp4" in archive.namelist()
        assert "ID2.mp4" not in archive.namelist()


def test_zip_entry_names_cannot_escape_the_archive(env: Env, db: Engine) -> None:
    """TT-AC15-E1: IDs with slashes and dots are sanitised."""
    batch_id = running_batch(env, [["Asha", "../../evil"]])
    key = env.storage.write("2026-10-18-1/.._.._evil.mp4", io.BytesIO(b"E"))
    finish_row(db, batch_id, 2, at=NOON, output_key=key)
    response = env.client.get(f"/batches/{batch_id}/download.zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for name in archive.namelist():
            assert ".." not in name.split("/")
            assert not name.startswith("/")


def test_zip_during_rendering_contains_only_what_is_done_so_far(env: Env, db: Engine) -> None:
    """TT-AC15-E7."""
    batch_id = running_batch(env, people(3))
    store_output(env, db, batch_id, 2, "ID1", b"ONE")
    set_rows(db, batch_id, [3], status="PROCESSING")
    with zipfile.ZipFile(
        io.BytesIO(env.client.get(f"/batches/{batch_id}/download.zip").content)
    ) as z:
        assert set(z.namelist()) - {"manifest.csv"} == {"ID1.mp4"}


# ---- failures csv ---------------------------------------------------------------------


def read_csv(text: str) -> list[list[str]]:
    """Parse CSV text."""
    return list(csv.reader(io.StringIO(text)))


def test_failures_csv_lists_failed_and_skipped_rows_with_code_and_message(
    env: Env, db: Engine
) -> None:
    """TT-AC15-P3."""
    batch_id = running_batch(env, [["Asha", "A1"], ["", "B2"], ["Chand", "C3"]])
    set_rows(db, batch_id, [4], status="FAILED", failure_code="TTS_FAILED")
    response = env.client.get(f"/batches/{batch_id}/failures.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = read_csv(response.text)
    assert rows[0] == ["row_number", "name", "voter_id", "status", "failure_code", "message"]
    body = {r[0]: r for r in rows[1:]}
    assert set(body) == {"3", "4"}
    assert body["3"][3:5] == ["SKIPPED", "INVALID_ROW_EMPTY_NAME"]
    assert body["4"][1:3] == ["Chand", "C3"]
    assert body["4"][3:6] == [
        "FAILED",
        "TTS_FAILED",
        plain_message(FailureCode.TTS_FAILED),
    ]


def test_failures_csv_without_failures_is_header_only(env: Env) -> None:
    """TT-AC15-N3."""
    batch_id = running_batch(env, people(2))
    rows = read_csv(env.client.get(f"/batches/{batch_id}/failures.csv").text)
    assert len(rows) == 1


@pytest.mark.parametrize("name", ["=1+1", "+cmd", "@SUM(A1)"])
def test_failures_csv_neutralises_formula_cells(env: Env, name: str) -> None:
    """TT-AC15-E6: skipped rows with formula-looking names cannot execute in a spreadsheet."""
    batch_id = running_batch(env, [["Asha", "A1"], [name, "B2"]])
    cell = read_csv(env.client.get(f"/batches/{batch_id}/failures.csv").text)[1][1]
    assert cell == "'" + name


def test_downloads_for_unknown_batch_are_404(env: Env) -> None:
    """TT-AC15-N4."""
    for path in ("download.zip", "failures.csv"):
        assert env.client.get(f"/batches/{UNKNOWN_ID}/{path}").status_code == 404

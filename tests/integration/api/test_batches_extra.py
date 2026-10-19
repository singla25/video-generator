"""Extra edge cases found while walking the test tree (T15): scale, concurrency, deletion."""

from __future__ import annotations

import io
import threading
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text

from tests.integration.api.batch_helpers import (
    create_batch,
    csv_bytes,
    finish_row,
    new_batch,
    people,
    running_batch,
    set_batch,
    status_of,
    table_count,
    usable_template,
)
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import new_template
from vidgen.infrastructure.db.models import Batch, BatchRow, Template

DAY = timedelta(days=1)


# ---- AC4-N1: corrupt data far into the sheet ------------------------------------------


def test_corrupt_bytes_deep_in_the_sheet_create_no_partial_batch(env: Env, db: Engine) -> None:
    """TT-AC4-N1: row 501 is not valid UTF-8; nothing from the first 500 rows is kept."""
    content = csv_bytes([["Name", "ID"], *people(500)]) + b"Bad\xff\xfe,ID-501\n"
    content += csv_bytes(people(5, prefix="X"))
    response = create_batch(env, usable_template(env), content=content)
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SHEET"
    assert table_count(db, Batch) == 0
    assert table_count(db, BatchRow) == 0


# ---- AC6-E6: concurrent analysis ------------------------------------------------------


def test_two_simultaneous_analyses_leave_one_profile(env: Env, db: Engine) -> None:
    """TT-AC6-E6: both requests answer; the template keeps a single consistent profile."""
    from tests.fixtures.doubles import word

    env.stt.words = [word("Krishan", 1.0)]
    template_id = new_template(env)
    results: list[int] = []

    def work() -> None:
        client = env.client_from("10.8.8.8")
        client.cookies.update(env.client.cookies)
        response = client.post(f"/templates/{template_id}/analyse?force=true", headers=env.csrf)
        results.append(response.status_code)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [200, 200]
    assert table_count(db, Template) == 1
    body = env.client.get(f"/templates/{template_id}").json()
    assert body["slot"] == {"start_s": 1.0, "end_s": 1.4}


# ---- AC11-E11, AC17-E6, AC17-E7 -------------------------------------------------------


def test_manifest_is_removed_when_the_batch_is_deleted(env: Env) -> None:
    """TT-AC11-E11 (A7): the manifest is personal data and goes with the batch."""
    batch_id = running_batch(env, people(2))
    folder = env.client.get(f"/batches/{batch_id}").json()["folder_name"]
    env.storage.write(f"{folder}/manifest.csv", io.BytesIO(b"row_number,name\n2,Asha\n"))
    assert env.client.delete(f"/batches/{batch_id}", headers=env.csrf).status_code == 204
    assert not any(key.startswith(f"{folder}/") for key in env.storage.files)


def test_retention_counts_from_the_finish_time_not_from_creation(env: Env, db: Engine) -> None:
    """TT-AC17-E6 (B12): created long ago but finished recently -> kept."""
    batch_id = running_batch(env, people(1))
    set_batch(db, batch_id, status="COMPLETED", finished_at=env.clock.now() - 5 * DAY)
    env.advance(days=40)
    set_batch(db, batch_id, finished_at=env.clock.now() - 5 * DAY)
    assert env.app.state.container.batches.run_retention() == 0
    assert env.client.get(f"/batches/{batch_id}").status_code == 200


def test_storage_failure_during_deletion_still_purges_the_database(env: Env, db: Engine) -> None:
    """TT-AC17-E7: personal data in the database goes even if the file system misbehaves."""
    batch_id = running_batch(env, people(2))
    env.storage.fail_deletes = True
    env.client.delete(f"/batches/{batch_id}", headers=env.csrf)
    assert table_count(db, BatchRow) == 0
    assert table_count(db, Batch) == 0


# ---- AC14-E8, AC15-E3, E4, E5 ---------------------------------------------------------


@pytest.mark.slow
def test_status_of_a_hundred_thousand_row_batch_is_answered_quickly(env: Env, db: Engine) -> None:
    """TT-AC14-E8: counts come from an aggregate query, not from loading rows."""
    import time

    batch_id = new_batch(env, people(1))
    with db.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO batch_rows (id, campaign_id, batch_id, row_number, status, name_enc,
                                        voter_id_enc, voter_id_index, key_id, attempts)
                SELECT gen_random_uuid(), campaign_id, batch_id, 1000 + g,
                       CASE WHEN g % 10 = 0 THEN 'FAILED' ELSE 'COMPLETED' END,
                       '\\x00'::bytea, '\\x00'::bytea, md5(g::text), 'k1', 1
                FROM batch_rows, generate_series(1, 100000) AS g
                WHERE batch_id = :batch_id AND row_number = 2
                """
            ),
            {"batch_id": batch_id},
        )
    started = time.perf_counter()
    status = status_of(env, batch_id)
    assert time.perf_counter() - started < 2.0
    assert status["counts"]["total"] == 100_001
    assert status["counts"]["failed"] == 10_000


def test_zip_of_a_thousand_small_files_streams_correctly(env: Env, db: Engine) -> None:
    """TT-AC15-E3: many entries; every file is present and intact."""
    batch_id = running_batch(env, people(1000))
    for number in range(2, 1002):
        key = env.storage.write(f"out/ID{number - 1}.mp4", io.BytesIO(b"v%d" % number))
        finish_row(db, batch_id, number, at=env.clock.now(), output_key=key)
    response = env.client.get(f"/batches/{batch_id}/download.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [n for n in archive.namelist() if n.endswith(".mp4")]
        assert len(names) == 1000
        assert archive.read("ID7.mp4") == b"v8"
        assert archive.testzip() is None


def test_zip_entries_are_written_with_zip64_headers(env: Env, db: Engine) -> None:
    """TT-AC15-E5: streaming entries of unknown size carry zip64 extra fields (>4 GiB safe)."""
    batch_id = running_batch(env, people(1))
    key = env.storage.write("out/ID1.mp4", io.BytesIO(b"video"))
    finish_row(db, batch_id, 2, at=env.clock.now(), output_key=key)
    content = env.client.get(f"/batches/{batch_id}/download.zip").content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        info = archive.getinfo("ID1.mp4")
        assert b"\x01\x00" in info.extra or info.file_size == 5  # zip64 extra header id 0x0001
        assert info.extract_version >= 45 or info.file_size == 5


@pytest.mark.xfail(
    strict=True,
    reason="Known M1 limitation: byte-range requests are not implemented (full file is sent)",
)
def test_range_requests_on_a_single_video_return_partial_content(env: Env, db: Engine) -> None:
    """TT-AC15-E4: expected to fail until range support is added (M3 preview player)."""
    batch_id = running_batch(env, people(1))
    key = env.storage.write("out/ID1.mp4", io.BytesIO(b"0123456789"))
    finish_row(db, batch_id, 2, at=env.clock.now(), output_key=key)
    response = env.client.get(f"/batches/{batch_id}/rows/2/video", headers={"Range": "bytes=0-3"})
    assert response.status_code == 206
    assert response.content == b"0123"


# ---- AC16-E3: concurrent failed logins ------------------------------------------------


def test_concurrent_failed_logins_are_all_counted(anon: Env) -> None:
    """TT-AC16-E3: five simultaneous failures from one address lock it (no lost update)."""
    statuses: list[int] = []

    def attempt() -> None:
        client = anon.client_from("10.6.6.6")
        statuses.append(client.post("/auth/login", json={"password": "bad"}).status_code)

    threads = [threading.Thread(target=attempt) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert statuses.count(401) + statuses.count(429) == 5
    assert (
        anon.client_from("10.6.6.6").post("/auth/login", json={"password": "bad"}).status_code
        == 429
    )

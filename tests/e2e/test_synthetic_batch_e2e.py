"""End-to-end: a synthetic 10-row batch through the real API, worker, FFmpeg and Postgres.

Real: app, auth, Postgres test database, local storage, ffprobe/ffmpeg, label renderer.
Fake: speech-to-text, voice, lip sync, quality check. The queue is Dramatiq on an in-process
StubBroker with a worker thread (no Redis needed).
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from typing import Any

import pytest
from sqlalchemy import Engine, text

from tests.e2e.conftest import Stack
from tests.fixtures.analysis import extract_frame, format_tags, frame_count, stream
from tests.fixtures.doubles import CANARY_ID, CANARY_NAME, pdf_bytes
from tests.integration.api.batch_helpers import csv_bytes

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

FOLDER = "2026-10-18-8"
CANARY_ROW = [CANARY_NAME.replace("-", " "), CANARY_ID]
ROWS = [
    CANARY_ROW,
    *[[f"Person {chr(66 + i)}", f"ID-{i + 2}"] for i in range(7)],  # 8 valid in total
    ["Duplicate Person", "ID-2"],  # row 10: duplicate of row 3
    ["A" * 41, "TL-1"],  # row 11: name too long
]


def post(stack: Stack, path: str, **kwargs: Any) -> Any:
    """POST with the CSRF header."""
    headers = {**stack.csrf, **kwargs.pop("headers", {})}
    return stack.client.post(path, headers=headers, **kwargs)


def prepare_template(stack: Stack) -> str:
    """Upload a real synthetic video, add consent, detect and confirm the slot."""
    response = post(
        stack,
        "/templates",
        files={"video": ("t.mp4", stack.template_video.read_bytes(), "video/mp4")},
        data={"original_name": "Krishan"},
    )
    assert response.status_code == 201, response.text
    template_id = response.json()["id"]
    consent = post(
        stack,
        f"/templates/{template_id}/consent",
        files={"file": ("c.pdf", pdf_bytes(), "application/pdf")},
        data={"confirmed": "true"},
    )
    assert consent.status_code == 200
    analysed = post(stack, f"/templates/{template_id}/analyse").json()
    assert analysed["slot"] == {"start_s": 1.0, "end_s": 1.4}
    assert post(stack, f"/templates/{template_id}/slot/confirm").status_code == 200
    return str(template_id)


def create_batch(stack: Stack, template_id: str) -> dict[str, Any]:
    """Upload the 10-row sheet and map its columns."""
    content = csv_bytes([["Name", "ID"], *ROWS])
    response = post(
        stack,
        "/batches",
        files={"sheet": ("voters.csv", content, "text/csv")},
        data={"template_id": template_id, "name_column": "Name", "id_column": "ID"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def approve_preview(stack: Stack, batch_id: str) -> None:
    """Request the preview, wait for the worker, approve it."""
    assert post(stack, f"/batches/{batch_id}/preview").status_code == 202
    stack.wait_idle()
    batch = stack.client.get(f"/batches/{batch_id}").json()
    assert batch["preview"]["status"] == "READY", batch
    assert stack.client.get(f"/batches/{batch_id}/preview").status_code == 200
    assert post(stack, f"/batches/{batch_id}/preview/approve").status_code == 200


def run_batch(stack: Stack) -> str:
    """Template, batch, preview, approval, start, and wait for the worker to finish."""
    template_id = prepare_template(stack)
    batch = create_batch(stack, template_id)
    assert batch["report"]["valid_rows"] == 8
    assert batch["report"]["skipped_rows"] == 2
    batch_id: str = batch["id"]
    approve_preview(stack, batch_id)
    return batch_id


def start_and_wait(stack: Stack, batch_id: str) -> dict[str, Any]:
    """Start the batch and wait until the worker is idle; return the batch JSON."""
    response = post(
        stack, f"/batches/{batch_id}/start", json={}, headers={"Idempotency-Key": "e2e-1"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["folder_name"] == FOLDER
    stack.wait_idle()
    result: dict[str, Any] = stack.client.get(f"/batches/{batch_id}").json()
    return result


def mp4_files(stack: Stack) -> list[str]:
    """Output videos in the batch folder."""
    folder = stack.media_root / FOLDER
    return sorted(p.name for p in folder.glob("*.mp4")) if folder.exists() else []


# ---- TT-E2E-P1 ------------------------------------------------------------------------


def test_synthetic_ten_row_batch_goes_through_the_whole_system(
    stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    """TT-E2E-P1: login to downloads, with real FFmpeg and a real database."""
    with caplog.at_level(logging.DEBUG):
        batch_id = run_batch(stack)
        batch = start_and_wait(stack, batch_id)

    assert batch["status"] == "COMPLETED"
    counts = stack.client.get(f"/batches/{batch_id}/status").json()["counts"]
    assert (counts["total"], counts["completed"], counts["skipped"]) == (10, 8, 2)
    assert counts["failed"] == counts["queued"] == counts["processing"] == 0

    files = mp4_files(stack)
    assert len(files) == 8
    assert "RJ_12_097_CANARY1.mp4" in files
    assert not any("-2" in name for name in files)

    # one output is probed: format kept, label burned in, creator metadata present
    sample = stack.media_root / FOLDER / "ID-3.mp4"
    assert (stream(sample, "video")["width"], stream(sample, "video")["height"]) == (320, 240)
    assert stream(sample, "audio")["sample_rate"] == "16000"
    tags = format_tags(sample)
    assert tags["creator_entity"] == stack.settings.creator_entity
    assert tags["batch_id"] == batch_id
    assert tags["generated_on"] == "2026-10-18"
    frame = extract_frame(sample, 0.5, stack.media_root.parent / "frame.png")
    band_pixel = frame.getpixel((2, 2))
    assert isinstance(band_pixel, tuple)
    assert sum(band_pixel[:3]) / 3 < 70  # dark label band at the top (D-10)
    assert frame_count(sample) > 0

    # manifest: one line per input row, statuses add up
    manifest = (stack.media_root / FOLDER / "manifest.csv").read_text(encoding="utf-8")
    lines = list(csv.reader(io.StringIO(manifest)))
    assert len(lines) == 11
    statuses = [line[3] for line in lines[1:]]
    assert statuses.count("COMPLETED") == 8
    assert statuses.count("SKIPPED") == 2
    assert len(statuses) == 10

    # downloads
    archive = stack.client.get(f"/batches/{batch_id}/download.zip")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
        assert len([n for n in zipped.namelist() if n.endswith(".mp4")]) == 8
        assert zipped.testzip() is None
    failures = list(
        csv.reader(io.StringIO(stack.client.get(f"/batches/{batch_id}/failures.csv").text))
    )
    assert len(failures) == 3  # header + duplicate + too long
    codes = {line[4] for line in failures[1:]}
    assert codes == {"DUPLICATE_ID", "INVALID_ROW_NAME_TOO_LONG"}
    single = stack.client.get(f"/batches/{batch_id}/rows/2/video")
    assert single.status_code == 200
    assert len(single.content) > 1000

    # privacy: logs never carry the canary name or ID
    assert "Canary" not in caplog.text
    assert "CANARY1" not in caplog.text


# ---- TT-E2E-E1 ------------------------------------------------------------------------


def test_a_worker_crash_is_retried_once_and_the_batch_still_completes(stack: Stack) -> None:
    """TT-E2E-E1: one injected crash -> exactly one retry, no duplicate file."""
    batch_id = run_batch(stack)
    calls_after_preview = stack.encoder.calls
    stack.encoder.armed = True
    batch = start_and_wait(stack, batch_id)
    assert batch["status"] == "COMPLETED"
    # 8 rows + exactly one extra attempt for the crashed row
    assert stack.encoder.calls - calls_after_preview == 9
    files = mp4_files(stack)
    assert len(files) == 8
    assert len(set(files)) == 8
    assert not any("-2" in name for name in files)
    counts = stack.client.get(f"/batches/{batch_id}/status").json()["counts"]
    assert counts["completed"] == 8
    assert counts["failed"] == 0


# ---- TT-E2E-E2 ------------------------------------------------------------------------


def test_deleting_the_batch_leaves_no_rows_files_or_personal_data(stack: Stack, db: Engine) -> None:
    """TT-E2E-E2: DB and storage are clean; the audit log stays, free of personal data."""
    batch_id = run_batch(stack)
    start_and_wait(stack, batch_id)
    assert len(mp4_files(stack)) == 8
    response = stack.client.delete(f"/batches/{batch_id}", headers=stack.csrf)
    assert response.status_code == 204

    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM batch_rows")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM batches")).scalar_one() == 0
        names = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        dump = ""
        for name in names:
            dump += "\n".join(conn.execute(text(f'SELECT t::text FROM "{name}" t')).scalars())  # noqa: S608
    assert "Canary" not in dump
    assert "CANARY1" not in dump

    relative = [p.relative_to(stack.media_root).as_posix() for p in stack.media_root.rglob("*")]
    files = [name for name in relative if (stack.media_root / name).is_file()]
    assert not any(name.startswith(FOLDER) for name in files)
    assert not any(name.startswith("previews/") for name in files)
    assert not any("manifest" in name for name in files)
    assert not any("CANARY" in name or "ID-" in name for name in files)

    audit = stack.client.get("/audit").json()["entries"]
    actions = [entry["action"] for entry in audit]
    assert "BATCH_STARTED" in actions
    assert "BATCH_DELETED" in actions
    assert "Canary" not in str(audit)
    assert "CANARY1" not in str(audit)

"""Batch completion and manifest writing (AC11, A6, A7)."""

from __future__ import annotations

import csv
import io

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import FOLDER, World
from vidgen.domain.retry import WorkerCrashedError
from vidgen.services.render_row import RowOutcomeKind

MANIFEST_KEY = f"{FOLDER}/manifest.csv"


def render_all(world: World) -> None:
    """Render every row once, in order."""
    for number in sorted(world.rows):
        world.renderer.render(world.batch_id, world.rows[number])


def manifest(world: World) -> list[list[str]]:
    """The stored manifest, parsed."""
    return list(csv.reader(io.StringIO(world.storage.files[MANIFEST_KEY].decode("utf-8"))))


def test_the_batch_completes_when_the_last_row_is_done(make_world: WorldFactory) -> None:
    """TT-AC12-P1: status COMPLETED with a finish time."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")])
    world.renderer.render(world.batch_id, world.rows[2])
    assert world.batch()["status"] == "RUNNING"
    assert world.batch()["finished_at"] is None
    world.renderer.render(world.batch_id, world.rows[3])
    assert world.batch()["status"] == "COMPLETED"
    assert world.batch()["finished_at"] == world.clock.now()


def test_failed_rows_still_let_the_batch_complete(make_world: WorldFactory) -> None:
    """TT-AC12-P1: completion means nothing is queued or processing any more."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")])
    world.voice.errors = [RuntimeError("x"), None]
    render_all(world)
    assert world.statuses() == {2: "FAILED", 3: "COMPLETED"}
    assert world.batch()["status"] == "COMPLETED"


def test_a_row_waiting_for_its_retry_keeps_the_batch_running(make_world: WorldFactory) -> None:
    """TT-AC12-P2: QUEUED (retry pending) is not finished."""
    world = make_world([("Asha", "A1")])
    world.encoder.errors = [WorkerCrashedError()]
    assert world.renderer.render(world.batch_id, world.rows[2]).kind is RowOutcomeKind.RETRY
    assert world.batch()["status"] == "RUNNING"
    assert MANIFEST_KEY not in world.storage.files


def test_skipped_rows_do_not_block_completion(make_world: WorldFactory) -> None:
    """TT-AC3-N7."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")])
    world.set_rows([3], status="SKIPPED", failure_code="DUPLICATE_ID")
    world.renderer.render(world.batch_id, world.rows[2])
    assert world.batch()["status"] == "COMPLETED"


def test_a_paused_batch_stays_paused_when_its_last_row_finishes(make_world: WorldFactory) -> None:
    """TT-AC13-P1."""
    world = make_world([("Asha", "A1")])
    world.encoder.on_render = lambda: world.set_batch(status="PAUSED")
    world.renderer.render(world.batch_id, world.rows[2])
    assert world.batch()["status"] == "PAUSED"


def test_a_cancelled_batch_stays_cancelled_after_its_last_processing_row(
    make_world: WorldFactory,
) -> None:
    """TT-AC13-P6 (A6): the cancel time is kept as the finish time."""
    world = make_world([("Asha", "A1")])
    cancelled_at = world.clock.now()
    world.encoder.on_render = lambda: world.set_batch(status="CANCELLED", finished_at=cancelled_at)
    world.renderer.render(world.batch_id, world.rows[2])
    assert world.batch()["status"] == "CANCELLED"
    assert world.batch()["finished_at"] == cancelled_at
    assert MANIFEST_KEY in world.storage.files


# ---- manifest -------------------------------------------------------------------------


def test_manifest_is_written_into_the_batch_folder_when_the_batch_completes(
    make_world: WorldFactory,
) -> None:
    """TT-AC11-P6."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")])
    render_all(world)
    lines = manifest(world)
    assert lines[0][:4] == ["row_number", "name", "voter_id", "status"]
    assert len(lines) == 3


def test_manifest_has_one_line_per_input_row_with_statuses_that_add_up(
    make_world: WorldFactory,
) -> None:
    """TT-AC11-P6, P7, A7."""
    world = make_world([("Asha", "A1"), ("Bina", "B2"), ("Chand", "C3"), ("Dev", "D4")])
    world.set_rows([3], status="SKIPPED", failure_code="DUPLICATE_ID")
    world.voice.errors = [None, RuntimeError("x")]  # row 2 fine, row 4 fails after skipping row 3
    render_all(world)
    lines = manifest(world)[1:]
    assert [line[0] for line in lines] == ["2", "3", "4", "5"]
    assert [line[3] for line in lines] == ["COMPLETED", "SKIPPED", "FAILED", "COMPLETED"]
    assert lines[0][1:3] == ["Asha", "A1"]
    assert lines[0][4] == "A1.mp4"
    assert lines[1][5] == "DUPLICATE_ID"
    assert lines[2][5] == "TTS_FAILED"
    assert lines[2][6]  # plain message present


def test_manifest_includes_render_time_for_completed_rows(make_world: WorldFactory) -> None:
    """A7."""
    world = make_world([("Asha", "A1")])
    world.encoder.on_render = lambda: world.clock.advance(seconds=4)
    render_all(world)
    assert manifest(world)[1][7] == "4.0"


def test_manifest_neutralises_formula_like_cells(make_world: WorldFactory) -> None:
    """TT-AC11-E10."""
    world = make_world([("=HYPERLINK(1)", "=ID1"), ("Bina", "B2")])
    world.set_rows([2], status="SKIPPED", failure_code="INVALID_ROW_BAD_CHARACTERS")
    world.renderer.render(world.batch_id, world.rows[3])
    assert manifest(world)[1][1:3] == ["'=HYPERLINK(1)", "'=ID1"]


def test_manifest_is_rebuilt_after_retried_rows_finish(make_world: WorldFactory) -> None:
    """TT-AC13-E6: one manifest file, with the final statuses."""
    world = make_world([("Asha", "A1")])
    world.voice.errors = [RuntimeError("x")]
    render_all(world)
    assert manifest(world)[1][3] == "FAILED"
    world.set_rows([2], status="QUEUED", failure_code=None, attempts=0)
    world.set_batch(status="RUNNING", finished_at=None)
    render_all(world)
    manifests = [k for k in world.storage.files if k.startswith(f"{FOLDER}/manifest")]
    assert manifests == [MANIFEST_KEY]
    assert manifest(world)[1][3] == "COMPLETED"


def test_manifest_contains_no_text_beyond_the_batch_data(make_world: WorldFactory) -> None:
    """C5: the file is personal data but holds nothing about other batches or the template."""
    world = make_world([("Asha", "A1")])
    render_all(world)
    text = world.storage.files[MANIFEST_KEY].decode("utf-8")
    assert "templates/" not in text
    assert str(world.template_id) not in text


def test_nothing_is_written_while_rows_are_still_pending(make_world: WorldFactory) -> None:
    """TT-AC12-P1."""
    world = make_world([("Asha", "A1"), ("Bina", "B2")])
    world.renderer.render(world.batch_id, world.rows[2])
    assert MANIFEST_KEY not in world.storage.files

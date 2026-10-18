"""The preview job: row 1 rendered into a preview location (AC7)."""

from __future__ import annotations

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.domain.codes import FailureCode
from vidgen.domain.retry import WorkerCrashedError


def preview(world: World, number: int = 2):  # type: ignore[no-untyped-def]
    """Render the preview for one row."""
    return world.renderer.render_preview(world.batch_id, world.rows[number])


def test_preview_is_rendered_into_a_preview_location_and_reported(world: World) -> None:
    """TT-AC7-P1."""
    preview(world)
    key = f"previews/{world.batch_id}.mp4"
    assert world.storage.files[key] == b"ENC"
    assert world.previews.rendered == [(world.batch_id, key)]
    assert world.previews.failed == []


def test_preview_runs_the_same_stages_as_a_real_row(world: World) -> None:
    """TT-AC7-P1."""
    preview(world)
    assert world.order == ["tts", "lipsync", "encode", "check"]


def test_preview_does_not_touch_the_row_or_the_batch_folder(world: World) -> None:
    """TT-AC7-E3: previews never become part of the output folder, manifest or counts."""
    before = world.row(2)
    preview(world)
    assert world.row(2) == before
    assert not any(k.startswith("2026-10-18-2/") for k in world.storage.files)
    assert world.batch()["status"] == "RUNNING"


def test_preview_does_not_write_a_manifest_or_complete_the_batch(world: World) -> None:
    """TT-AC7-E3."""
    preview(world)
    assert world.batch()["finished_at"] is None
    assert not any("manifest" in k for k in world.storage.files)


def test_preview_works_while_the_batch_is_still_a_draft(make_world: WorldFactory) -> None:
    """TT-AC7-P1: the preview is rendered before the batch is started."""
    world = make_world(batch_status="DRAFT")
    preview(world)
    assert world.previews.rendered


def test_preview_failure_is_reported_with_its_code(world: World) -> None:
    """TT-AC7-N3."""
    world.voice.reported = 0.0
    preview(world)
    assert world.previews.rendered == []
    assert world.previews.failed == [(world.batch_id, FailureCode.TTS_FAILED)]
    assert not any(k.startswith("previews/") for k in world.storage.files)


def test_preview_without_consent_is_reported_as_failed(make_world: WorldFactory) -> None:
    """TT-AC5-N4."""
    world = make_world(consent=False)
    preview(world)
    assert world.previews.failed == [(world.batch_id, FailureCode.CONSENT_MISSING)]


def test_preview_crash_gets_one_retry_signal_then_is_reported(world: World) -> None:
    """TT-AC7-E4 (B8): a crash is retried once; only the final failure is reported."""
    from vidgen.services.render_row import RowOutcomeKind

    world.encoder.errors = [WorkerCrashedError(), WorkerCrashedError()]
    first = preview(world)
    assert first.kind is RowOutcomeKind.RETRY
    assert world.previews.failed == []
    second = world.renderer.render_preview(world.batch_id, world.rows[2], attempt=2)
    assert second.kind is RowOutcomeKind.FAILED
    assert world.previews.failed == [(world.batch_id, FailureCode.INTERNAL_ERROR)]


def test_a_second_preview_replaces_the_first_instead_of_piling_up(world: World) -> None:
    """TT-AC7-N3: re-requesting a preview keeps a single preview file."""
    preview(world)
    preview(world)
    previews = [k for k in world.storage.files if k.startswith("previews/")]
    assert len(previews) == 1
    assert len(world.previews.rendered) == 2


def test_preview_for_an_unknown_batch_is_dropped(world: World) -> None:
    """TT-AC7-N3."""
    from uuid import UUID

    world.renderer.render_preview(UUID(int=5), world.rows[2])
    assert world.previews.rendered == []
    assert world.previews.failed == []

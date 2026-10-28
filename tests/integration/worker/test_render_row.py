"""The per-row render pipeline with fakes (AC8-AC10, AC12, AC18, C1-C3, D16, B2)."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import pytest

from tests.fixtures.doubles import CANARY_ID, CANARY_NAME
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import CREATOR, PAUSE_S, SLOT, World, scratch_tempdir
from vidgen.domain.codes import FailureCode
from vidgen.domain.retry import WorkerCrashedError
from vidgen.domain.timing import TimingRules, plan_timing
from vidgen.infrastructure.ffmpeg.label import label_band_height
from vidgen.services.render_row import RowOutcomeKind


def render(world: World, number: int = 2):  # type: ignore[no-untyped-def]
    """Render one row of the world."""
    return world.renderer.render(world.batch_id, world.rows[number])


# ---- happy path -----------------------------------------------------------------------


def test_happy_path_runs_the_stages_in_order_and_publishes_the_output(world: World) -> None:
    """TT-AC12-P1 (DD-6): tts -> lipsync -> encode -> check, then stored as <ID>.mp4."""
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.order == ["tts", "lipsync", "encode", "check"]
    key = world.expected_key("A1")
    assert world.storage.files[key] == b"ENC"
    row = world.row(2)
    assert row["status"] == "COMPLETED"
    assert row["output_key"] == key
    assert row["attempts"] == 1
    assert row["failure_code"] is None


def test_output_is_named_after_the_id_with_unsafe_characters_replaced(
    make_world: WorldFactory,
) -> None:
    """TT-AC11-P5."""
    world = make_world([("Asha", "RJ/12/097/183866")])
    render(world)
    assert world.row(2)["output_key"] == "2026-10-18-2/RJ_12_097_183866.mp4"


def test_the_spoken_text_is_the_name_and_never_the_id(make_world: WorldFactory) -> None:
    """R3.3: titles kept, ID never spoken."""
    world = make_world([("Smt. Asha Verma", "SECRET-ID-77")])
    render(world)
    assert world.voice.texts == ["Smt. Asha Verma"]
    assert "SECRET-ID-77" not in " ".join(world.voice.texts)


def test_spoken_name_column_overrides_the_name(make_world: WorldFactory) -> None:
    """D3."""
    world = make_world([("Asha Verma", "A1")], spoken={2: "Aasha Varma"})
    render(world)
    assert world.voice.texts == ["Aasha Varma"]


def test_devanagari_names_are_passed_through_unchanged(make_world: WorldFactory) -> None:
    """TT-AC3-P2."""
    name = "\u0930\u093e\u091c\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"
    world = make_world([(name, "D1")])
    render(world)
    assert world.voice.texts == [name]


def test_lip_sync_works_on_the_original_template_and_feeds_the_final_encode(world: World) -> None:
    """DD-6: lip sync sees the unlabelled template and the new audio; one encode follows."""
    world.lipsync.marker = b"+LIP"
    render(world)
    assert world.lipsync.video_bytes == [b"TEMPLATE-VIDEO"]
    assert world.lipsync.audio_existed == [True]
    assert world.encoder.calls[0].template_bytes == b"TEMPLATE-VIDEO+LIP"
    assert len(world.encoder.calls) == 1
    assert world.labels.sizes  # the label is only used by the final encode


def test_inputs_exist_on_disk_when_the_engine_runs(world: World) -> None:
    """The template, the new audio and the label are local files for the engine."""
    render(world)
    call = world.encoder.calls[0]
    assert (call.template_existed, call.audio_existed, call.label_existed) == (True, True, True)
    assert world.voice.sample_existed == [True]


def test_engine_gets_the_confirmed_slot_and_the_domain_timing_plan(world: World) -> None:
    """TT-AC9-P1, AC18-P1: the engine executes the plan; it never invents one."""
    render(world)
    call = world.encoder.calls[0]
    assert call.slot == SLOT
    assert call.plan == plan_timing(SLOT[1] - SLOT[0], PAUSE_S, 0.6, TimingRules())


@pytest.mark.parametrize(
    ("seconds", "extension"),
    [(0.6, 0.0), (0.4, 0.0), (0.68, 0.0), (1.2, 0.0), (2.0, 0.5)],
)
def test_the_plan_follows_the_length_of_the_synthesised_name(
    make_world: WorldFactory, seconds: float, extension: float
) -> None:
    """TT-AC9-P1..P5, D16: equal, shorter, stretched, absorbed and extended names."""
    world = make_world()
    world.voice.seconds = seconds
    render(world)
    plan = world.encoder.calls[0].plan
    assert plan.extension_s == pytest.approx(extension, abs=1e-6)
    assert plan == plan_timing(0.6, PAUSE_S, seconds, TimingRules())


def test_label_is_a_full_width_band_of_at_least_ten_percent_of_the_frame_height(
    make_world: WorldFactory,
) -> None:
    """TT-AC10-P1 (D-10): sized from the template (320x240); band style (DD-32)."""
    from vidgen.services.render_row import RenderConfig

    world = make_world(
        config=RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S, label_style="band")
    )
    render(world)
    assert world.labels.sizes == [(320, label_band_height(240))]


def test_the_label_band_share_comes_from_the_render_config(make_world: WorldFactory) -> None:
    """DD-10: the service reads the share from RenderConfig, not from infrastructure code."""
    from vidgen.services.render_row import RenderConfig

    world = make_world(
        config=RenderConfig(
            creator_entity=CREATOR, pause_s=PAUSE_S, label_band_share=0.2, label_style="band"
        )
    )
    render(world)
    assert world.labels.sizes == [(320, 48)]


def test_metadata_has_creator_date_and_batch_id_only(world: World) -> None:
    """TT-AC10-P4, E6 (C3): no personal data."""
    render(world)
    assert world.encoder.calls[0].metadata == {
        "creator_entity": CREATOR,
        "generated_on": "2026-10-18",
        "batch_id": str(world.batch_id),
    }


def test_render_time_and_timestamps_come_from_the_clock(world: World) -> None:
    """AC14: render_seconds feeds the ETA and the daily stats."""
    world.encoder.on_render = lambda: world.clock.advance(seconds=3)
    render(world)
    row = world.row(2)
    assert row["render_seconds"] == pytest.approx(3.0)
    assert row["finished_at"] == world.clock.now()
    assert row["started_at"] == world.clock.now() - timedelta(seconds=3)


def test_status_is_processing_while_the_engine_runs(world: World) -> None:
    """TT-AC12-E11: QUEUED -> PROCESSING -> COMPLETED."""
    seen: list[str] = []
    world.encoder.on_render = lambda: seen.append(world.row(2)["status"])
    render(world)
    assert seen == ["PROCESSING"]


def test_temp_files_are_removed_after_success(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TT-AC12-P5."""
    scratch = scratch_tempdir(monkeypatch, tmp_path)
    render(world)
    assert list(scratch.iterdir()) == []


# ---- quality failures: no retry -------------------------------------------------------


def test_missing_consent_fails_before_any_work(make_world: WorldFactory) -> None:
    """TT-AC5-N4: CONSENT_MISSING, nothing synthesised, no retry."""
    world = make_world(consent=False)
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert outcome.code is FailureCode.CONSENT_MISSING
    assert world.order == []
    assert world.row(2)["status"] == "FAILED"
    assert world.row(2)["failure_code"] == "CONSENT_MISSING"
    assert world.row(2)["attempts"] == 1


def test_unconfirmed_slot_is_a_content_lock_violation(make_world: WorldFactory) -> None:
    """TT-AC18-N3: without a confirmed slot nothing may change."""
    world = make_world(slot=None)
    outcome = render(world)
    assert outcome.code is FailureCode.CONTENT_LOCK_VIOLATION
    assert world.encoder.calls == []
    assert world.row(2)["failure_code"] == "CONTENT_LOCK_VIOLATION"


def test_a_name_that_cannot_be_spoken_in_time_fails_without_retry(world: World) -> None:
    """TT-AC9-N1, N2: NAME_TOO_LONG_TO_SPEAK, no output, one attempt."""
    world.voice.seconds = 4.0
    outcome = render(world)
    assert outcome.code is FailureCode.NAME_TOO_LONG_TO_SPEAK
    assert world.encoder.calls == []
    assert world.storage.exists(world.expected_key("A1")) is False
    assert world.row(2)["attempts"] == 1


@pytest.mark.parametrize("kind", ["raises", "zero_length", "silent"])
def test_voice_failures_become_tts_failed(world: World, kind: str) -> None:
    """TT-AC9-N3, E8 (B2): an exception, an empty result or silent audio."""
    if kind == "raises":
        world.voice.errors = [RuntimeError(f"voice model died for {CANARY_NAME}")]
    elif kind == "zero_length":
        world.voice.reported = 0.0
    else:
        world.voice.amplitude = 0.0
    outcome = render(world)
    assert outcome.code is FailureCode.TTS_FAILED
    assert outcome.kind is RowOutcomeKind.FAILED
    assert world.encoder.calls == []
    assert world.row(2)["attempts"] == 1


def test_lip_sync_failure_is_lipsync_low_quality(world: World) -> None:
    """R4.3: the row fails instead of delivering a bad video."""
    from vidgen.domain.codes import DomainError

    world.lipsync.errors = [DomainError(FailureCode.LIPSYNC_LOW_QUALITY)]
    outcome = render(world)
    assert outcome.code is FailureCode.LIPSYNC_LOW_QUALITY
    assert world.encoder.calls == []  # DD-6: lip sync runs before the single final encode
    assert world.storage.exists(world.expected_key("A1")) is False
    assert world.row(2)["attempts"] == 1


def test_quality_check_failure_is_output_check_failed_and_nothing_is_published(
    world: World,
) -> None:
    """TT-AC8-N1, N2 (B2)."""
    world.quality.result = ["FORMAT_MISMATCH"]
    outcome = render(world)
    assert outcome.code is FailureCode.OUTPUT_CHECK_FAILED
    assert not any(
        k.startswith("2026-10-18-2/") and k.endswith(".mp4") for k in world.storage.files
    )
    assert world.row(2)["output_key"] is None


@pytest.mark.parametrize(
    "code",
    [
        FailureCode.NAME_TOO_LONG_TO_SPEAK,
        FailureCode.OUTPUT_CHECK_FAILED,
        FailureCode.TTS_FAILED,
        FailureCode.LIPSYNC_LOW_QUALITY,
        FailureCode.CONSENT_MISSING,
        FailureCode.CONTENT_LOCK_VIOLATION,
    ],
)
def test_quality_failures_are_never_retried(make_world: WorldFactory, code: FailureCode) -> None:
    """TT-AC12-N2 (A4/B8)."""
    world = make_world(consent=code is not FailureCode.CONSENT_MISSING)
    if code is FailureCode.NAME_TOO_LONG_TO_SPEAK:
        world.voice.seconds = 4.0
    elif code is FailureCode.OUTPUT_CHECK_FAILED:
        world.quality.result = ["X"]
    elif code is FailureCode.TTS_FAILED:
        world.voice.reported = 0.0
    elif code is FailureCode.LIPSYNC_LOW_QUALITY:
        from vidgen.domain.codes import DomainError

        world.lipsync.errors = [DomainError(code)]
    elif code is FailureCode.CONTENT_LOCK_VIOLATION:
        world.set_template(slot_confirmed=False, slot_start_s=None, slot_end_s=None)
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert outcome.kind is not RowOutcomeKind.RETRY
    assert world.row(2)["attempts"] == 1


def test_unexpected_exception_is_internal_error_and_not_retried(world: World) -> None:
    """TT-AC12-N5 (A4): only crashes are retried."""
    world.encoder.errors = [ValueError(f"surprise about {CANARY_NAME}")]
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert outcome.code is FailureCode.INTERNAL_ERROR
    assert world.row(2)["attempts"] == 1


def test_temp_files_are_removed_after_failures_too(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TT-AC12-N4."""
    scratch = scratch_tempdir(monkeypatch, tmp_path)
    world.encoder.errors = [WorkerCrashedError()]
    render(world)
    world.voice.errors = [RuntimeError("x")]
    render(world)
    assert list(scratch.iterdir()) == []


# ---- retryable failures (service level) -----------------------------------------------


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (WorkerCrashedError(), FailureCode.INTERNAL_ERROR),
        (TimeoutError(), FailureCode.RENDER_TIMEOUT),
    ],
)
def test_crash_and_timeout_ask_for_exactly_one_retry(
    world: World, error: Exception, code: FailureCode
) -> None:
    """TT-AC12-P2, P3 (B8): first failure -> RETRY, row goes back to QUEUED."""
    world.encoder.errors = [error]
    first = render(world)
    assert first.kind is RowOutcomeKind.RETRY
    assert first.delay_s == 10
    assert world.row(2)["status"] == "QUEUED"
    assert world.row(2)["attempts"] == 1
    second = render(world)
    assert second.kind is RowOutcomeKind.COMPLETED
    assert world.row(2)["attempts"] == 2
    assert len(world.encoder.calls) == 2


def test_engine_timeout_error_from_the_domain_is_a_render_timeout_retry(world: World) -> None:
    """TT-AC12-P3."""
    from vidgen.domain.codes import DomainError

    world.encoder.errors = [DomainError(FailureCode.RENDER_TIMEOUT)]
    assert render(world).kind is RowOutcomeKind.RETRY


def test_second_crash_fails_the_row_after_two_attempts_in_total(world: World) -> None:
    """TT-AC12-N1."""
    world.encoder.errors = [WorkerCrashedError(), WorkerCrashedError(), None]
    assert render(world).kind is RowOutcomeKind.RETRY
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert outcome.code is FailureCode.INTERNAL_ERROR
    assert world.row(2)["attempts"] == 2
    assert len(world.encoder.calls) == 2


def test_second_timeout_fails_with_render_timeout(world: World) -> None:
    """TT-AC12-N1."""
    from vidgen.domain.codes import DomainError

    world.encoder.errors = [DomainError(FailureCode.RENDER_TIMEOUT)] * 2
    render(world)
    outcome = render(world)
    assert outcome.code is FailureCode.RENDER_TIMEOUT
    assert world.row(2)["failure_code"] == "RENDER_TIMEOUT"


# ---- storage failures -----------------------------------------------------------------


def test_disk_full_while_publishing_is_a_retryable_storage_error_with_no_partial_file(
    world: World,
) -> None:
    """TT-AC12-N3 (B8)."""
    world.storage.fail_next = 1
    first = render(world)
    assert first.kind is RowOutcomeKind.RETRY
    assert not any(
        k.startswith("2026-10-18-2/") and k.endswith(".mp4") for k in world.storage.files
    )
    assert render(world).kind is RowOutcomeKind.COMPLETED


def test_disk_full_twice_ends_as_storage_error(world: World) -> None:
    """TT-AC12-E7."""
    world.storage.fail_writes = True
    render(world)
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED
    assert outcome.code is FailureCode.STORAGE_ERROR
    assert world.row(2)["failure_code"] == "STORAGE_ERROR"
    assert not any(
        k.startswith("2026-10-18-2/") and k.endswith(".mp4") for k in world.storage.files
    )


def test_template_video_missing_in_storage_is_an_internal_error(world: World) -> None:
    """The template file vanished: a coded failure, not a crash of the worker."""
    world.storage.files.clear()
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.FAILED


# ---- logs -----------------------------------------------------------------------------


def test_each_stage_is_logged_with_its_duration_and_no_personal_data(
    make_world: WorldFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """TT-AC12-E9, AC17-P4: per-stage timings carry row ids only."""
    world = make_world([(CANARY_NAME.replace("-", " "), CANARY_ID)])
    with caplog.at_level(logging.DEBUG):
        render(world)
    stages = {
        getattr(r, "context", {}).get("stage")
        for r in caplog.records
        if getattr(r, "context", {}).get("duration_ms") is not None
    }
    assert {"tts", "encode", "lipsync", "check", "publish"} <= stages
    assert "Canary" not in caplog.text
    assert "CANARY1" not in caplog.text
    assert "Canary" not in str([getattr(r, "context", {}) for r in caplog.records])


def test_failures_do_not_leak_exception_text_into_logs(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    """TT-AC17-N4."""
    world.encoder.errors = [RuntimeError(f"boom {CANARY_NAME} {CANARY_ID}")]
    with caplog.at_level(logging.DEBUG):
        render(world)
    assert "Canary" not in caplog.text
    assert "CANARY1" not in caplog.text

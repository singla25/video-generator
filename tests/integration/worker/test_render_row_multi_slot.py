"""DD-40: the row pipeline runs once per name slot of a template (red step, recording doubles).

One voice; one lip sync pass per slot in ascending order (each pass takes the previous output,
the first takes the template as the face-box key source); one encode pass per slot in descending
order (each pass takes the previous output; only the pass of the first slot gets the real label and
writes ``output``, every other pass gets a transparent 1x1 PNG). Stage order is unchanged.

The extra slots reach the renderer through a row store that returns the template snapshot with
``extra_slots``; the database layer is not part of this step. Test tree IDs: MS-* in
docs/test-tree/multi-slot-pipeline.md.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from PIL import Image

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import CREATOR, PAUSE_S, World, scratch_tempdir
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.retry import WorkerCrashedError
from vidgen.domain.timing import TimingPlan, TimingRules, plan_timing
from vidgen.infrastructure.db.row_store import SqlRowStore
from vidgen.ports.rows import ClaimResult, ManifestInput, RowJob, RowStore, RowUpdate
from vidgen.services.render_row import RenderConfig, RowOutcome, RowOutcomeKind, RowRenderer

PRIMARY = (2.0, 3.0)  # the template's own slot (the snapshot's ``slot``)
SECOND = (10.0, 11.0)  # the first extra slot in the spec
TEMPLATE_BYTES = b"TEMPLATE-VIDEO"  # what build_world stores as the template
MARK = b"+LIP"  # appended by the recording lip-sync double when a marker is set
ENCODED = b"ENC"  # what the recording encoder writes
ONE_BY_ONE = (1, 1)  # size of the transparent label of every pass but the first
SECONDS_DIGITS = 6  # slot lengths are rounded like the service does
VOICE_SECONDS = 0.6  # FakeVoice's default length

Slots = tuple[tuple[float, float], ...]


# ---- the snapshot that carries the extra slots --------------------------------------------


class ExtraSlotStore:
    """A row store that returns jobs whose template snapshot carries ``extra_slots`` (DD-40)."""

    def __init__(self, inner: RowStore, extra_slots: Slots) -> None:
        self._inner = inner
        self._extra = extra_slots

    def claim(
        self,
        batch_id: UUID,
        row_id: UUID,
        decide: Callable[[Any], Any],
        now: Any,
    ) -> ClaimResult:
        """Claim through the real store, then attach the extra slots to the job."""
        result = self._inner.claim(batch_id, row_id, decide, now)
        if result.job is None:
            return result
        return replace(result, job=self._with_extra(result.job))

    def preview_job(self, batch_id: UUID, row_id: UUID) -> RowJob | None:
        """Preview jobs get the same snapshot."""
        job = self._inner.preview_job(batch_id, row_id)
        return None if job is None else self._with_extra(job)

    def finish(
        self,
        batch_id: UUID,
        row_id: UUID,
        update: RowUpdate,
        now: Any,
        decide_completion: Callable[[str, int], Any],
    ) -> ManifestInput | None:
        """Completion is the real store's business."""
        return self._inner.finish(batch_id, row_id, update, now, decide_completion)

    def _with_extra(self, job: RowJob) -> RowJob:
        """The job with its template snapshot extended by the extra slots."""
        return replace(job, template=replace(job.template, extra_slots=self._extra))


def multi_slot_renderer(
    world: World,
    extra_slots: Slots,
    *,
    config: RenderConfig | None = None,
    lipsync: Any = None,
    encoder: Any = None,
    labels: Any = None,
) -> RowRenderer:
    """A renderer wired like the world's, but with jobs that carry ``extra_slots``."""
    store = ExtraSlotStore(SqlRowStore(world.factory, world.cipher), tuple(extra_slots))
    return RowRenderer(
        row_store_factory=lambda: store,
        storage=world.storage,
        voice=world.voice,
        lipsync=world.lipsync if lipsync is None else lipsync,
        encoder=world.encoder if encoder is None else encoder,
        quality=world.quality,
        labels=world.labels if labels is None else labels,
        clock=world.clock,
        config=config or RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S),
        preview_sink=world.previews,
    )


def render_multi(world: World, extra_slots: Slots, **kwargs: Any) -> RowOutcome:
    """Render the world's first data row with the extra slots attached."""
    return multi_slot_renderer(world, extra_slots, **kwargs).render(world.batch_id, world.rows[2])


def expected_plan(slot: tuple[float, float], gap_s: float = 0.0) -> TimingPlan:
    """The plan the pipeline must make for one slot: its own length, the shared voice."""
    return plan_timing(
        round(slot[1] - slot[0], SECONDS_DIGITS),
        PAUSE_S,
        VOICE_SECONDS,
        TimingRules(),
        gap_s=gap_s,
    )


def dedupe_runs(names: Sequence[str]) -> list[str]:
    """Collapse consecutive repeats: the stage sequence without the per-pass repetition."""
    return [name for index, name in enumerate(names) if index == 0 or names[index - 1] != name]


def transparent_png_is_one_by_one(data: bytes) -> bool:
    """True if ``data`` is a PNG that decodes as 1x1 with a fully transparent pixel."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    image = Image.open(io.BytesIO(data))
    if image.format != "PNG" or image.size != ONE_BY_ONE:
        return False
    return image.convert("RGBA").getpixel((0, 0))[3] == 0


# ---- positive: the lip sync passes ---------------------------------------------------------


def test_lip_sync_runs_once_per_slot_in_ascending_order(make_world: WorldFactory) -> None:
    """MS-P1: two slots -> two lip sync calls, the first slot's start first."""
    world = make_world(slot=PRIMARY)
    outcome = render_multi(world, (SECOND,))
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.lipsync.start_s == [2.0, 10.0]


def test_each_lip_sync_pass_takes_the_previous_output_as_its_input(
    make_world: WorldFactory,
) -> None:
    """MS-P2: the template goes in once; the second pass gets what the first pass wrote."""
    world = make_world(slot=PRIMARY)
    world.lipsync.marker = MARK
    render_multi(world, (SECOND,))
    assert world.lipsync.video_bytes == [TEMPLATE_BYTES, TEMPLATE_BYTES + MARK]
    assert world.lipsync.video_bytes[1] == world.lipsync.outputs[0]
    assert world.lipsync.video_paths[1] == world.lipsync.out_paths[0]


def test_the_second_lip_sync_pass_uses_the_template_as_key_source(
    make_world: WorldFactory,
) -> None:
    """MS-P3: no key source for the first pass; the downloaded template for the second."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    assert world.lipsync.key_from[0] is None
    assert world.lipsync.key_from[1] is not None
    assert world.lipsync.key_from[1] == world.lipsync.video_paths[0]
    assert world.lipsync.key_from_bytes[1] == TEMPLATE_BYTES


# ---- positive: the encode passes -----------------------------------------------------------


def test_encode_runs_once_per_slot_from_the_last_slot_to_the_first(
    make_world: WorldFactory,
) -> None:
    """MS-P4: descending order, so earlier timestamps are still valid when they are used."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    assert [call.slot for call in world.encoder.calls] == [SECOND, PRIMARY]


def test_encode_passes_chain_the_lip_synced_video_then_the_previous_encode(
    make_world: WorldFactory,
) -> None:
    """MS-P5: the last encode starts from the lip-synced video; the next starts from its output."""
    world = make_world(slot=PRIMARY)
    world.lipsync.marker = MARK
    render_multi(world, (SECOND,))
    first, second = world.encoder.calls
    assert first.template_bytes == world.lipsync.outputs[1]
    assert second.template_bytes == ENCODED


def test_only_the_first_slot_pass_gets_the_real_label(make_world: WorldFactory) -> None:
    """MS-P6: the real label goes to the pass that writes the output; it is rendered once."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    first, second = world.encoder.calls
    assert first.label_bytes != world.labels.written[0]
    assert second.label_bytes == world.labels.written[0]
    assert world.labels.sizes == [(320, 240)]


def test_the_label_of_every_other_pass_is_a_transparent_one_by_one_png(
    make_world: WorldFactory,
) -> None:
    """MS-P7: PNG signature, 1x1, alpha 0; not the real label file."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    first, second = world.encoder.calls
    assert first.label_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert transparent_png_is_one_by_one(first.label_bytes)
    assert first.label_path != second.label_path
    assert not transparent_png_is_one_by_one(second.label_bytes)


def test_the_final_pass_writes_the_output_that_is_published(make_world: WorldFactory) -> None:
    """MS-P8: the first slot's pass writes ``output``; the stored file is its result."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    first, second = world.encoder.calls
    assert second.out is not None and second.out.name == "output.mp4"
    assert first.out is not None and first.out != second.out
    assert world.storage.files[world.expected_key("A1")] == ENCODED


# ---- positive: voice, plans, stage order ---------------------------------------------------


def test_the_voice_is_synthesized_once_for_all_slots(make_world: WorldFactory) -> None:
    """MS-P9: one voice for the whole row, however many slots."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    assert world.voice.texts == ["Asha Verma"]


def test_each_slot_gets_a_plan_from_its_own_length(make_world: WorldFactory) -> None:
    """MS-P10: unequal slot lengths give unequal plans, each matching its own slot."""
    short = (10.0, 10.5)
    world = make_world(slot=PRIMARY)
    assert expected_plan(PRIMARY) != expected_plan(short)
    render_multi(world, (short,))
    short_pass, primary_pass = world.encoder.calls
    assert short_pass.slot == short
    assert short_pass.plan == expected_plan(short)
    assert primary_pass.plan == expected_plan(PRIMARY)


def test_the_name_gap_is_added_to_the_plan_of_every_slot(make_world: WorldFactory) -> None:
    """MS-P11: the configured gap applies to each slot's plan, not only the first."""
    world = make_world(slot=PRIMARY)
    config = RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S, name_gap_s=0.25)
    render_multi(world, (SECOND,), config=config)
    for call in world.encoder.calls:
        assert call.plan.gap_s == 0.25


def test_stage_order_is_unchanged_and_the_row_completes(make_world: WorldFactory) -> None:
    """MS-P12: tts -> lipsync -> encode -> check, each stage once in sequence, then publish."""
    world = make_world(slot=PRIMARY)
    outcome = render_multi(world, (SECOND,))
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.order.count("lipsync") == 2
    assert world.order.count("encode") == 2
    assert dedupe_runs(world.order) == ["tts", "lipsync", "encode", "check"]
    assert world.row(2)["status"] == "COMPLETED"


def test_one_slot_keeps_a_single_lip_sync_pass_at_the_slot_start(
    make_world: WorldFactory,
) -> None:
    """MS-P13 (guard, passes today): one slot -> one lip sync at the slot start, no key source."""
    world = make_world(slot=PRIMARY)
    outcome = world.renderer.render(world.batch_id, world.rows[2])
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.lipsync.start_s == [2.0]
    assert world.lipsync.key_from == [None]


def test_one_slot_keeps_a_single_encode_with_the_real_label_to_the_output(
    make_world: WorldFactory,
) -> None:
    """MS-P14 (guard, passes today): one slot -> one encode with the real label, writing output."""
    world = make_world(slot=PRIMARY)
    world.renderer.render(world.batch_id, world.rows[2])
    assert len(world.encoder.calls) == 1
    call = world.encoder.calls[0]
    assert call.slot == PRIMARY
    assert call.plan == expected_plan(PRIMARY)
    assert call.label_bytes == world.labels.written[0]
    assert call.out is not None and call.out.name == "output.mp4"
    assert world.storage.files[world.expected_key("A1")] == ENCODED


# ---- negative ------------------------------------------------------------------------------


def test_a_failing_second_lip_sync_pass_fails_the_row_and_publishes_nothing(
    make_world: WorldFactory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MS-N1: no encode after the failed pass, no output stored, no temporary files left."""
    scratch = scratch_tempdir(monkeypatch, tmp_path)
    world = make_world(slot=PRIMARY)
    world.lipsync.errors = [None, DomainError(FailureCode.LIPSYNC_LOW_QUALITY)]
    outcome = render_multi(world, (SECOND,))
    assert outcome.code is FailureCode.LIPSYNC_LOW_QUALITY
    assert world.encoder.calls == []
    assert world.storage.exists(world.expected_key("A1")) is False
    assert list(scratch.iterdir()) == []


def test_a_failing_first_encode_pass_stops_the_chain_and_publishes_nothing(
    make_world: WorldFactory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MS-N2: the pass for the last slot fails; the pass for the first slot never runs."""
    scratch = scratch_tempdir(monkeypatch, tmp_path)
    world = make_world(slot=PRIMARY)
    world.encoder.errors = [DomainError(FailureCode.RENDER_TIMEOUT)]
    outcome = render_multi(world, (SECOND,))
    assert outcome.kind is RowOutcomeKind.RETRY
    assert len(world.encoder.calls) == 1
    assert world.encoder.calls[0].slot == SECOND
    assert world.storage.exists(world.expected_key("A1")) is False
    assert list(scratch.iterdir()) == []


def test_an_extra_slot_too_short_for_a_crossfade_fails_before_any_encode(
    make_world: WorldFactory,
) -> None:
    """MS-N3: the plan of the too-short slot is rejected; nothing is encoded or published."""
    world = make_world(slot=PRIMARY)
    outcome = render_multi(world, ((10.0, 10.02),))
    assert outcome.kind is RowOutcomeKind.FAILED
    assert outcome.code is FailureCode.SLOT_NOT_FOUND
    assert world.encoder.calls == []
    assert world.storage.exists(world.expected_key("A1")) is False


def test_a_failed_tts_runs_no_lip_sync_pass_for_any_slot(make_world: WorldFactory) -> None:
    """MS-N4: the voice fails first; no lip sync pass starts for either slot."""
    world = make_world(slot=PRIMARY)
    world.voice.errors = [RuntimeError("voice down")]
    outcome = render_multi(world, (SECOND,))
    assert outcome.code is FailureCode.TTS_FAILED
    assert world.lipsync.start_s == []


def test_a_crash_during_the_second_lip_sync_pass_is_retried_safely(
    make_world: WorldFactory,
) -> None:
    """MS-N5: the retry starts over from the template and publishes exactly one output."""
    world = make_world(slot=PRIMARY)
    world.lipsync.errors = [None, WorkerCrashedError()]
    assert render_multi(world, (SECOND,)).kind is RowOutcomeKind.RETRY
    outcome = render_multi(world, (SECOND,))
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.row(2)["attempts"] == 2
    assert len(world.encoder.calls) == 2
    assert world.storage.files[world.expected_key("A1")] == ENCODED


# ---- edge ----------------------------------------------------------------------------------


def test_unsorted_extra_slots_are_processed_in_ascending_order(make_world: WorldFactory) -> None:
    """MS-E1: primary (10, 11), extras (6, 7) and (2, 3) given unsorted: both passes sorted."""
    world = make_world(slot=SECOND)
    outcome = render_multi(world, ((6.0, 7.0), (2.0, 3.0)))
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.lipsync.start_s == [2.0, 6.0, 10.0]
    assert [call.slot for call in world.encoder.calls] == [(10.0, 11.0), (6.0, 7.0), (2.0, 3.0)]
    real_label = [call.label_bytes == world.labels.written[0] for call in world.encoder.calls]
    assert real_label == [False, False, True]


def test_three_slots_chain_through_every_pass(make_world: WorldFactory) -> None:
    """MS-E2: three passes each way; each encode takes the previous output."""
    world = make_world(slot=PRIMARY)
    world.lipsync.marker = MARK
    render_multi(world, ((6.0, 7.0), SECOND))
    assert world.lipsync.start_s == [2.0, 6.0, 10.0]
    assert world.lipsync.video_bytes[2] == world.lipsync.outputs[1]
    assert world.lipsync.key_from[1:] == [world.lipsync.video_paths[0]] * 2
    assert len(world.encoder.calls) == 3
    assert [call.slot for call in world.encoder.calls] == [SECOND, (6.0, 7.0), PRIMARY]
    assert world.encoder.calls[1].template_bytes == ENCODED
    assert world.encoder.calls[2].template_bytes == ENCODED


def test_intermediate_files_live_only_in_the_temporary_folder(
    make_world: WorldFactory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MS-E3: every intermediate path is inside the temporary folder, and that folder is removed."""
    scratch = scratch_tempdir(monkeypatch, tmp_path)
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    paths: list[Path] = list(world.lipsync.out_paths)
    for call in world.encoder.calls:
        paths.extend(p for p in (call.out, call.label_path) if p is not None)
    assert paths
    assert all(scratch in path.parents for path in paths)
    assert list(scratch.iterdir()) == []


def test_the_intermediate_label_is_not_drawn_from_the_real_label_renderer(
    make_world: WorldFactory,
) -> None:
    """MS-E4: the transparent label is a file of its own; the label renderer ran once only."""
    world = make_world(slot=PRIMARY)
    render_multi(world, (SECOND,))
    assert len(world.labels.written) == 1
    assert world.encoder.calls[0].label_path != world.encoder.calls[1].label_path

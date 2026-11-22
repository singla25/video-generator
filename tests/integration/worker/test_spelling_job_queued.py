"""BL-11: a READY preview queues one spelling job in local AI mode, never in fake mode (AC1)."""

from __future__ import annotations

import logging

import pytest

from tests.fixtures.doubles import FakeJobQueue
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.domain.codes import FailureCode
from vidgen.infrastructure.db.uow import SqlUnitOfWork
from vidgen.infrastructure.sheets.reader import FileSheetReader
from vidgen.ports.batches import PREVIEW_READY
from vidgen.services.batch_support import BatchContext
from vidgen.services.batches import BatchService


class StubTransliterator:
    def transliterate(self, text: str, target_script: str) -> str:
        return "सुझाव"


def service_for(
    world: World, queue: FakeJobQueue, *, local: bool = True
) -> tuple[BatchService, FakeJobQueue]:
    ctx = BatchContext(
        uow=lambda: SqlUnitOfWork(world.factory, world.cipher),
        storage=world.storage,
        clock=world.clock,
        queue=queue,
        reader=FileSheetReader(),
        max_sheet_rows=100_000,
        max_name_graphemes=40,
        retention_days=30,
        transliterator=StubTransliterator() if local else None,
        require_spelling=local,
    )
    return BatchService(ctx), queue


def test_local_mode_queues_exactly_one_spelling_job_when_the_preview_is_ready(
    make_world: WorldFactory,
) -> None:
    """SP-J-P1."""
    world = make_world(batch_status="DRAFT")
    service, queue = service_for(world, FakeJobQueue())
    service.request_preview(world.batch_id)
    service.preview_rendered(world.batch_id, "previews/x.mp4")
    assert queue.spellings == [world.batch_id]


def test_fake_mode_queues_no_spelling_job(make_world: WorldFactory) -> None:
    """SP-J-N1."""
    world = make_world(batch_status="DRAFT")
    service, queue = service_for(world, FakeJobQueue(), local=False)
    service.request_preview(world.batch_id)
    service.preview_rendered(world.batch_id, "previews/x.mp4")
    assert queue.spellings == []


def test_a_failed_preview_queues_no_spelling_job(make_world: WorldFactory) -> None:
    """SP-J-N2."""
    world = make_world(batch_status="DRAFT")
    service, queue = service_for(world, FakeJobQueue())
    service.request_preview(world.batch_id)
    service.preview_failed(world.batch_id, FailureCode.TTS_FAILED)
    assert queue.spellings == []


def test_requesting_a_preview_or_starting_does_not_queue_the_job_itself(
    make_world: WorldFactory,
) -> None:
    """SP-J-N3: only a READY preview triggers it; start never waits for it."""
    world = make_world(batch_status="DRAFT")
    service, queue = service_for(world, FakeJobQueue())
    service.request_preview(world.batch_id)
    assert queue.spellings == []


def test_the_preview_still_becomes_ready_when_the_queue_is_down(
    make_world: WorldFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """SP-J-N4: the spelling job is optional; a queue error never fails the preview."""
    world = make_world(batch_status="DRAFT")
    queue = FakeJobQueue()
    service, _ = service_for(world, queue)
    service.request_preview(world.batch_id)
    queue.fail_spellings = ConnectionError("redis down")
    with caplog.at_level(logging.DEBUG):
        service.preview_rendered(world.batch_id, "previews/x.mp4")
    assert service.get(world.batch_id).preview_status == PREVIEW_READY
    assert queue.spellings == []


def test_a_preview_of_a_deleted_batch_queues_nothing_and_does_not_crash(
    make_world: WorldFactory,
) -> None:
    """SP-J-E1."""
    from uuid import uuid4

    world = make_world(batch_status="DRAFT")
    service, queue = service_for(world, FakeJobQueue())
    service.preview_rendered(uuid4(), "previews/x.mp4")
    assert queue.spellings == []


def test_two_ready_previews_of_two_regenerations_queue_two_jobs_that_are_safe_to_repeat(
    make_world: WorldFactory,
) -> None:
    """SP-J-E2: a regenerate queues again; the job itself is idempotent."""
    world = make_world(batch_status="DRAFT")
    service, queue = service_for(world, FakeJobQueue())
    for _ in range(2):
        service.request_preview(world.batch_id)
        service.preview_rendered(world.batch_id, "previews/x.mp4")
    assert queue.spellings == [world.batch_id, world.batch_id]

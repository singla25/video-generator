"""RP-RTE: the Dramatiq adapter sends to a chosen queue and counts depth per queue (AC6).

EXPECTED API (vidgen.infrastructure.queue.dramatiq_queue.DramatiqJobQueue, in-memory StubBroker)
  enqueue_preview(batch_id, row_id, queue_name=None) / enqueue_rows(batch_id, row_ids,
    queue_name=None)
  depth(queue_name=None)      None = the adapter's own queue (today's behaviour)
  Unknown queue names are declared on the broker on first use.
"""

from __future__ import annotations

from uuid import uuid4

from dramatiq.brokers.stub import StubBroker

from vidgen.infrastructure.queue.dramatiq_queue import DEFAULT_QUEUE, DramatiqJobQueue

PROVIDER_QUEUE = "vidgen.modal-demo"


def make() -> DramatiqJobQueue:
    return DramatiqJobQueue(StubBroker())


def test_rows_with_a_queue_name_land_only_on_that_queue() -> None:
    """RP-RTE-P1."""
    queue = make()
    queue.enqueue_rows(uuid4(), [uuid4(), uuid4()], queue_name=PROVIDER_QUEUE)
    assert queue.depth(queue_name=PROVIDER_QUEUE) == 2
    assert queue.depth() == 0
    assert queue.depth(queue_name=DEFAULT_QUEUE) == 0


def test_a_preview_with_a_queue_name_lands_only_on_that_queue() -> None:
    """RP-RTE-P2."""
    queue = make()
    queue.enqueue_preview(uuid4(), uuid4(), queue_name=PROVIDER_QUEUE)
    assert queue.depth(queue_name=PROVIDER_QUEUE) == 1
    assert queue.depth() == 0


def test_without_a_queue_name_jobs_go_to_the_default_queue_as_before() -> None:
    """RP-RTE-N1: old batches keep working."""
    queue = make()
    queue.enqueue_rows(uuid4(), [uuid4()])
    assert queue.depth() == 1
    assert queue.depth(queue_name=PROVIDER_QUEUE) == 0


def test_two_provider_queues_never_see_each_others_jobs() -> None:
    """RP-RTE-N2: a worker on another queue never gets the job."""
    queue = make()
    queue.enqueue_rows(uuid4(), [uuid4()] * 3, queue_name="vidgen.a")
    queue.enqueue_rows(uuid4(), [uuid4()] * 2, queue_name="vidgen.b")
    assert (queue.depth(queue_name="vidgen.a"), queue.depth(queue_name="vidgen.b")) == (3, 2)


def test_a_live_job_marker_is_kept_for_routed_rows() -> None:
    """RP-RTE-E1: the requeue job asks has_live_job per row, whatever queue it went to."""
    queue = make()
    row = uuid4()
    queue.enqueue_rows(uuid4(), [row], queue_name=PROVIDER_QUEUE)
    assert queue.has_live_job(row)

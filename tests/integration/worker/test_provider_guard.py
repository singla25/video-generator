"""RP-WRK: the worker enforces C5 and the spend cap on its own (AC7, AC8).

EXPECTED API
  vidgen.services.provider_guard.ProviderGuard(registry: ProviderRegistry, *,
    row_timeout_seconds: int)
  RowRenderer(..., provider_guard: ProviderGuard | None = None)   None = today's behaviour exactly
  Behaviour of ``render(batch_id, row_id)`` with a guard, the provider being batches.provider_id
  (null = registry default):
    * data class not allowed (demo_only provider, batch data_class "real"): the row is NOT rendered
      (stays QUEUED, attempts 0, no TTS call), the batch becomes PAUSED, outcome DEFERRED
    * spent + row worst case > cap (spent = sum of batch_rows.cost_usd of every batch of that
      provider):
      same result (row untouched, batch PAUSED, DEFERRED); equal to the cap is still rendered
    * a completed row stores cost_usd = render_seconds * provider.rate_per_second (0 for local)
  The API shows the reason through ``pause_reason``
    (tests/integration/api/test_batch_data_class.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.fixtures.pipeline_fakes import FakeVoice
from tests.fixtures.providers import local_provider, remote_provider
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import CREATOR, PAUSE_S, World
from vidgen.domain.providers import ProviderRegistry
from vidgen.infrastructure.db.models import BatchRow
from vidgen.infrastructure.db.row_store import SqlRowStore
from vidgen.services.provider_guard import ProviderGuard
from vidgen.services.render_row import RenderConfig, RowOutcomeKind, RowRenderer

RATE = 0.25  # USD per second, exact in binary so cap arithmetic has no rounding noise
RENDER_SECONDS = 4.0  # the fake voice moves the fake clock by this much, so each row costs 1.0
TIMEOUT = 2  # worst case of one row = 2 s x 0.25 = 0.5 USD
PEOPLE = [("Asha Verma", "A1"), ("Bina Rao", "B2"), ("Chitra Nair", "C3"), ("Dev Shah", "D4")]


class SlowVoice(FakeVoice):
    """A voice whose synthesis 'takes' RENDER_SECONDS on the world's fake clock."""

    def __init__(self, world: World) -> None:
        super().__init__(world.order)
        self._world = world

    def synthesize(self, text: str, voice_sample: Path, out: Path) -> float:
        self._world.clock.advance(seconds=RENDER_SECONDS)
        return super().synthesize(text, voice_sample, out)


def guarded(world: World, cap: float = 2.0) -> RowRenderer:
    """A renderer over the world's fakes with a ProviderGuard (local-mac + modal-demo registry)."""
    remote = remote_provider(spend_cap_usd=cap, rate_per_second=RATE)
    registry = ProviderRegistry([local_provider(), remote])
    world.voice = SlowVoice(world)
    return RowRenderer(
        row_store_factory=lambda: SqlRowStore(world.factory, world.cipher),
        storage=world.storage,
        voice=world.voice,
        lipsync=world.lipsync,
        encoder=world.encoder,
        quality=world.quality,
        labels=world.labels,
        clock=world.clock,
        config=RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S),
        preview_sink=world.previews,
        provider_guard=ProviderGuard(registry, row_timeout_seconds=TIMEOUT),
    )


def cost_of(world: World, number: int) -> float | None:
    with Session(world.engine) as session:
        value = session.execute(
            select(BatchRow.cost_usd).where(
                BatchRow.batch_id == world.batch_id, BatchRow.row_number == number
            )
        ).scalar_one()
    return None if value is None else float(value)


def spent(world: World) -> float:
    return sum(c for n in world.rows if (c := cost_of(world, n)) is not None)


def render(renderer: RowRenderer, world: World, number: int):  # type: ignore[no-untyped-def]
    return renderer.render(world.batch_id, world.rows[number])


@pytest.fixture
def four(make_world: WorldFactory) -> World:
    return make_world(PEOPLE)


# ---- C5 -------------------------------------------------------------------------------


def test_the_worker_refuses_a_demo_only_provider_for_a_real_batch_even_if_the_api_was_bypassed(
    make_world: WorldFactory,
) -> None:
    """RP-WRK-N1 (AC8): not rendered, batch paused, outcome DEFERRED, nothing synthesised."""
    world = make_world()
    world.set_batch(provider_id="modal-demo", data_class="real")
    outcome = render(guarded(world), world, 2)
    assert outcome.kind is RowOutcomeKind.DEFERRED
    assert world.row(2)["status"] == "QUEUED"
    assert world.row(2)["attempts"] == 0
    assert world.voice.texts == []
    assert world.encoder.calls == []
    assert world.batch()["status"] == "PAUSED"
    assert world.storage.files.get(world.expected_key("A1")) is None


def test_a_demo_batch_on_the_demo_only_provider_renders_and_records_its_cost(
    make_world: WorldFactory,
) -> None:
    """RP-WRK-P1."""
    world = make_world()
    world.set_batch(provider_id="modal-demo", data_class="demo")
    outcome = render(guarded(world), world, 2)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.row(2)["render_seconds"] == pytest.approx(RENDER_SECONDS)
    assert cost_of(world, 2) == pytest.approx(RENDER_SECONDS * RATE)


def test_a_real_batch_on_a_local_provider_renders_with_zero_cost(make_world: WorldFactory) -> None:
    """RP-WRK-P2."""
    world = make_world()
    world.set_batch(provider_id="local-mac", data_class="real")
    assert render(guarded(world), world, 2).kind is RowOutcomeKind.COMPLETED
    assert cost_of(world, 2) == 0.0


def test_an_old_batch_without_a_provider_uses_the_default_provider(
    make_world: WorldFactory,
) -> None:
    """RP-WRK-E1 (R5): null provider, real data -> default (local) -> renders."""
    world = make_world()
    assert render(guarded(world), world, 2).kind is RowOutcomeKind.COMPLETED
    assert world.batch()["status"] == "RUNNING"


def test_without_a_guard_the_worker_behaves_exactly_as_before(make_world: WorldFactory) -> None:
    """RP-WRK-E2: the guard is opt-in, existing wiring is unchanged."""
    world = make_world()
    world.set_batch(provider_id="modal-demo", data_class="real")
    outcome = world.renderer.render(world.batch_id, world.rows[2])
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert cost_of(world, 2) is None


# ---- spend cap ------------------------------------------------------------------------


def test_spent_accumulates_and_the_batch_pauses_before_the_row_that_would_pass_the_cap(
    four: World,
) -> None:
    """RP-WRK-P3 (AC7): cap 2.0; rows cost 1.0 each; worst case 0.5."""
    four.set_batch(provider_id="modal-demo", data_class="demo")
    renderer = guarded(four, cap=2.0)
    assert render(renderer, four, 2).kind is RowOutcomeKind.COMPLETED  # 0.0 + 0.5 <= 2.0
    assert render(renderer, four, 3).kind is RowOutcomeKind.COMPLETED  # 1.0 + 0.5 <= 2.0
    assert spent(four) == pytest.approx(2.0)
    outcome = render(renderer, four, 4)  # 2.0 + 0.5 > 2.0
    assert outcome.kind is RowOutcomeKind.DEFERRED
    assert four.statuses() == {2: "COMPLETED", 3: "COMPLETED", 4: "QUEUED", 5: "QUEUED"}
    assert four.row(4)["attempts"] == 0  # no row failed, none was started
    assert four.batch()["status"] == "PAUSED"
    assert spent(four) == pytest.approx(2.0)


def test_reaching_the_cap_exactly_is_allowed(four: World) -> None:
    """RP-WRK-E3: cap 2.5: the third row needs 2.0 + 0.5 = 2.5, not above it."""
    four.set_batch(provider_id="modal-demo", data_class="demo")
    renderer = guarded(four, cap=2.5)
    kinds = [render(renderer, four, n).kind for n in (2, 3, 4, 5)]
    assert kinds == [
        RowOutcomeKind.COMPLETED,
        RowOutcomeKind.COMPLETED,
        RowOutcomeKind.COMPLETED,
        RowOutcomeKind.DEFERRED,
    ]
    assert four.batch()["status"] == "PAUSED"


def test_a_raised_cap_lets_the_resumed_batch_render_the_waiting_row(four: World) -> None:
    """RP-WRK-E4."""
    four.set_batch(provider_id="modal-demo", data_class="demo")
    assert [render(guarded(four, cap=1.0), four, n).kind for n in (2, 3)] == [
        RowOutcomeKind.COMPLETED,
        RowOutcomeKind.DEFERRED,
    ]
    four.set_batch(status="RUNNING")  # the Admin raised the cap (new registry) and resumed
    assert render(guarded(four, cap=5.0), four, 3).kind is RowOutcomeKind.COMPLETED
    assert four.row(3)["status"] == "COMPLETED"


def test_a_paused_batch_keeps_deferring_without_spending(four: World) -> None:
    """RP-WRK-E5: redelivered jobs of a capped batch cost nothing and change nothing."""
    four.set_batch(provider_id="modal-demo", data_class="demo")
    renderer = guarded(four, cap=1.0)
    render(renderer, four, 2)
    render(renderer, four, 3)  # pauses
    before = spent(four)
    for _ in range(3):
        assert render(renderer, four, 4).kind is RowOutcomeKind.DEFERRED
    assert spent(four) == before

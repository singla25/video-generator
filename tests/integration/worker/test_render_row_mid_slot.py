"""DD-39 part B: the row pipeline hands the template slot start to the lip sync.

A name in the middle of the template must get mouth movement at the slot, not at 0:00. The
recording lip-sync double (FakeLipSync) keeps every start_s it receives. Stage order and the
published output are unchanged. Test tree IDs: ML-R-* (docs/test-tree/mid-slot-lipsync.md).
"""

from __future__ import annotations

import pytest

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.services.render_row import RowOutcome, RowOutcomeKind


def render_row_two(world: World) -> RowOutcome:
    """Render the first data row of the world for real."""
    return world.renderer.render(world.batch_id, world.rows[2])


@pytest.mark.parametrize(("slot", "start_s"), [((4.5, 5.4), 4.5), ((0.0, 1.0), 0.0)])
def test_lip_sync_receives_the_slot_start(
    make_world: WorldFactory, slot: tuple[float, float], start_s: float
) -> None:
    """ML-R-P1 (name in the middle, 4.5 s) and ML-R-P2 (name at the start, 0.0 s)."""
    world = make_world(slot=slot)
    outcome = render_row_two(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.lipsync.start_s == [start_s]


def test_the_lip_sync_gets_the_start_not_the_end_of_the_slot(make_world: WorldFactory) -> None:
    """ML-R-E1: the end (5.4) and the length (0.9) of the slot are never passed as the start."""
    world = make_world(slot=(4.5, 5.4))
    render_row_two(world)
    assert world.lipsync.start_s != [5.4]
    assert world.lipsync.start_s == [4.5]


def test_stage_order_is_unchanged_and_the_output_is_published(make_world: WorldFactory) -> None:
    """ML-R-P3: tts -> lipsync -> encode -> check, then stored under the row's key."""
    world = make_world(slot=(4.5, 5.4))
    outcome = render_row_two(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert world.order == ["tts", "lipsync", "encode", "check"]
    assert world.storage.files[world.expected_key("A1")] == b"ENC"

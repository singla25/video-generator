"""The row pipeline hands the name gap to the planner and then to the encoder (DD-34)."""

from __future__ import annotations

from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import CREATOR, PAUSE_S, World
from vidgen.services.render_row import RenderConfig, RowOutcomeKind


def config(**kwargs: object) -> RenderConfig:
    """A render config for the tests."""
    return RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S, **kwargs)  # type: ignore[arg-type]


def render(world: World):  # type: ignore[no-untyped-def]
    """Render the world's single row."""
    return world.renderer.render(world.batch_id, world.rows[2])


def test_the_plan_given_to_the_encoder_carries_the_configured_gap(
    make_world: WorldFactory,
) -> None:
    """DD-34 positive: name_gap_s 0.25 reaches plan.gap_s of the encoder call."""
    world = make_world(config=config(name_gap_s=0.25))
    outcome = render(world)
    assert outcome.kind is RowOutcomeKind.COMPLETED
    assert len(world.encoder.calls) == 1
    assert world.encoder.calls[0].plan.gap_s == 0.25


def test_the_default_config_gives_a_plan_with_no_gap(world: World) -> None:
    """DD-34 default: a row rendered with the default config has plan.gap_s == 0.0."""
    assert render(world).kind is RowOutcomeKind.COMPLETED
    assert world.encoder.calls[0].plan.gap_s == 0.0


def test_a_gap_does_not_change_the_row_outcome(make_world: WorldFactory) -> None:
    """DD-34 edge: the maximum gap (1.0 s) still completes the row and stores the output."""
    world = make_world(config=config(name_gap_s=1.0))
    assert render(world).kind is RowOutcomeKind.COMPLETED
    assert world.row(2)["status"] == "COMPLETED"
    assert world.encoder.calls[0].plan.gap_s == 1.0

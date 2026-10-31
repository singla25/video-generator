"""DD-39: the voice gets "<name> <suffix>" for batch rows and for the preview row.

The suffix is RenderConfig.spoken_suffix (the worker copies it from Settings). A confirmed
spoken name (DD-38, D3) is what gets the suffix when there is one. The voice is the recording
fake the neighbouring tests use.

Test tree IDs: SS-R-* (row pipeline) and SS-P-* (preview), see docs/test-tree/spoken-suffix.md.
"""

from __future__ import annotations

import pytest

from tests.fixtures.names import DEVANAGARI_NAME
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.test_preview_uses_confirmed_name import ready_draft
from tests.integration.worker.world import CREATOR, PAUSE_S, World
from vidgen.services.render_row import RenderConfig

SUFFIX = "जी"  # "जी"
CONFIRMED = "आशा वर्मा"  # "आशा वर्मा", the typed spelling
PREVIEW_ROW = 2  # the first data row of the world
BATCH_ROW = 2


def config(suffix: str) -> RenderConfig:
    """A render config with the given spoken suffix and everything else as in the worker tests."""
    return RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S, spoken_suffix=suffix)


def render_batch_row(world: World) -> list[str]:
    """Render the first data row for real and return the texts the voice was given."""
    world.renderer.render(world.batch_id, world.rows[BATCH_ROW])
    return list(world.voice.texts)


def render_preview_row(world: World) -> list[str]:
    """Render the preview of the preview row and return the texts the voice was given."""
    world.renderer.render_preview(world.batch_id, world.rows[PREVIEW_ROW])
    return list(world.voice.texts)


# ---- batch rows -----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Asha Verma", DEVANAGARI_NAME])
def test_batch_row_speaks_the_name_then_the_suffix(make_world: WorldFactory, name: str) -> None:
    """SS-R-P1: the configured suffix follows the name in the text given to the voice."""
    world = make_world([(name, "A1")], config=config(SUFFIX))
    assert render_batch_row(world) == [f"{name} {SUFFIX}"]


def test_empty_suffix_speaks_the_name_only(make_world: WorldFactory) -> None:
    """SS-R-N1: with no suffix configured (the RenderConfig default) only the name is spoken."""
    world = make_world([("Asha Verma", "A1")])
    assert render_batch_row(world) == ["Asha Verma"]


def test_name_already_ending_with_the_suffix_is_not_doubled(make_world: WorldFactory) -> None:
    """SS-R-E1: the name's last word equals the suffix, so the voice gets it once."""
    world = make_world([(f"Asha {SUFFIX}", "A1")], config=config(SUFFIX))
    assert render_batch_row(world) == [f"Asha {SUFFIX}"]


def test_roman_name_ending_with_the_suffix_in_another_case_is_not_doubled(
    make_world: WorldFactory,
) -> None:
    """SS-R-E1: the comparison ignores case for Roman letters."""
    world = make_world([("Asha ji", "A1")], config=config("Ji"))
    assert render_batch_row(world) == ["Asha ji"]


def test_a_suffix_word_in_the_middle_of_the_name_does_not_stop_the_suffix(
    make_world: WorldFactory,
) -> None:
    """SS-R-E2: only the last word of the name decides."""
    world = make_world([(f"{SUFFIX} Asha Verma", "A1")], config=config(SUFFIX))
    assert render_batch_row(world) == [f"{SUFFIX} Asha Verma {SUFFIX}"]


def test_the_voice_never_gets_the_id_even_with_a_suffix(make_world: WorldFactory) -> None:
    """SS-R-E3: the suffix does not change the rule that the ID is never spoken (R3.3)."""
    world = make_world([("Smt. Asha Verma", "SECRET-ID-77")], config=config(SUFFIX))
    render_batch_row(world)
    assert world.voice.texts == [f"Smt. Asha Verma {SUFFIX}"]
    assert "SECRET-ID-77" not in " ".join(world.voice.texts)


def test_confirmed_spoken_name_gets_the_suffix_after_it(make_world: WorldFactory) -> None:
    """SS-R-P2: the spoken-name column (D3) is the base; the suffix comes after it."""
    world = make_world(
        [("Asha Verma", "A1")], spoken={BATCH_ROW: "Aasha Varma"}, config=config(SUFFIX)
    )
    assert render_batch_row(world) == [f"Aasha Varma {SUFFIX}"]


def test_confirmed_spoken_name_already_ending_with_the_suffix_is_not_doubled(
    make_world: WorldFactory,
) -> None:
    """SS-R-E4: a spoken name that already ends with the suffix gets it only once."""
    world = make_world(
        [("Asha Verma", "A1")], spoken={BATCH_ROW: f"Aasha Varma {SUFFIX}"}, config=config(SUFFIX)
    )
    assert render_batch_row(world) == [f"Aasha Varma {SUFFIX}"]


# ---- preview row ----------------------------------------------------------------------


def test_preview_speaks_the_row_name_with_the_suffix(make_world: WorldFactory) -> None:
    """SS-P-P1: with no confirmation the preview gets the row name plus the suffix."""
    world = make_world(batch_status="DRAFT", config=config(SUFFIX))
    service = ready_draft(world)
    service.request_preview(world.batch_id)
    assert render_preview_row(world) == [f"Asha Verma {SUFFIX}"]


def test_preview_speaks_the_confirmed_name_with_the_suffix_after_it(
    make_world: WorldFactory,
) -> None:
    """SS-P-P2: the confirmed spelling is the base; the suffix follows it in the preview."""
    world = make_world(batch_status="DRAFT", config=config(SUFFIX))
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, CONFIRMED)
    service.request_preview(world.batch_id)
    assert render_preview_row(world) == [f"{CONFIRMED} {SUFFIX}"]


def test_preview_confirmed_name_already_ending_with_the_suffix_is_not_doubled(
    make_world: WorldFactory,
) -> None:
    """SS-P-E1: a confirmed spelling that ends with the suffix is spoken once."""
    world = make_world(batch_status="DRAFT", config=config(SUFFIX))
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, f"{CONFIRMED} {SUFFIX}")
    service.request_preview(world.batch_id)
    assert render_preview_row(world) == [f"{CONFIRMED} {SUFFIX}"]


def test_preview_with_an_empty_suffix_speaks_the_confirmed_name_only(
    make_world: WorldFactory,
) -> None:
    """SS-P-N1: the suffix switched off (""): the preview is the confirmed name, as before."""
    world = make_world(batch_status="DRAFT", config=config(""))
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, CONFIRMED)
    service.request_preview(world.batch_id)
    assert render_preview_row(world) == [CONFIRMED]

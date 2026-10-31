"""DD-38: the preview render speaks the spelling the human confirmed, not the row's own name.

The API path (confirm, then regenerate) is driven through the batch service on the worker's
own database and cipher, so the render reads exactly what the API would have stored. The voice
is the recording fake the other preview tests use.
"""

from __future__ import annotations

from typing import Any

from tests.fixtures.doubles import FakeJobQueue
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.infrastructure.db.uow import SqlUnitOfWork
from vidgen.infrastructure.sheets.reader import FileSheetReader
from vidgen.services.batch_support import BatchContext
from vidgen.services.batches import BatchService

CONFIRMED = "आशा वर्मा"  # the spelling the human typed for the row 'Asha Verma'
ROW_NAME = "Asha Verma"
PREVIEW_ROW = 2  # the first data row of the world


class StubTransliterator:
    """Local AI mode needs a transliterator; a fixed guess keeps the weights out of the test."""

    def transliterate(self, text: str, target_script: str) -> str:
        """Return a canned suggestion."""
        return "सुझाव"


def service_for(world: World) -> BatchService:
    """The batch service of the API, wired to the worker's database, cipher and storage."""
    ctx = BatchContext(
        uow=lambda: SqlUnitOfWork(world.factory, world.cipher),
        storage=world.storage,
        clock=world.clock,
        queue=FakeJobQueue(),
        reader=FileSheetReader(),
        max_sheet_rows=100_000,
        max_name_graphemes=40,
        retention_days=30,
        transliterator=StubTransliterator(),
        require_spelling=True,
    )
    return BatchService(ctx)


def ready_draft(world: World) -> BatchService:
    """A DRAFT batch whose first preview has been rendered (the 'worker' reports it)."""
    service = service_for(world)
    service.request_preview(world.batch_id)
    service.preview_rendered(world.batch_id, f"previews/{world.batch_id}.mp4")
    return service


def render(world: World) -> list[str]:
    """Render the preview of the preview row and return the texts the voice was given."""
    world.renderer.render_preview(world.batch_id, world.rows[PREVIEW_ROW])
    return list(world.voice.texts)


def test_preview_speaks_the_confirmed_name_after_regenerate(make_world: WorldFactory) -> None:
    """DD-38 W-P1: confirm, regenerate, render: the voice gets the confirmed text."""
    world = make_world(batch_status="DRAFT")
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, CONFIRMED)
    service.request_preview(world.batch_id)
    assert render(world) == [CONFIRMED]


def test_preview_speaks_the_row_name_when_nothing_was_confirmed(make_world: WorldFactory) -> None:
    """DD-38 W-E1: no confirmation at all: the voice keeps getting the row's own name."""
    world = make_world(batch_status="DRAFT")
    service = ready_draft(world)
    service.request_preview(world.batch_id)
    assert render(world) == [ROW_NAME]


def test_blank_confirmed_name_falls_back_to_the_row_name(make_world: WorldFactory) -> None:
    """DD-38 W-N1: a whitespace-only confirmation is never spoken; the row name is used."""
    world = make_world(batch_status="DRAFT")
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, "   ")
    service.request_preview(world.batch_id)
    assert render(world) == [ROW_NAME]


def test_confirmed_name_is_not_used_for_a_different_row(make_world: WorldFactory) -> None:
    """DD-38 W-E1: the confirmed spelling belongs to the preview row only.

    A second row of the same batch keeps its own name when it is rendered for real.
    """
    world = make_world(
        [("Asha Verma", "A1"), ("Bina Rao", "B2")],
        batch_status="DRAFT",
    )
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, CONFIRMED)
    service.request_preview(world.batch_id)
    world.renderer.render_preview(world.batch_id, world.rows[3])
    assert world.voice.texts == ["Bina Rao"]
    assert CONFIRMED not in world.voice.texts


def test_confirmed_name_never_appears_in_the_stored_row(make_world: WorldFactory) -> None:
    """DD-38 W-E1: the render of the preview does not write the confirmed text into the row."""
    world = make_world(batch_status="DRAFT")
    service = ready_draft(world)
    service.confirm_spelling(world.batch_id, CONFIRMED)
    service.request_preview(world.batch_id)
    before: dict[str, Any] = world.row(PREVIEW_ROW)
    render(world)
    assert world.row(PREVIEW_ROW) == before

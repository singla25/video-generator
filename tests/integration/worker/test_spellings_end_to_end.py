"""BL-11: a row filled by the spelling job is spoken in Devanagari; a row without one is not.

The filler runs on the real row store of the world; the voice is the recording fake.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.fixtures.spelling_fakes import FakeTransliterator
from tests.integration.worker.conftest import WorldFactory
from tests.integration.worker.world import World
from vidgen.infrastructure.db.models import BatchRow
from vidgen.infrastructure.db.row_store import SqlRowStore
from vidgen.services.spelling_filler import SpellingFiller

PEOPLE = [("Asha Verma", "A1"), ("Bina Rao", "B2"), ("Chitra Sen", "C3")]
SPELLED = {"Asha Verma": "आशा वर्मा", "Bina Rao": "बीना राव", "Chitra Sen": "चित्रा सेन"}


def filler_for(world: World, translit: FakeTransliterator, page_size: int = 50) -> SpellingFiller:
    return SpellingFiller(
        SqlRowStore(world.factory, world.cipher), translit, "devanagari", page_size=page_size
    )


def raw_column(world: World, number: int) -> bytes | None:
    with Session(world.engine) as session:
        value = session.execute(
            select(BatchRow.spoken_name_enc).where(
                BatchRow.batch_id == world.batch_id, BatchRow.row_number == number
            )
        ).scalar_one()
        return None if value is None else bytes(value)


def test_rows_filled_by_the_job_are_synthesized_with_their_spelling(
    make_world: WorldFactory,
) -> None:
    """SP-W-P1 (AC3)."""
    world = make_world(PEOPLE)
    filler_for(world, FakeTransliterator(dict(SPELLED))).fill_missing(world.batch_id)
    for number in (2, 3, 4):
        world.renderer.render(world.batch_id, world.rows[number])
    assert sorted(world.voice.texts) == sorted(SPELLED.values())


def test_a_row_without_a_spelling_still_speaks_its_roman_text(make_world: WorldFactory) -> None:
    """SP-W-P2 (AC3): the job has not run (or failed for this row)."""
    world = make_world(PEOPLE)
    translit = FakeTransliterator(dict(SPELLED))
    translit.errors["Bina Rao"] = RuntimeError("model failed")
    filler_for(world, translit).fill_missing(world.batch_id)
    for number in (2, 3, 4):
        world.renderer.render(world.batch_id, world.rows[number])
    assert sorted(world.voice.texts) == sorted(["आशा वर्मा", "Bina Rao", "चित्रा सेन"])


def test_without_running_the_job_nothing_changes_for_the_render(make_world: WorldFactory) -> None:
    """SP-W-P3."""
    world = make_world(PEOPLE)
    world.renderer.render(world.batch_id, world.rows[2])
    assert world.voice.texts == ["Asha Verma"]


def test_the_spellings_are_encrypted_in_the_row_column(make_world: WorldFactory) -> None:
    """SP-W-P4."""
    world = make_world(PEOPLE)
    filler_for(world, FakeTransliterator(dict(SPELLED))).fill_missing(world.batch_id)
    raw = raw_column(world, 2)
    assert raw is not None
    assert "आशा".encode() not in raw
    assert world.cipher.decrypt(raw) == "आशा वर्मा"


def test_a_sheet_spoken_name_wins_and_is_never_overwritten(make_world: WorldFactory) -> None:
    """SP-W-N1."""
    world = make_world(PEOPLE, spoken={2: "अपना नाम"})
    before = raw_column(world, 2)
    filler_for(world, FakeTransliterator(dict(SPELLED))).fill_missing(world.batch_id)
    assert raw_column(world, 2) == before
    world.renderer.render(world.batch_id, world.rows[2])
    assert world.voice.texts == ["अपना नाम"]


def test_rows_already_processing_or_completed_are_not_touched(make_world: WorldFactory) -> None:
    """SP-W-N2."""
    world = make_world(PEOPLE)
    world.set_rows([2], status="PROCESSING")
    world.set_rows([3], status="COMPLETED")
    filler_for(world, FakeTransliterator(dict(SPELLED))).fill_missing(world.batch_id)
    assert raw_column(world, 2) is None
    assert raw_column(world, 3) is None
    assert raw_column(world, 4) is not None


def test_more_rows_than_a_page_and_a_second_run(make_world: WorldFactory) -> None:
    """SP-W-E1: page size 2 over 3 rows, then idempotent."""
    world = make_world(PEOPLE)
    translit = FakeTransliterator(dict(SPELLED))
    filler = filler_for(world, translit, page_size=2)
    first = filler.fill_missing(world.batch_id)
    stored = [raw_column(world, n) for n in (2, 3, 4)]
    second = filler.fill_missing(world.batch_id)
    assert (first.filled, second.filled) == (3, 0)
    assert [raw_column(world, n) for n in (2, 3, 4)] == stored
    assert translit.released == 2


def test_a_batch_deleted_during_the_run_does_not_crash_the_job(make_world: WorldFactory) -> None:
    """SP-W-E2: the batch is gone after the first page; the next writes find nothing."""
    from vidgen.infrastructure.db.repositories import BatchRepository

    world = make_world(PEOPLE)
    translit = FakeTransliterator(dict(SPELLED))

    def delete_on_first_call(text: str) -> str:
        with Session(world.engine) as session:
            BatchRepository(session, world.cipher).delete_batch(world.batch_id)
            session.commit()
        return "आशा"

    translit.default = delete_on_first_call
    report = filler_for(world, translit, page_size=2).fill_missing(world.batch_id)
    assert report.failed == 0
    assert translit.released == 1

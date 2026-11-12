"""Template repository: the extra slots round trip through the templates table (DD-40).

Test IDs: MS-DB-* in docs/test-tree/multi-slot-model.md.
The column is a nullable JSON list of [start, end] pairs; NULL and [] both read as ().
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.integration.db.helpers import make_campaign
from vidgen.infrastructure.db.repositories import SqlTemplateRepository
from vidgen.ports.models import TemplateRecord


def record(**overrides: object) -> TemplateRecord:
    """A template record with a primary slot 1.0-2.0."""
    fields: dict[str, object] = {
        "id": uuid4(),
        "video_key": "templates/t.mp4",
        "original_name": "Krishan",
        "duration_s": 4.0,
        "width": 320,
        "height": 240,
        "slot_start_s": 1.0,
        "slot_end_s": 2.0,
        "slot_source": "MANUAL",
    }
    fields.update(overrides)
    return TemplateRecord(**fields)  # type: ignore[arg-type]


def add_template(db: Engine, template: TemplateRecord) -> UUID:
    """Store a template in its own campaign and return its id."""
    with Session(db) as session:
        campaign = make_campaign(session)
        SqlTemplateRepository(session).add(campaign.id, template)
        session.commit()
    return template.id


def read_template(db: Engine, template_id: UUID) -> TemplateRecord | None:
    """Load a template through the repository in a fresh session."""
    with Session(db) as session:
        return SqlTemplateRepository(session).get(template_id)


def raw_extra_slots(db: Engine, template_id: UUID) -> object:
    """The stored value of the column, bypassing the repository."""
    with db.connect() as conn:
        return conn.execute(
            text("SELECT extra_slots FROM templates WHERE id = :id"), {"id": template_id}
        ).scalar_one()


# ---- positive -------------------------------------------------------------------------


def test_extra_slots_round_trip_as_a_tuple_of_tuples(db: Engine) -> None:
    """MS-DB-P1."""
    extras = ((2.2, 2.8), (3.0, 3.5))
    template_id = add_template(db, record(extra_slots=extras))
    loaded = read_template(db, template_id)
    assert loaded is not None
    assert loaded.extra_slots == extras
    assert loaded.slots == ((1.0, 2.0), (2.2, 2.8), (3.0, 3.5))


def test_a_template_saved_without_extras_reads_back_as_empty_tuple(db: Engine) -> None:
    """MS-DB-P2."""
    template_id = add_template(db, record())
    loaded = read_template(db, template_id)
    assert loaded is not None
    assert loaded.extra_slots == ()


def test_saving_with_no_extras_again_clears_the_stored_extras(db: Engine) -> None:
    """MS-DB-P3: the save path writes the new field too."""
    template = record(extra_slots=((2.2, 2.8),))
    template_id = add_template(db, template)
    with Session(db) as session:
        repo = SqlTemplateRepository(session)
        loaded = repo.get(template_id)
        assert loaded is not None
        loaded.extra_slots = ()
        repo.save(loaded)
        session.commit()
    reloaded = read_template(db, template_id)
    assert reloaded is not None
    assert reloaded.extra_slots == ()


def test_stored_json_is_a_list_of_start_end_pairs(db: Engine) -> None:
    """MS-DB-P4."""
    template_id = add_template(db, record(extra_slots=((2.2, 2.8), (3.0, 3.5))))
    assert raw_extra_slots(db, template_id) == [[2.2, 2.8], [3.0, 3.5]]


# ---- negative -------------------------------------------------------------------------


def test_unknown_template_still_reads_as_none(db: Engine) -> None:
    """MS-DB-N1: the new column does not change lookups of missing rows."""
    assert read_template(db, uuid4()) is None


# ---- edge -----------------------------------------------------------------------------


def test_null_in_the_column_reads_as_empty_tuple(db: Engine) -> None:
    """MS-DB-E1: rows written before the column existed hold NULL."""
    template_id = add_template(db, record())
    with db.begin() as conn:
        conn.execute(
            text("UPDATE templates SET extra_slots = NULL WHERE id = :id"), {"id": template_id}
        )
    loaded = read_template(db, template_id)
    assert loaded is not None
    assert loaded.extra_slots == ()


def test_empty_json_list_in_the_column_reads_as_empty_tuple(db: Engine) -> None:
    """MS-DB-E2."""
    template_id = add_template(db, record())
    with db.begin() as conn:
        conn.execute(
            text("UPDATE templates SET extra_slots = CAST(:v AS JSON) WHERE id = :id"),
            {"v": "[]", "id": template_id},
        )
    loaded = read_template(db, template_id)
    assert loaded is not None
    assert loaded.extra_slots == ()

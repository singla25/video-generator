"""The ``slots`` property of a template and of the row-job template snapshot (DD-40).

Test IDs: MS-SP-* in docs/test-tree/multi-slot-model.md.
``slots`` is the primary slot plus the extra slots, all sorted by start; () when there is no
primary slot.
"""

from __future__ import annotations

from uuid import uuid4

from vidgen.ports.models import TemplateRecord
from vidgen.ports.rows import TemplateInfo


def make_template(**overrides: object) -> TemplateRecord:
    """A template with probe facts and no slot."""
    fields: dict[str, object] = {
        "id": uuid4(),
        "video_key": "templates/t.mp4",
        "original_name": "Krishan",
        "duration_s": 4.0,
        "width": 320,
        "height": 240,
    }
    fields.update(overrides)
    return TemplateRecord(**fields)  # type: ignore[arg-type]


# ---- positive -------------------------------------------------------------------------


def test_primary_only_gives_one_slot_pair() -> None:
    """MS-SP-P1."""
    template = make_template(slot_start_s=1.0, slot_end_s=2.0)
    assert template.slots == ((1.0, 2.0),)


def test_primary_plus_extras_gives_all_of_them_sorted_by_start() -> None:
    """MS-SP-P2."""
    template = make_template(slot_start_s=1.0, slot_end_s=2.0, extra_slots=((2.2, 2.8), (3.0, 3.5)))
    assert template.slots == ((1.0, 2.0), (2.2, 2.8), (3.0, 3.5))


def test_extra_slots_defaults_to_empty_tuple() -> None:
    """MS-SP-P3."""
    assert make_template().extra_slots == ()


def test_row_job_snapshot_slots_follow_the_same_meaning() -> None:
    """MS-SP-P4: TemplateInfo is the row job's template snapshot."""
    info = TemplateInfo(
        video_key="templates/t.mp4",
        width=320,
        height=240,
        slot=(1.0, 2.0),
        slot_confirmed=True,
        consent_confirmed=True,
        extra_slots=((2.2, 2.8),),
    )
    assert info.slots == ((1.0, 2.0), (2.2, 2.8))


def test_row_job_snapshot_extra_slots_defaults_to_empty_tuple() -> None:
    """MS-SP-P4: existing callers that do not pass extra slots keep working."""
    info = TemplateInfo(
        video_key="templates/t.mp4",
        width=320,
        height=240,
        slot=(1.0, 2.0),
        slot_confirmed=True,
        consent_confirmed=True,
    )
    assert info.extra_slots == ()
    assert info.slots == ((1.0, 2.0),)


# ---- negative -------------------------------------------------------------------------


def test_without_a_primary_slot_slots_is_empty_even_with_extras() -> None:
    """MS-SP-N1."""
    template = make_template(extra_slots=((2.0, 2.6),))
    assert template.slots == ()


def test_row_job_snapshot_without_primary_slot_is_empty() -> None:
    """MS-SP-N1 for the snapshot."""
    info = TemplateInfo(
        video_key="templates/t.mp4",
        width=320,
        height=240,
        slot=None,
        slot_confirmed=False,
        consent_confirmed=False,
        extra_slots=((2.0, 2.6),),
    )
    assert info.slots == ()


# ---- edge -----------------------------------------------------------------------------


def test_primary_in_the_middle_is_sorted_by_start_not_placed_first() -> None:
    """MS-SP-E1: 'all slots sorted' means one sorted list, not primary-then-extras."""
    template = make_template(slot_start_s=2.0, slot_end_s=2.6, extra_slots=((0.0, 0.5), (3.0, 3.5)))
    assert template.slots == ((0.0, 0.5), (2.0, 2.6), (3.0, 3.5))


def test_slots_is_a_tuple_of_float_pairs() -> None:
    """MS-SP-E2."""
    template = make_template(slot_start_s=1.0, slot_end_s=2.0, extra_slots=((3.0, 3.5),))
    assert isinstance(template.slots, tuple)
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in template.slots)
    assert all(isinstance(value, float) for pair in template.slots for value in pair)

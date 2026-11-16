"""The approval fingerprint includes the extra slots (DD-40, A5).

Test IDs: MS-FP-* in docs/test-tree/multi-slot-model.md.
"""

from __future__ import annotations

from uuid import UUID

from vidgen.domain.status import ApprovalFingerprint, PreviewGate, approve_preview, can_start
from vidgen.ports.batches import MappingRecord
from vidgen.ports.models import TemplateRecord
from vidgen.services.batch_rules import fingerprint_for

TEMPLATE_ID = UUID("6f1c2a3e-8b7d-4e21-9c0a-1d2e3f4a5b6c")
MAPPING = MappingRecord(
    name_column="Name",
    id_column="ID",
    spoken_name_column=None,
    name_index=0,
    id_index=1,
    spoken_name_index=None,
)


def template(extra_slots: tuple[tuple[float, float], ...] = ()) -> TemplateRecord:
    """A template with the primary slot 1.0-2.0 and the given extra slots."""
    return TemplateRecord(
        id=TEMPLATE_ID,
        video_key="templates/t.mp4",
        original_name="Krishan",
        duration_s=4.0,
        width=320,
        height=240,
        slot_start_s=1.0,
        slot_end_s=2.0,
        extra_slots=extra_slots,
    )


def test_fingerprint_has_no_extra_slots_by_default() -> None:
    """MS-FP-E2: the positional form used before the feature still works, with ()."""
    fingerprint = ApprovalFingerprint(1.0, 2.0, "t1", (0, 1, None))
    assert fingerprint.extra_slots == ()


def test_fingerprint_for_carries_the_template_extra_slots() -> None:
    """MS-FP-P1 (unit side): the fingerprint is filled from the template."""
    extras = ((2.2, 2.8),)
    assert fingerprint_for(template(extras), MAPPING).extra_slots == extras


def test_same_template_and_extras_give_the_same_fingerprint() -> None:
    """MS-FP-P1: an unchanged template keeps its fingerprint."""
    extras = ((2.2, 2.8),)
    assert fingerprint_for(template(extras), MAPPING) == fingerprint_for(template(extras), MAPPING)


def test_changing_only_an_extra_slot_changes_the_fingerprint() -> None:
    """MS-FP-E1: same primary slot, same template, same mapping; only an extra differs."""
    before = fingerprint_for(template(((2.2, 2.8),)), MAPPING)
    after = fingerprint_for(template(((2.2, 2.9),)), MAPPING)
    assert before != after


def test_no_extras_fingerprint_matches_the_fingerprint_before_the_feature() -> None:
    """MS-FP-E2: a template without extras has fingerprint extra_slots () and the old fields."""
    fingerprint = fingerprint_for(template(), MAPPING)
    assert fingerprint == ApprovalFingerprint(1.0, 2.0, str(TEMPLATE_ID), (0, 1, None))


def test_gate_approved_for_old_extras_cannot_start_after_an_extra_only_change() -> None:
    """MS-FP-N1, MS-FP-E3: the stale mechanism of the preview gate sees the extra slot."""
    old = fingerprint_for(template(((2.2, 2.8),)), MAPPING)
    new = fingerprint_for(template(((2.2, 2.9),)), MAPPING)
    gate = approve_preview(PreviewGate(rendered_for=old), old)
    assert can_start(gate, old)
    assert not can_start(gate, new)

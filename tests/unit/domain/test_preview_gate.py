"""Preview approval as a pure state rule (AC7, A5). Cases TT-AC7-*."""

from __future__ import annotations

import pytest

from vidgen.domain.status import (
    ApprovalFingerprint,
    PreviewGate,
    PreviewNotReadyError,
    approve_preview,
    can_start,
    preview_rendered,
)

FP = ApprovalFingerprint(slot_start_s=1.0, slot_end_s=1.6, template_id="t1", mapping=(0, 1, None))


def test_new_gate_cannot_start() -> None:
    """TT-AC7-N1."""
    assert not can_start(PreviewGate(), FP)


def test_rendered_but_unapproved_preview_cannot_start() -> None:
    """TT-AC7-N2."""
    gate = preview_rendered(PreviewGate(), FP)
    assert not can_start(gate, FP)


def test_approving_a_rendered_preview_allows_start() -> None:
    """TT-AC7-P2."""
    gate = approve_preview(preview_rendered(PreviewGate(), FP), FP)
    assert can_start(gate, FP)


def test_approval_before_preview_is_ready_is_rejected() -> None:
    """TT-AC7-N4."""
    with pytest.raises(PreviewNotReadyError):
        approve_preview(PreviewGate(), FP)


def test_approval_of_a_different_fingerprint_than_the_rendered_one_is_rejected() -> None:
    """TT-AC7-N4: cannot approve a preview rendered for another slot."""
    other = ApprovalFingerprint(2.0, 2.6, "t1", (0, 1, None))
    gate = preview_rendered(PreviewGate(), FP)
    with pytest.raises(PreviewNotReadyError):
        approve_preview(gate, other)


@pytest.mark.parametrize(
    "changed",
    [
        ApprovalFingerprint(1.2, 1.6, "t1", (0, 1, None)),  # slot start
        ApprovalFingerprint(1.0, 1.8, "t1", (0, 1, None)),  # slot end
        ApprovalFingerprint(1.0, 1.6, "t2", (0, 1, None)),  # template
        ApprovalFingerprint(1.0, 1.6, "t1", (1, 0, None)),  # column mapping
        ApprovalFingerprint(1.0, 1.6, "t1", (0, 1, 2)),  # spoken-name column added
    ],
)
def test_changing_slot_template_or_mapping_invalidates_approval(
    changed: ApprovalFingerprint,
) -> None:
    """TT-AC7-N6, N7, N8 (A5)."""
    gate = approve_preview(preview_rendered(PreviewGate(), FP), FP)
    assert can_start(gate, FP)
    assert not can_start(gate, changed)


def test_new_preview_and_approval_after_a_change_allows_start_again() -> None:
    """TT-AC7-E6 (A5)."""
    changed = ApprovalFingerprint(1.2, 1.6, "t1", (0, 1, None))
    gate = approve_preview(preview_rendered(PreviewGate(), FP), FP)
    gate = approve_preview(preview_rendered(gate, changed), changed)
    assert can_start(gate, changed)
    assert not can_start(gate, FP)


def test_approving_twice_is_idempotent() -> None:
    """TT-AC7-E2."""
    gate = approve_preview(preview_rendered(PreviewGate(), FP), FP)
    assert approve_preview(gate, FP) == gate

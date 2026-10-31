"""Several name slots per template over the API (DD-40).

Test IDs: MS-API-* and MS-FP-* in docs/test-tree/multi-slot-model.md.
PUT /templates/{id}/slot takes an optional ``extra_slots`` list of [start_s, end_s] pairs.
Invalid sets of slots answer 422 with the same body shape as an invalid slot (code SLOTS_INVALID
for the rules that apply to the set together; SLOT_NOT_FOUND for a single bad slot).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.fixtures.doubles import DURATION_S
from tests.integration.api.batch_helpers import (
    approve_preview,
    create_batch,
    get_batch,
    people,
    start,
    usable_template,
)
from tests.integration.api.conftest import Env
from tests.integration.api.helpers import (
    analyse,
    confirm_slot,
    get_template,
    krishan_at,
    new_template,
    set_slot,
)
from vidgen.domain.codes import FailureCode, plain_message

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
PRIMARY = (1.0, 1.6)


def put_slots(
    env: Env,
    template_id: str,
    start_s: float,
    end_s: float,
    extra: Any = None,
) -> Any:
    """PUT /templates/{id}/slot; ``extra`` is sent only when given (None omits the field)."""
    body: dict[str, Any] = {"start_s": start_s, "end_s": end_s}
    if extra is not None:
        body["extra_slots"] = extra
    return env.client.put(f"/templates/{template_id}/slot", json=body, headers=env.csrf)


def with_primary(env: Env, extra: Any = None) -> str:
    """A new template whose primary slot is 1.0-1.6, with the given extras set."""
    template_id = new_template(env)
    assert put_slots(env, template_id, *PRIMARY, extra).status_code == 200
    return template_id


def unchanged_since_primary(env: Env, template_id: str) -> None:
    """The template still has only the primary slot 1.0-1.6 and no extras."""
    body = get_template(env, template_id)
    assert body["slot"] == {"start_s": 1.0, "end_s": 1.6}
    assert body["extra_slots"] == []
    assert body["slots"] == [[1.0, 1.6]]


# ---- positive -------------------------------------------------------------------------


def test_put_with_extra_slots_then_get_shows_extras_and_all_slots(env: Env) -> None:
    """MS-API-P1."""
    template_id = new_template(env)
    response = put_slots(env, template_id, 1.0, 1.6, [[2.2, 2.8], [3.1, 3.5]])
    assert response.status_code == 200
    body = get_template(env, template_id)
    assert body["extra_slots"] == [[2.2, 2.8], [3.1, 3.5]]
    assert body["slots"] == [[1.0, 1.6], [2.2, 2.8], [3.1, 3.5]]
    assert body["slot"] == {"start_s": 1.0, "end_s": 1.6}


def test_put_and_confirm_responses_carry_extra_slots_and_slots(env: Env) -> None:
    """MS-API-P2."""
    template_id = new_template(env)
    put_body = put_slots(env, template_id, 1.0, 1.6, [[2.2, 2.8]]).json()
    assert put_body["extra_slots"] == [[2.2, 2.8]]
    assert put_body["slots"] == [[1.0, 1.6], [2.2, 2.8]]
    confirm_body = confirm_slot(env, template_id).json()
    assert confirm_body["extra_slots"] == [[2.2, 2.8]]
    assert confirm_body["slots"] == [[1.0, 1.6], [2.2, 2.8]]


def test_a_request_without_extra_slots_stores_none(env: Env) -> None:
    """MS-API-P3: the field is optional and defaults to empty."""
    template_id = new_template(env)
    assert set_slot(env, template_id, *PRIMARY).status_code == 200
    body = get_template(env, template_id)
    assert body["extra_slots"] == []
    assert body["slots"] == [[1.0, 1.6]]


def test_extras_sent_unsorted_come_back_sorted_in_slots(env: Env) -> None:
    """MS-API-P4."""
    template_id = new_template(env)
    assert put_slots(env, template_id, *PRIMARY, [[3.1, 3.5], [2.2, 2.8]]).status_code == 200
    body = get_template(env, template_id)
    assert sorted(body["extra_slots"]) == [[2.2, 2.8], [3.1, 3.5]]
    assert body["slots"] == [[1.0, 1.6], [2.2, 2.8], [3.1, 3.5]]


def test_four_extra_slots_five_in_total_are_accepted(env: Env) -> None:
    """MS-API-P5: the maximum of five slots in total."""
    template_id = new_template(env)
    extra = [[0.9, 1.3], [1.8, 2.2], [2.7, 3.1], [3.6, 4.0]]
    response = put_slots(env, template_id, 0.0, 0.4, extra)
    assert response.status_code == 200
    assert len(get_template(env, template_id)["slots"]) == 5


def test_an_extra_slot_ending_at_the_video_duration_is_accepted(env: Env) -> None:
    """MS-API-P6."""
    template_id = new_template(env)
    response = put_slots(env, template_id, *PRIMARY, [[3.0, DURATION_S]])
    assert response.status_code == 200


def test_gap_of_exactly_point_two_seconds_is_accepted(env: Env) -> None:
    """MS-API-P7: primary ends at 2.0, extra starts at 2.2."""
    template_id = new_template(env)
    response = put_slots(env, template_id, 1.0, 2.0, [[2.2, 2.8]])
    assert response.status_code == 200


def test_listing_shows_extra_slots_and_slots_for_every_template(env: Env) -> None:
    """MS-API-P8."""
    template_id = with_primary(env, [[2.2, 2.8]])
    listing = env.client.get("/templates").json()["templates"]
    entry = next(t for t in listing if t["id"] == template_id)
    assert entry["extra_slots"] == [[2.2, 2.8]]
    assert entry["slots"] == [[1.0, 1.6], [2.2, 2.8]]


def test_a_new_template_has_empty_extra_slots_and_slots(env: Env) -> None:
    """MS-API-P9."""
    template_id = new_template(env)
    body = get_template(env, template_id)
    assert body["extra_slots"] == []
    assert body["slots"] == []
    assert body["slot"] is None


def test_analyse_clears_the_extra_slots(env: Env) -> None:
    """MS-API-P10: automatic detection replaces the whole slot set with its own result."""
    template_id = with_primary(env, [[2.2, 2.8]])
    env.stt.words = [krishan_at(1.0)]
    assert analyse(env, template_id).status_code == 200
    body = get_template(env, template_id)
    assert body["extra_slots"] == []
    assert body["slots"] == [[1.0, 1.4]]


def test_changing_only_an_extra_slot_unconfirms_a_confirmed_slot(env: Env) -> None:
    """MS-API-P11: the confirmed set is no longer the one that was confirmed."""
    template_id = usable_template(env)
    assert get_template(env, template_id)["usable"] is True
    assert put_slots(env, template_id, *PRIMARY, [[2.2, 2.8]]).status_code == 200
    body = get_template(env, template_id)
    assert body["slot_confirmed"] is False
    assert body["usable"] is False


# ---- negative -------------------------------------------------------------------------


def test_overlapping_extra_slot_is_422_slots_invalid_and_nothing_changes(env: Env) -> None:
    """MS-API-N1."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, [[1.5, 2.0]])
    assert response.status_code == 422
    assert response.json() == {
        "code": "SLOTS_INVALID",
        "message": plain_message(FailureCode.SLOTS_INVALID),
    }
    unchanged_since_primary(env, template_id)


def test_gap_of_point_nineteen_seconds_is_422_slots_invalid(env: Env) -> None:
    """MS-API-N2."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, [[1.79, 2.4]])
    assert response.status_code == 422
    assert response.json()["code"] == "SLOTS_INVALID"
    unchanged_since_primary(env, template_id)


def test_touching_slots_are_422_slots_invalid(env: Env) -> None:
    """MS-API-N3."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, [[1.6, 2.2]])
    assert response.status_code == 422
    assert response.json()["code"] == "SLOTS_INVALID"
    unchanged_since_primary(env, template_id)


def test_extra_slot_beyond_the_duration_is_422_slot_not_found(env: Env) -> None:
    """MS-API-N4: the single-slot rule, same body as an invalid slot today."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, [[3.5, 4.5]])
    assert response.status_code == 422
    assert response.json() == {
        "code": "SLOT_NOT_FOUND",
        "message": plain_message(FailureCode.SLOT_NOT_FOUND),
    }
    unchanged_since_primary(env, template_id)


def test_six_slots_in_total_are_422_and_nothing_changes(env: Env) -> None:
    """MS-API-N5: five extras plus the primary; the request is refused as too many."""
    template_id = with_primary(env)
    extra = [[2.2, 2.3], [2.5, 2.6], [2.8, 2.9], [3.1, 3.2], [3.4, 3.5]]
    response = put_slots(env, template_id, *PRIMARY, extra)
    assert response.status_code == 422
    unchanged_since_primary(env, template_id)


@pytest.mark.parametrize(
    "raw_extra",
    [
        b"[[2.0]]",
        b"[[2.0, 2.6, 3.0]]",
        b'[["a", "b"]]',
        b"[[2.0, null]]",
        b"[2.0, 2.6]",
        b'[{"start_s": 2.0, "end_s": 2.6}]',
        b"[[NaN, 2.6]]",
        b'"abc"',
    ],
)
def test_malformed_extra_slots_are_422_validation_error_and_nothing_changes(
    env: Env, raw_extra: bytes
) -> None:
    """MS-API-N6, MS-API-N7: each item must be exactly two numbers; the field must be a list."""
    template_id = with_primary(env)
    body = b'{"start_s": 1.0, "end_s": 1.6, "extra_slots": ' + raw_extra + b"}"
    response = env.client.put(
        f"/templates/{template_id}/slot",
        content=body,
        headers={**env.csrf, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    unchanged_since_primary(env, template_id)


def test_put_with_extras_for_an_unknown_template_is_404(env: Env) -> None:
    """MS-API-N8."""
    response = put_slots(env, UNKNOWN_ID, *PRIMARY, [[2.2, 2.8]])
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---- edge -----------------------------------------------------------------------------


def test_extra_slot_equal_to_the_primary_is_an_overlap(env: Env) -> None:
    """MS-API-E1."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, [[1.0, 1.6]])
    assert response.status_code == 422
    assert response.json()["code"] == "SLOTS_INVALID"
    unchanged_since_primary(env, template_id)


@pytest.mark.parametrize("extra", [[[2.0, 2.0]], [[2.6, 2.0]]], ids=["zero-length", "reversed"])
def test_zero_length_or_reversed_extra_slot_is_422_slot_not_found(env: Env, extra: Any) -> None:
    """MS-API-E2: each slot must pass validate_slot on its own."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, extra)
    assert response.status_code == 422
    assert response.json()["code"] == "SLOT_NOT_FOUND"
    unchanged_since_primary(env, template_id)


def test_extras_given_out_of_order_that_overlap_once_sorted_are_refused(env: Env) -> None:
    """MS-API-E3."""
    template_id = with_primary(env)
    response = put_slots(env, template_id, *PRIMARY, [[2.5, 3.0], [2.2, 2.8]])
    assert response.status_code == 422
    assert response.json()["code"] == "SLOTS_INVALID"
    unchanged_since_primary(env, template_id)


def test_an_empty_extra_slots_list_behaves_like_no_extras(env: Env) -> None:
    """MS-API-E4."""
    template_id = new_template(env)
    assert put_slots(env, template_id, *PRIMARY, []).status_code == 200
    body = get_template(env, template_id)
    assert body["extra_slots"] == []
    assert body["slots"] == [[1.0, 1.6]]


# ---- approval goes stale on an extra-only change (A5) ---------------------------------


def test_re_sending_the_same_extras_keeps_an_approved_preview(env: Env) -> None:
    """MS-FP-P1: an unchanged fingerprint keeps the approval."""
    template_id = usable_template(env)
    batch_id = create_batch(env, template_id, people(2)).json()["id"]
    approve_preview(env, batch_id)
    assert put_slots(env, template_id, 1.0, 1.6, []).status_code == 200
    assert get_batch(env, batch_id)["preview"]["approved"] is True


def test_changing_only_an_extra_slot_makes_the_approved_preview_stale(env: Env) -> None:
    """MS-FP-N1, MS-FP-N2: the primary slot is unchanged; only an extra slot moves."""
    template_id = usable_template(env)
    batch_id = create_batch(env, template_id, people(2)).json()["id"]
    approve_preview(env, batch_id)
    assert put_slots(env, template_id, 1.0, 1.6, [[2.2, 2.8]]).status_code == 200
    assert get_batch(env, batch_id)["preview"]["approved"] is False
    response = start(env, batch_id)
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_NOT_APPROVED"


def test_extra_slots_are_part_of_the_slot_set_a_template_confirms(env: Env) -> None:
    """MS-FP-E1 (API side): after an extra-only change the batch needs a new preview."""
    template_id = usable_template(env)
    batch_id = create_batch(env, template_id, people(2)).json()["id"]
    approve_preview(env, batch_id)
    assert put_slots(env, template_id, 1.0, 1.6, [[2.2, 2.8]]).status_code == 200
    assert confirm_slot(env, template_id).status_code == 200
    assert get_batch(env, batch_id)["preview"]["approved"] is False
    approve_preview(env, batch_id)
    assert start(env, batch_id).status_code == 200

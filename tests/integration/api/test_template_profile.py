"""Template analysis, slot and content lock (AC6, AC18, C3, D-1)."""

from __future__ import annotations

import pytest

from tests.fixtures.doubles import CANARY_NAME, DURATION_S, word
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import (
    analyse,
    audit_actions,
    confirm_slot,
    get_template,
    give_consent,
    krishan_at,
    new_template,
    set_slot,
)
from vidgen.domain.codes import FailureCode, plain_message

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
DEVANAGARI_NAME = "\u0915\u0943\u0937\u094d\u0923"  # a name written in Devanagari


# ---- analysis: positive ---------------------------------------------------------------


def test_analysis_locates_the_original_name_with_its_timestamps(env: Env) -> None:
    """TT-AC6-P1: the slot is the spoken voter name, not the word 'ji'."""
    env.stt.words = [word("namaste", 0.0), krishan_at(1.0), word("ji", 1.5)]
    template_id = new_template(env)
    response = analyse(env, template_id)
    assert response.status_code == 200
    body = response.json()
    assert body["slot"] == {"start_s": 1.0, "end_s": 1.4}
    assert body["slot_source"] == "AUTO"
    assert body["slot_confidence"] == pytest.approx(0.95)
    assert body["slot_confirmed"] is False
    assert body["needs_manual_slot"] is False
    assert env.stt.calls == 1


def test_matching_ignores_case_and_surrounding_punctuation(env: Env) -> None:
    """The match is case-insensitive; the spoken form 'krishan,' counts."""
    env.stt.words = [word("krishan,", 2.0)]
    template_id = new_template(env)
    assert analyse(env, template_id).json()["slot"]["start_s"] == 2.0


def test_the_word_ji_is_never_selected_unless_it_is_the_original_name(env: Env) -> None:
    """The title 'ji' follows the name and must stay untouched."""
    env.stt.words = [word("ji", 1.5, 0.99)]
    template_id = new_template(env)
    body = analyse(env, template_id).json()
    assert body["slot"] is None
    assert body["needs_manual_slot"] is True


def test_ji_can_be_the_original_name_if_the_template_says_so(env: Env) -> None:
    """The original name is per template, whatever it is."""
    env.stt.words = [word("ji", 1.5, 0.99)]
    template_id = new_template(env, original_name="ji")
    assert analyse(env, template_id).json()["slot"]["start_s"] == 1.5


def test_devanagari_original_name_matches_the_same_devanagari_transcript_word(env: Env) -> None:
    """Devanagari-aware: exact match after case-folding and punctuation stripping."""
    env.stt.words = [word(DEVANAGARI_NAME, 1.0)]
    template_id = new_template(env, original_name=DEVANAGARI_NAME)
    assert analyse(env, template_id).json()["slot"]["start_s"] == 1.0


def test_no_transliteration_in_m1_so_a_script_mismatch_needs_a_manual_slot(env: Env) -> None:
    """Documented limit: 'Krishan' (Latin) does not match the Devanagari transcript word."""
    env.stt.words = [word(DEVANAGARI_NAME, 1.0)]
    template_id = new_template(env)  # original_name "Krishan"
    body = analyse(env, template_id).json()
    assert body["needs_manual_slot"] is True
    assert body["slot_error"] == "SLOT_NOT_FOUND"


def test_analysis_result_is_reused_without_calling_stt_again(env: Env) -> None:
    """TT-AC6-P3: the profile is stored and reused."""
    env.stt.words = [krishan_at(1.0)]
    template_id = new_template(env)
    analyse(env, template_id)
    again = analyse(env, template_id)
    assert again.status_code == 200
    assert again.json()["slot"] == {"start_s": 1.0, "end_s": 1.4}
    assert env.stt.calls == 1
    get_template(env, template_id)
    assert env.stt.calls == 1


def test_force_runs_the_analysis_again_and_replaces_the_profile(env: Env) -> None:
    """TT-AC6-E5: explicit re-analysis, audited."""
    env.stt.words = [krishan_at(1.0)]
    template_id = new_template(env)
    analyse(env, template_id)
    env.stt.words = [krishan_at(2.0)]
    body = analyse(env, template_id, force=True).json()
    assert body["slot"]["start_s"] == 2.0
    assert env.stt.calls == 2
    assert audit_actions(env).count("TEMPLATE_ANALYSED") == 2


def test_manual_slot_inside_the_video_is_accepted(env: Env) -> None:
    """TT-AC6-P2."""
    template_id = new_template(env)
    response = set_slot(env, template_id, 1.0, 1.6)
    assert response.status_code == 200
    body = response.json()
    assert body["slot"] == {"start_s": 1.0, "end_s": 1.6}
    assert body["slot_source"] == "MANUAL"
    assert body["slot_confirmed"] is False


def test_confirming_the_slot_marks_the_profile_confirmed_and_audits_it(env: Env) -> None:
    """TT-AC6-P2, C4."""
    template_id = new_template(env)
    set_slot(env, template_id, 1.0, 1.6)
    response = confirm_slot(env, template_id)
    assert response.status_code == 200
    assert response.json()["slot_confirmed"] is True
    assert "SLOT_CONFIRMED" in audit_actions(env)


def test_template_with_consent_and_confirmed_slot_is_usable(env: Env) -> None:
    """TT-AC6-P3, AC5-P4."""
    template_id = new_template(env)
    give_consent(env, template_id)
    set_slot(env, template_id, 1.0, 1.6)
    confirm_slot(env, template_id)
    assert get_template(env, template_id)["usable"] is True


# ---- analysis: negative ---------------------------------------------------------------


def test_low_confidence_match_needs_a_manual_slot(env: Env) -> None:
    """TT-AC6-N1."""
    env.stt.words = [krishan_at(1.0, confidence=0.59)]
    template_id = new_template(env)
    response = analyse(env, template_id)
    assert response.status_code == 200
    body = response.json()
    assert body["slot"] is None
    assert body["needs_manual_slot"] is True
    assert body["slot_error"] == "SLOT_NOT_FOUND"
    assert body["usable"] is False


def test_name_not_in_the_transcript_needs_a_manual_slot(env: Env) -> None:
    """TT-AC6-N2."""
    env.stt.words = [word("namaste", 0.0), word("aap", 1.0)]
    template_id = new_template(env)
    body = analyse(env, template_id).json()
    assert body["needs_manual_slot"] is True
    assert body["slot_error"] == "SLOT_NOT_FOUND"


def test_empty_transcript_needs_a_manual_slot(env: Env) -> None:
    """TT-AC6-N2."""
    env.stt.words = []
    template_id = new_template(env)
    assert analyse(env, template_id).json()["needs_manual_slot"] is True


@pytest.mark.parametrize(
    ("start", "end"),
    [(1.0, DURATION_S + 0.001), (2.0, 2.0), (2.0, 1.0), (-0.1, 1.0), (0.0, 99.0)],
)
def test_invalid_manual_slots_are_refused_and_change_nothing(
    env: Env, start: float, end: float
) -> None:
    """TT-AC6-N3, N4, E1 (D-1): end beyond the video, zero length, reversed, negative."""
    template_id = new_template(env)
    set_slot(env, template_id, 1.0, 1.6)
    response = set_slot(env, template_id, start, end)
    assert response.status_code == 422
    assert response.json() == {
        "code": "SLOT_NOT_FOUND",
        "message": plain_message(FailureCode.SLOT_NOT_FOUND),
    }
    assert get_template(env, template_id)["slot"] == {"start_s": 1.0, "end_s": 1.6}


@pytest.mark.parametrize(
    "body", [b'{"start_s": NaN, "end_s": 1.0}', b'{"start_s": 1.0, "end_s": Infinity}']
)
def test_non_finite_slot_numbers_are_refused(env: Env, body: bytes) -> None:
    """TT-AC6-N4."""
    template_id = new_template(env)
    response = env.client.put(
        f"/templates/{template_id}/slot",
        content=body,
        headers={**env.csrf, "Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [{}, {"start_s": 1.0}, {"start_s": "a", "end_s": "b"}])
def test_slot_with_missing_or_non_numeric_fields_is_a_validation_error(
    env: Env, payload: dict[str, object]
) -> None:
    """TT-AC6-N4."""
    template_id = new_template(env)
    response = env.client.put(f"/templates/{template_id}/slot", json=payload, headers=env.csrf)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_slot_covering_the_whole_video_is_accepted(env: Env) -> None:
    """TT-AC6-E1."""
    template_id = new_template(env)
    assert set_slot(env, template_id, 0.0, DURATION_S).status_code == 200


def test_stt_failure_is_502_stt_failed_without_leaking_details(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    """TT-AC6-N5, TT-AC17-N4: a name inside the error text must not reach client or logs."""
    env.stt.error = RuntimeError(f"model crashed on {CANARY_NAME}")
    template_id = new_template(env)
    response = analyse(env, template_id)
    assert response.status_code == 502
    assert response.json() == {
        "code": "STT_FAILED",
        "message": plain_message(FailureCode.STT_FAILED),
    }
    assert CANARY_NAME not in response.text
    assert CANARY_NAME not in caplog.text
    body = get_template(env, template_id)
    assert body["slot"] is None
    assert body["slot_confirmed"] is False


def test_confirming_without_any_slot_is_409(env: Env) -> None:
    """TT-AC6-N6."""
    template_id = new_template(env)
    response = confirm_slot(env, template_id)
    assert response.status_code == 409
    assert response.json()["code"] == "SLOT_NOT_FOUND"


def test_template_without_consent_is_unusable_even_with_a_confirmed_slot(env: Env) -> None:
    """TT-AC5-N1, AC6-N6."""
    template_id = new_template(env)
    set_slot(env, template_id, 1.0, 1.6)
    confirm_slot(env, template_id)
    assert get_template(env, template_id)["usable"] is False


@pytest.mark.parametrize("path", ["analyse", "slot/confirm"])
def test_unknown_template_is_404_for_profile_actions(env: Env, path: str) -> None:
    """TT-AC6-N6."""
    response = env.client.post(f"/templates/{UNKNOWN_ID}/{path}", headers=env.csrf)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert set_slot(env, UNKNOWN_ID, 1.0, 1.6).status_code == 404


# ---- content lock (AC18) --------------------------------------------------------------


# DELETE is the delete-template route since DD-37; it is covered in test_template_delete.py.
@pytest.mark.parametrize("method", ["PATCH", "PUT"])
def test_the_slot_cannot_be_changed_through_the_template_resource(env: Env, method: str) -> None:
    """TT-AC18-E6: slot changes exist only on the slot endpoints."""
    template_id = new_template(env)
    set_slot(env, template_id, 1.0, 1.6)
    response = env.client.request(
        method,
        f"/templates/{template_id}",
        json={"slot": {"start_s": 0.0, "end_s": 3.0}},
        headers=env.csrf,
    )
    assert response.status_code in (404, 405)
    assert get_template(env, template_id)["slot"] == {"start_s": 1.0, "end_s": 1.6}


def test_changing_the_slot_after_confirmation_requires_a_new_confirmation(env: Env) -> None:
    """TT-AC18-E4, plan A5: an edited slot is unconfirmed and the template unusable again."""
    template_id = new_template(env)
    give_consent(env, template_id)
    set_slot(env, template_id, 1.0, 1.6)
    confirm_slot(env, template_id)
    assert get_template(env, template_id)["usable"] is True
    set_slot(env, template_id, 1.1, 1.7)
    body = get_template(env, template_id)
    assert body["slot"] == {"start_s": 1.1, "end_s": 1.7}
    assert body["slot_confirmed"] is False
    assert body["usable"] is False
    assert audit_actions(env).count("SLOT_SET") == 2


# ---- C3 tie-break and threshold -------------------------------------------------------


def test_several_matches_pick_the_highest_confidence(env: Env) -> None:
    """TT-AC6-E2 (C3)."""
    env.stt.words = [krishan_at(1.0, 0.7), krishan_at(5.0, 0.95), krishan_at(9.0, 0.8)]
    template_id = new_template(env)
    assert analyse(env, template_id).json()["slot"]["start_s"] == 5.0


def test_equal_confidence_picks_the_earliest(env: Env) -> None:
    """TT-AC6-E2 (C3)."""
    env.stt.words = [krishan_at(9.0, 0.9), krishan_at(1.0, 0.9), krishan_at(5.0, 0.9)]
    template_id = new_template(env)
    assert analyse(env, template_id).json()["slot"]["start_s"] == 1.0


def test_confidence_exactly_at_the_threshold_counts_as_found(env: Env) -> None:
    """TT-AC6-E3 (C3): inclusive threshold from settings (default 0.6)."""
    env.stt.words = [krishan_at(1.0, 0.6)]
    template_id = new_template(env)
    assert analyse(env, template_id).json()["needs_manual_slot"] is False


def test_threshold_comes_from_settings(make_env: EnvFactory) -> None:
    """TT-AC6-E3."""
    env = make_env(stt_confidence_threshold=0.9)
    env.stt.words = [krishan_at(1.0, 0.8)]
    template_id = new_template(env)
    assert analyse(env, template_id).json()["needs_manual_slot"] is True


# ---- csrf on profile actions ----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("POST", "analyse"), ("PUT", "slot"), ("POST", "slot/confirm"), ("POST", "consent")],
)
def test_profile_actions_need_the_csrf_token(env: Env, method: str, suffix: str) -> None:
    """TT-AC16-N2."""
    template_id = new_template(env)
    response = env.client.request(method, f"/templates/{template_id}/{suffix}")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"

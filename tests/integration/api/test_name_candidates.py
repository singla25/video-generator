"""Analyse with sound-alike matching: candidates only in the response (AC2-AC4, AC6, AC8)."""

from __future__ import annotations

from typing import Any

from tests.fixtures.doubles import word
from tests.integration.api.conftest import Env, EnvFactory
from tests.integration.api.helpers import (
    analyse,
    get_template,
    krishan_at,
    new_template,
)
from vidgen.domain.values import Word

UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
CANDIDATE_KEYS = {"text", "start_s", "end_s", "closeness", "confidence"}


def run(env: Env, words: list[Word], **kwargs: Any) -> dict[str, Any]:
    env.stt.words = words
    template_id = new_template(env, **kwargs)
    response = analyse(env, template_id)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    body["_id"] = template_id
    return body


# ---- positive -------------------------------------------------------------------------


def test_devanagari_word_for_a_roman_name_is_found(env: Env) -> None:
    body = run(env, [word("namaste", 0.0), word("कृष्ण", 1.0)])
    assert body["slot"]["start_s"] == 1.0
    assert body["needs_manual_slot"] is False
    assert body["candidates"] == []


def test_exact_match_still_works(env: Env) -> None:
    body = run(env, [krishan_at(2.0)])
    assert body["slot"] == {"start_s": 2.0, "end_s": 2.4}
    assert body["candidates"] == []


def test_found_slot_stays_unconfirmed(env: Env) -> None:
    body = run(env, [word("किशन", 1.0)])
    assert body["slot"] is not None
    assert body["slot_confirmed"] is False


def test_low_confidence_close_word_is_a_candidate_not_a_slot(env: Env) -> None:
    body = run(env, [word("Krishan", 1.0, 0.3)])
    assert body["slot"] is None
    assert body["needs_manual_slot"] is True
    assert body["slot_confirmed"] is False
    assert body["candidates"] == [
        {"text": "Krishan", "start_s": 1.0, "end_s": 1.4, "closeness": 1.0, "confidence": 0.3}
    ]


def test_candidates_are_best_first_at_most_three_with_the_agreed_fields(env: Env) -> None:
    words = [word("Krishan", float(i), 0.1 + i / 100) for i in range(5)]
    body = run(env, words)
    candidates = body["candidates"]
    assert len(candidates) == 3
    assert all(set(c) == CANDIDATE_KEYS for c in candidates)
    assert [c["start_s"] for c in candidates] == [4.0, 3.0, 2.0]


def test_closeness_and_confidence_are_rounded_to_three_decimals(env: Env) -> None:
    body = run(env, [word("Kishan", 1.0, 0.123456)], original_name="Krishan")
    (candidate,) = body["candidates"]
    assert candidate["confidence"] == 0.123
    assert candidate["closeness"] == round(candidate["closeness"], 3)
    assert 0.4 <= candidate["closeness"] <= 1.0


def test_the_typed_name_is_passed_to_speech_to_text_as_the_hint(env: Env) -> None:
    run(env, [krishan_at(1.0)], original_name="Krishan")
    assert env.stt.hints == ["Krishan"]


def test_a_devanagari_typed_name_is_passed_as_typed(env: Env) -> None:
    run(env, [word("कृष्ण", 1.0)], original_name="कृष्ण")
    assert env.stt.hints == ["कृष्ण"]


def test_closeness_threshold_comes_from_settings(make_env: EnvFactory) -> None:
    env = make_env(name_match_threshold=1.0)
    body = run(env, [word("Kishan", 1.0)])
    assert body["slot"] is None
    assert [c["text"] for c in body["candidates"]] == ["Kishan"]


# ---- negative -------------------------------------------------------------------------


def test_unrelated_words_give_not_found_and_no_candidates(env: Env) -> None:
    body = run(env, [word("Zzzz", 1.0), word("namaste", 2.0)])
    assert body["slot"] is None
    assert body["needs_manual_slot"] is True
    assert body["candidates"] == []


def test_empty_transcript_gives_not_found_and_no_candidates(env: Env) -> None:
    body = run(env, [])
    assert body["slot"] is None and body["candidates"] == []


def test_analyse_needs_a_session(anon: Env) -> None:
    response = anon.client.post(f"/templates/{UNKNOWN_ID}/analyse")
    assert response.status_code == 401


def test_analyse_of_an_unknown_template_is_refused_clearly(env: Env) -> None:
    response = analyse(env, UNKNOWN_ID)
    assert response.status_code == 404
    assert "candidates" not in response.json()


# ---- edge -----------------------------------------------------------------------------


def test_candidates_are_not_stored_and_absent_on_get(env: Env) -> None:
    body = run(env, [word("Krishan", 1.0, 0.3)])
    assert body["candidates"]
    stored = get_template(env, body["_id"])
    assert stored.get("candidates", []) == []
    assert stored["slot"] is None


def test_candidates_are_not_stored_in_any_new_database_column(env: Env, db: Any) -> None:
    from sqlalchemy import inspect

    columns = {c["name"] for c in inspect(db).get_columns("templates")}
    assert not any("candidate" in name for name in columns)


def test_reanalysing_replaces_an_earlier_candidate_list(env: Env) -> None:
    body = run(env, [word("Krishan", 1.0, 0.3)])
    env.stt.words = [krishan_at(2.0)]
    again = analyse(env, body["_id"], force=True).json()
    assert again["candidates"] == []
    assert again["slot"]["start_s"] == 2.0


def test_a_single_character_typed_name_is_not_matched_loosely(env: Env) -> None:
    body = run(env, [word("Ka", 1.0), word("Ko", 2.0)], original_name="K")
    assert body["slot"] is None
    assert body["candidates"] == []


def test_punctuation_only_typed_name_finds_nothing_and_does_not_crash(env: Env) -> None:
    body = run(env, [word("Krishan", 1.0)], original_name="!!!")
    assert body["slot"] is None and body["candidates"] == []

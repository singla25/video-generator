"""Adversarial false-positive check (AC1): common but DIFFERENT Indian first names, made up.

Each name is tried in Roman and Devanagari against the targets Krishan, Rahul and Aman.
Names of other people must stay below the default threshold 0.8.
The exceptions are true spelling variants of the target (Krishan/Krishn/Kishan/Krishna/
Kirshan are one name written differently), listed explicitly as expected matches.
"""

from __future__ import annotations

import pytest

from vidgen.domain.name_match import closeness, sound_key

THRESHOLD = 0.8

# (Roman, Devanagari) of other people's common first names.
OTHER_NAMES: list[tuple[str, str]] = [
    ("Rahul", "राहुल"), ("Aman", "अमन"), ("Gurpreet", "गुरप्रीत"), ("Sita", "सीता"),
    ("Pappu", "पप्पू"), ("Sushila", "सुशीला"), ("Javed", "जावेद"), ("Mumtaz", "मुमताज"),
    ("Santosh", "संतोष"), ("Rekha", "रेखा"), ("Mohan", "मोहन"), ("Sohan", "सोहन"),
    ("Rohan", "रोहन"), ("Ramesh", "रमेश"), ("Suresh", "सुरेश"), ("Mahesh", "महेश"),
    ("Naresh", "नरेश"), ("Anil", "अनिल"), ("Sunil", "सुनील"), ("Vijay", "विजय"),
    ("Deepak", "दीपक"), ("Pooja", "पूजा"), ("Priya", "प्रिया"), ("Geeta", "गीता"),
    ("Kavita", "कविता"), ("Lakshmi", "लक्ष्मी"), ("Sanjay", "संजय"), ("Ajay", "अजय"),
    ("Manoj", "मनोज"), ("Dinesh", "दिनेश"), ("Ramu", "रामू"), ("Raman", "रमन"),
    ("Amar", "अमर"), ("Aryan", "आर्यन"), ("Harish", "हरीश"), ("Karan", "करण"),
    ("Kiran", "किरण"), ("Sachin", "सचिन"), ("Nitin", "नितिन"), ("Ravi", "रवि"),
    ("Sunita", "सुनीता"), ("Anita", "अनीता"),
]  # fmt: skip

# Spelling variants of the target: the same name, so a match is the RIGHT answer.
VARIANTS: dict[str, list[str]] = {
    "Krishan": ["Krishn", "Kishan", "Krishna", "Kirshan", "कृष्ण", "कृष्णा", "किशन", "किरशन"],
    "Rahul": ["राहुल", "Rahool"],
    "Aman": ["अमन", "Amaan"],
}
TARGETS = list(VARIANTS)


def _is_variant(target: str, heard: str) -> bool:
    return heard in VARIANTS[target] or heard.casefold() == target.casefold()


def _unrelated_pairs() -> list[tuple[str, str]]:
    return [(t, h) for t in TARGETS for pair in OTHER_NAMES for h in pair if not _is_variant(t, h)]


@pytest.mark.parametrize(("target", "heard"), _unrelated_pairs())
def test_a_different_persons_name_stays_below_the_threshold(target: str, heard: str) -> None:
    assert closeness(target, heard) < THRESHOLD, (target, heard, closeness(target, heard))


@pytest.mark.parametrize(("target", "heard"), [(t, v) for t, vs in VARIANTS.items() for v in vs])
def test_a_spelling_variant_of_the_target_is_accepted(target: str, heard: str) -> None:
    assert closeness(target, heard) >= THRESHOLD, (target, heard)


def test_closest_unrelated_pair_is_reported_and_below_threshold() -> None:
    """Documents the worst near miss (Krishan vs Kishan-like Kiran/Karan scored 0.75)."""
    best = max(_unrelated_pairs(), key=lambda p: closeness(*p))
    assert closeness(*best) < THRESHOLD
    assert closeness(*best) > 0.7  # guards against the probe going silent


def test_a_lone_digit_token_has_a_sound_key_of_its_own() -> None:
    assert sound_key("7") == "7"


def test_devanagari_visarga_sounds_like_h() -> None:
    assert sound_key("\u0903") == "h"

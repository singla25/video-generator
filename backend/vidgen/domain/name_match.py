"""Sound-alike matching of a typed name against heard words, across Roman and Devanagari.

Pure Python, deterministic, no I/O. A word becomes a "sound skeleton" (``sound_key``); two
skeletons are compared with a weighted edit distance (``closeness``, 0 to 1). ``select_name_slot``
applies the accept rule (closeness AND speech-to-text confidence) and lists near misses so a
person can pick one instead of marking the time by hand.
"""

from __future__ import annotations

import functools
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.domain import name_sounds as sounds
from vidgen.domain.values import Word

# Below this closeness a word is not worth showing as a candidate.
MIN_CANDIDATE_CLOSENESS = 0.4
DEFAULT_MAX_CANDIDATES = 3
# A typed name of fewer characters than this is refused (a single letter matches too much) ...
MIN_TARGET_CHARS = 2
# ... and a skeleton shorter than this needs an exact skeleton match, with no candidates.
LOOSE_KEY_LENGTH = 3
WEAK_COST = 0.5
SIMILAR_COST = 0.5


@dataclass(frozen=True, slots=True)
class ScoredWord:
    """A heard word with its closeness to the typed name."""

    word: Word
    closeness: float


@dataclass(frozen=True, slots=True)
class NameMatch:
    """Outcome of ``select_name_slot``: the chosen word, or the closest near misses."""

    found: Word | None
    candidates: tuple[ScoredWord, ...]


def _tokens(text: str) -> list[str]:
    """Characters that can carry sound: Devanagari and digits as they are, Latin letters
    reduced to plain a-z (accents stripped). Everything else (spaces, punctuation, emoji,
    other scripts, zero-width characters) is dropped."""
    out: list[str] = []
    for char in unicodedata.normalize("NFC", text).casefold():
        if "\u0900" <= char <= "\u097f":
            out.append(char)
        elif char.isdigit():
            out.append(str(unicodedata.digit(char, 0)))
        else:
            out.extend(
                c for c in unicodedata.normalize("NFKD", char) if c.isascii() and c.isalpha()
            )
    return out


def _sound_of(char: str, started: bool) -> str:
    """Skeleton letters for one token; "" when it carries no sound for the skeleton."""
    if char in sounds.SILENT:
        return ""
    if char in sounds.DEVANAGARI_LETTERS:
        return sounds.DEVANAGARI_LETTERS[char]
    if char in sounds.DEVANAGARI_RI:
        return "r"
    if char in sounds.DEVANAGARI_NASALS:
        return "n"
    if char == sounds.DEVANAGARI_VISARGA:
        return "h"
    if char in sounds.DEVANAGARI_VOWELS or char in sounds.ROMAN_VOWELS:
        return "" if started else sounds.LEADING_VOWEL
    if char in sounds.ROMAN_LETTERS:
        return sounds.ROMAN_LETTERS[char]
    return char if char.isdigit() else ""


def _skeleton(text: str) -> list[str]:
    """Sound letters of ``text`` in order, before repeated sounds are collapsed."""
    tokens = _tokens(text)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        pair = "".join(tokens[i : i + 2])
        if pair in sounds.ROMAN_DIGRAPHS:
            out.append(sounds.ROMAN_DIGRAPHS[pair])
            i += 2
            continue
        out.append(_sound_of(tokens[i], started=any(out)))
        i += 1
    return out


@functools.lru_cache(maxsize=8192)
def sound_key(text: str) -> str:
    """Sound skeleton of ``text``: the same for equal-sounding Roman and Devanagari spellings.

    Case, punctuation, spaces, zero-width characters, nukta and emoji are ignored; repeated
    sounds collapse. Text with no sound at all gives "".
    """
    key: list[str] = []
    for part in "".join(_skeleton(text)):
        if not key or key[-1] != part:
            key.append(part)
    return "".join(key)


def _substitution_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if any(a in group and b in group for group in sounds.SIMILAR_GROUPS):
        return SIMILAR_COST
    return 1.0


def _skip_cost(letter: str) -> float:
    return WEAK_COST if letter in sounds.WEAK_LETTERS else 1.0


@functools.lru_cache(maxsize=65536)
def _closeness_of_keys(a: str, b: str) -> float:
    """Weighted edit distance between two keys, turned into a 0 to 1 similarity."""
    previous = [0.0]
    for letter in b:
        previous.append(previous[-1] + _skip_cost(letter))
    for x in a:
        row = [previous[0] + _skip_cost(x)]
        for j, y in enumerate(b, start=1):
            row.append(
                min(
                    previous[j] + _skip_cost(x),
                    row[j - 1] + _skip_cost(y),
                    previous[j - 1] + _substitution_cost(x, y),
                )
            )
        previous = row
    return max(0.0, 1.0 - previous[-1] / max(len(a), len(b)))


def closeness(a: str, b: str) -> float:
    """How alike two words sound, 0.0 to 1.0 (symmetric); 0.0 if either has no sound."""
    key_a, key_b = sound_key(a), sound_key(b)
    if not key_a or not key_b:
        return 0.0
    if key_a == key_b:
        return 1.0
    return _closeness_of_keys(*sorted((key_a, key_b)))


def _rank(item: ScoredWord) -> tuple[float, float, float]:
    """Best first: closeness, then confidence, then earliest."""
    return (-item.closeness, -item.word.confidence, item.word.start_s)


def select_name_slot(
    words: Sequence[Word],
    target: str,
    *,
    confidence_threshold: float,
    closeness_threshold: float,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> NameMatch:
    """Pick the heard word that sounds like ``target``, or list the closest near misses.

    A word is chosen only if closeness >= ``closeness_threshold`` AND confidence >=
    ``confidence_threshold`` (both inclusive). Otherwise up to ``max_candidates`` words with
    closeness >= MIN_CANDIDATE_CLOSENESS are returned, best first; they are never chosen
    automatically. A one-character target is refused; a target with fewer than three sounds
    needs an exact skeleton match and gives no candidates (too little to compare loosely).
    """
    target_key = sound_key(target)
    if not target_key or len(_tokens(target)) < MIN_TARGET_CHARS:
        return NameMatch(None, ())
    strict = len(target_key) < LOOSE_KEY_LENGTH
    scored = [ScoredWord(w, closeness(target, w.text)) for w in words]
    scored = [s for s in scored if s.closeness > 0.0]
    accepted = [
        s
        for s in scored
        if s.word.confidence >= confidence_threshold
        and s.closeness >= (1.0 if strict else closeness_threshold)
    ]
    if accepted:
        return NameMatch(min(accepted, key=_rank).word, ())
    if strict:
        return NameMatch(None, ())
    near = sorted((s for s in scored if s.closeness >= MIN_CANDIDATE_CLOSENESS), key=_rank)
    return NameMatch(None, tuple(near[:max_candidates]))

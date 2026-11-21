"""Spelling tables for the sound skeleton (Roman and Devanagari map to the same letters).

Why a skeleton of consonants: Hindi names are written with many equivalent spellings
("Krishan", "Krishn", "Kishan", "कृष्ण"). Vowel length, matras and the hidden schwa differ
between spellings and between speakers, while the consonants stay stable. So vowels are
dropped (except a leading one, kept as ``a``) and similar consonants share one letter.
"""

from __future__ import annotations

# Letter used for a name that starts with a vowel ("Anil", "अनिल"): the only vowel we keep.
LEADING_VOWEL = "a"

# Characters that carry no sound: zero-width joiners / marks, virama (halant), nukta, avagraha.
SILENT = frozenset("​‌‍⁠﻿़्ऽ")

# Roman two-letter groups, longest match first. "ph" is f and aspirates lose their h.
ROMAN_DIGRAPHS: dict[str, str] = {
    "sh": "s",
    "ch": "c",
    "kh": "k",
    "gh": "g",
    "th": "t",
    "dh": "d",
    "bh": "b",
    "jh": "j",
    "ph": "f",
}
ROMAN_VOWELS = frozenset("aeiou")
ROMAN_LETTERS: dict[str, str] = {
    "b": "b",
    "c": "k",
    "d": "d",
    "f": "f",
    "g": "g",
    "h": "h",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "q": "k",
    "r": "r",
    "s": "s",
    "t": "t",
    "v": "v",
    "w": "v",  # v/w are one sound in Indian English
    "x": "ks",
    "y": "y",
    "z": "j",
}

_DEVANAGARI_CONSONANTS = (
    "क=k ख=k ग=g घ=g ङ=n च=c छ=c ज=j झ=j ञ=n ट=t ठ=t ड=d ढ=d ण=n त=t थ=t द=d ध=d न=n "
    "प=p फ=f ब=b भ=b म=m य=y र=r ल=l ळ=l व=v श=s ष=s स=s ह=h "
    "क़=k ख़=k ग़=g ज़=j ड़=d ढ़=d फ़=f य़=y"
)
DEVANAGARI_LETTERS: dict[str, str] = dict(pair.split("=") for pair in _DEVANAGARI_CONSONANTS.split())
# Vowel signs that sound like "ri" (ऋ, ृ): the r is part of the name's skeleton.
DEVANAGARI_RI = frozenset("ऋॠृॄ")
# Anusvara, chandrabindu and visarga: a nasal (n) or breath (h) that spellings write both ways.
DEVANAGARI_NASALS = frozenset("ंँ")
DEVANAGARI_VISARGA = "ः"
# Independent vowels (only the first one of a word matters) and dependent vowel signs (matras).
DEVANAGARI_VOWELS = frozenset("अआइईउऊऌॡएऐओऔऍऑऎऒ")
DEVANAGARI_MATRAS = frozenset("ािीुूेैोौॅॉॆॊॢॣ")

# Consonants that speakers and spellings often add or drop ("Krishan" / "Kishan"): cheap to skip.
WEAK_LETTERS = frozenset("rhy")
# Neighbouring sounds: swapping them costs less than swapping unrelated letters.
SIMILAR_GROUPS = ("nm", "kg", "td", "pbf", "sj", "vb")

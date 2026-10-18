"""Fake names and IDs shared by tests. Every value here is invented."""

from __future__ import annotations

# Devanagari built from explicit code points so editors cannot change them.
KA = "\u0915"
KI = KA + "\u093f"  # one grapheme, two code points (consonant + vowel sign)
VIRAMA = "\u094d"
SSA = "\u0937"
ZWJ = "\u200d"
ZWNJ = "\u200c"

LATIN_NAME = "Rajesh Kumar"
DEVANAGARI_NAME = "\u0930\u093e\u091c\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"
TITLED_MIXED_NAME = "Smt. \u0938\u0941\u0928\u0940\u0924\u093e Devi"
PUNCTUATED_NAME = "Dr. Anne-Marie O'Neil"
ACCENTED_NAME = "Jos\u00e9 Mu\u00f1oz"

LATIN_40 = "A" * 40
LATIN_41 = "A" * 41
DEVANAGARI_40_GRAPHEMES = KI * 40  # 80 code points
DEVANAGARI_41_GRAPHEMES = KI * 41

CONJUNCT_WITH_ZWJ = KA + VIRAMA + ZWJ + SSA
CONJUNCT_WITH_ZWNJ = KA + VIRAMA + ZWNJ + SSA

BAD_CHARACTER_NAMES = [
    "Raj3sh",
    "A_B",
    "a/b",
    "<b>x</b>",
    "Raj\U0001f600",
    "\u0639\u0644\u064a",  # Arabic
    "\u5f20\u4f1f",  # CJK
    "Raj@",
    "Raj\u00a0Kumar",  # NBSP
    "\uff32\uff41\uff4a",  # full-width Latin
    "Raj\u200bKumar",  # zero-width space
    "\u202eRaj",  # RTL override
    "A" + ZWJ + "B",  # ZWJ between Latin letters
    ZWJ,  # ZWJ standing alone
]

VALID_ID = "183866"
SLASHED_ID = "RJ/12/097/183866"

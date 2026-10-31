"""The text the voice speaks for a name: the name followed by the spoken suffix (DD-39).

The suffix is an honorific such as "जी". It is added after the name unless the name already
ends with it, so a name typed as "Asha ji" is not spoken as "Asha ji ji".
"""

from __future__ import annotations


def spoken_text(name: str, suffix: str) -> str:
    """Return ``name`` followed by ``suffix``, each stripped at the ends, joined by one space.

    An empty suffix returns the stripped name; an empty name returns "". When the last words
    of the name equal the suffix words (compared with ``str.casefold``), the name is returned
    unchanged. Spaces inside the name are kept.
    """
    base = name.strip()
    if not base:
        return ""
    tail = suffix.strip()
    if not tail:
        return base
    suffix_words = [word.casefold() for word in tail.split()]
    name_end = [word.casefold() for word in base.split()[-len(suffix_words) :]]
    if name_end == suffix_words:
        return base
    return f"{base} {tail}"

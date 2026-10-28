# ruff: noqa
# mypy: ignore-errors
# Throwaway M2 spike script: exempt from the project lint and type gates.
"""S2: IndicXlit Roman -> Devanagari on CPU."""

import resource
import sys
import time
import types

# Attempt 2: urduhack (Urdu-only dep) breaks on keras; stub it, we only need Hindi.
for n in ("urduhack", "urduhack.normalization", "urduhack.tokenization"):
    sys.modules[n] = types.ModuleType(n)
sys.modules["urduhack"].normalize = lambda x: x  # type: ignore[attr-defined]

from ai4bharat.transliteration import XlitEngine

t = time.time()
e = XlitEngine("hi", beam_width=10, rescore=True)
print("load_s", round(time.time() - t, 1))
for name in ["Amit Dighal", "Krishan", "Priya Sharma", "Ramesh Kumar"]:
    t = time.time()
    out = e.translit_sentence(name, lang_code="hi")
    print(name, "->", out, round(time.time() - t, 2), "s")
print("peak_rss_MB", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20))

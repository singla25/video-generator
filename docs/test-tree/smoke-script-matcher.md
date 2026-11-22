Feature: Smoke script finds the name slot with the app's name matcher
└── Scenario: operator runs local_ai_smoke.py with --name (or --slot)
    ├── ✅ Positive  — Rahul matches a Devanagari word; slot, pause, hint passed; manual --slot unchanged and skips the matcher; --name only / --slot only / both (manual wins)
    ├── ❌ Negative  — no --name and no --slot errors naming both; unrelated name exits listing up to 3 candidates as time + closeness only (no heard words, no typed name); no candidate message; low-confidence close word is a candidate only; invalid --slot, bad --out-name
    └── ⚠️ Edge      — thresholds inclusive (confidence and closeness exactly at limit); just below/above refused; first word no longer assumed to be the name; empty transcript

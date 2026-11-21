# Test tree: Better name detection (BL-6, backend)

Plan: `docs/plans/better-name-detection.md`. Test files: `tests/unit/name_detection/`,
`tests/unit/infra/test_name_match_setting.py`, `tests/integration/api/test_name_candidates.py`.
Only made-up words; the labelled pair list is `tests/unit/name_detection/name_pairs.py`.

## Names chosen where the contract was open
- Service: candidates leave the service only through the API, so service behaviour is tested through
  the analyse route (POST templates, id, analyse) with the real service, a real database and a fake
  STT. The developer may add an internal method; tests do not call it.
- Analyse response gains `candidates`: `[{text, start_s, end_s, closeness, confidence}]` (max 3,
  closeness and confidence rounded to 3 decimals). GET has no `candidates` or an empty list.
- Script loader: `loader(weights_dir: Path) -> model` where the model has faster-whisper's
  `transcribe(path, **kw) -> (segments, info)`; `main(argv, *, loader=...) -> int` (exit code).
  Messages for exit code 2 go to stderr and contain the missing path; the table goes to stdout, one
  row per size starting with the size name, with a header naming closeness and memory.
- Fake STT (`tests/fixtures/doubles.py`) records `hints`.

```
Feature: Better name detection
├── Scenario: Compare a typed name with a heard word (sound_key, closeness)   [AC1]
│   ├── ✅ Positive  Krishan vs कृष्ण, किशन, krishan, Krishn, Kishan >= 0.8; equal keys give 1.0;
│   │                36 labelled pairs match at >= 90 %; case, punctuation, ZWJ, nukta, chandrabindu ignored
│   ├── ❌ Negative  Krishan vs Ramesh < 0.5; 14 unrelated pairs < 0.8; empty / punctuation-only key
│   │                is "" and closeness is 0.0
│   └── ⚠️ Edge      one letter, digits, mixed script, emoji / RTL, 200 characters (fast),
│                    repeated letters, symmetry, determinism, NFC
├── Scenario: Choose the name slot (select_name_slot)                          [AC2, AC3, AC4, AC8]
│   ├── ✅ Positive  exact and sound-alike found, no candidates; closeness beats confidence; ties by
│   │                confidence then earliest; duplicate words; low-confidence close word becomes a
│   │                candidate; candidates best first, max 3 (max_candidates honoured)
│   ├── ❌ Negative  confident but far = nothing; empty list; empty / punctuation target; empty-sound
│   │                words never chosen; short target (key < 3) needs 1.0 and gives no candidates
│   └── ⚠️ Edge      both thresholds exactly at the limit (inclusive, nextafter just beyond),
│                    fewer than 3 words, 100 words, 2000 words < 0.5 s, frozen results, deterministic
├── Scenario: Setting name_match_threshold                                     [AC2]
│   ├── ✅ Positive  default 0.8; env VIDGEN_NAME_MATCH_THRESHOLD overrides
│   ├── ❌ Negative  -0.01, 1.01, "high" refused
│   └── ⚠️ Edge      0.0 and 1.0 accepted
├── Scenario: Analyse a template (service via API)                             [AC1-AC4, AC8]
│   ├── ✅ Positive  Devanagari word found; exact match works; slot stays unconfirmed; candidates in
│   │                the response with the five fields, rounded; threshold from settings
│   ├── ❌ Negative  unrelated words and empty transcript: not found, empty list; no session = 401;
│   │                unknown template = 404
│   └── ⚠️ Edge      candidates not stored (absent on GET, no DB column); re-analyse replaces them;
│                    one-character and punctuation-only typed names are not matched loosely
├── Scenario: Whisper hint                                                     [AC6]
│   ├── ✅ Positive  port has `hint=None`; local adapter passes hotwords=hint (Roman and Devanagari,
│   │                keyword or positional); Modal and fake accept it
│   ├── ❌ Negative  no hint or empty hint: no `hotwords` kwarg (same as today)
│   └── ⚠️ Edge      Modal ignores the hint (same remote call)
└── Scenario: Model-size script                                                [AC7]
    ├── ✅ Positive  one row per size (found yes / no, closeness, candidates, seconds, memory);
    │                several audio files; no network (socket blocked); writes nothing
    ├── ❌ Negative  missing weights folder, missing audio, no size subfolders: exit 2 with the path;
    │                missing arguments: exit 2
    └── ⚠️ Edge      silent audio gives "no" rows, no crash
```

Frontend tree (A-N2): `docs/test-tree/better-name-detection-ui.md`.

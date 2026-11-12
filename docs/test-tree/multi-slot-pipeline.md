# Test tree: the pipeline runs once per name slot (DD-40, red step)

A template can hold several name slots. The row pipeline makes one voice, then one lip sync pass
per slot in ascending order (each pass takes the previous output; the first pass takes no key
source, later passes take the template as the face-box key source), then one encode pass per slot
in descending order (each pass takes the previous output; only the pass of the first slot gets the
real label and writes `output`, every other pass gets a transparent 1x1 PNG). Stage order is
unchanged.

Test files:
- `tests/integration/worker/test_render_row_multi_slot.py` (MS-P, MS-N, MS-E: row pipeline with recording doubles)
- `tests/unit/ai_local/test_lipsync_key_from.py` (MS-K: the port and the MuseTalk adapter take `key_from`)
- `tests/integration/worker/test_render_row_multi_slot_engine.py` (MS-V: real FFmpeg, slow)

```
Feature: the row pipeline runs once per name slot (DD-40)
├── Scenario: lip sync runs once per slot, in ascending order
│   ├── ✅ MS-P1 slots (2.0, 3.0) and (10.0, 11.0): two lip sync calls, starts 2.0 then 10.0
│   ├── ✅ MS-P2 each lip sync pass takes the previous output; the template goes in once
│   ├── ✅ MS-P3 first pass key_from None; second pass key_from is the template, bytes equal
│   └── ✅ MS-P13 one slot: one lip sync at the slot start, key_from None (guard, passes today)
├── Scenario: encode runs once per slot, in descending order
│   ├── ✅ MS-P4 encode calls: slot (10, 11) first, then (2, 3)
│   ├── ✅ MS-P5 last encode gets the lip-synced video; the next gets the previous encode output
│   ├── ✅ MS-P6 only the first-slot pass gets the real label; the label is rendered once
│   ├── ✅ MS-P7 other passes get a 1x1 transparent PNG (PNG signature, alpha 0, not the real label)
│   ├── ✅ MS-P8 the first-slot pass writes output.mp4; the published bytes are its result
│   └── ✅ MS-P14 one slot: one encode with the real label to output (guard, passes today)
├── Scenario: voice, plans and stage order
│   ├── ✅ MS-P9 the voice is synthesized once for all slots
│   ├── ✅ MS-P10 each slot gets a plan from its own length (unequal lengths)
│   ├── ✅ MS-P11 the name gap is added to the plan of every slot
│   └── ✅ MS-P12 stage order tts, lipsync, encode, check, publish; row COMPLETED
├── Scenario: failures leave nothing behind
│   ├── ❌ MS-N1 second lip sync pass fails: no encode, nothing published, temp folder empty
│   ├── ❌ MS-N2 first encode pass fails: the chain stops, nothing published, temp folder empty
│   ├── ❌ MS-N3 an extra slot too short for a crossfade: SLOT_NOT_FOUND before any encode
│   ├── ❌ MS-N4 TTS fails: no lip sync pass starts for any slot
│   └── ❌ MS-N5 a crash during the second lip sync pass: retry is safe, one output published
├── Scenario: edge cases
│   ├── ⚠️ MS-E1 unsorted extra slots: lip sync and encode run in ascending / descending order
│   ├── ⚠️ MS-E2 three slots: every pass takes the previous output; labels only on the last pass
│   ├── ⚠️ MS-E3 every intermediate file is inside the temporary folder, which is removed
│   └── ⚠️ MS-E4 the real label renderer runs once, for the first-slot pass only
├── Scenario: the port and the MuseTalk adapter take key_from (test_lipsync_key_from.py)
│   ├── ✅ MS-K-P1 the adapter passes key_from as the fifth argument of model.run
│   ├── ✅ MS-K-P2 a key source that is not the input is forwarded as given
│   ├── ✅ MS-K-P3 defaults pass 0.0 and None to the model
│   ├── ✅ MS-K-P4 an explicit None key source reaches the model as None
│   ├── ✅ MS-K-P5 FakeLipSyncer accepts a key source and copies the video
│   └── ✅ MS-K-P6 FakeLipSyncer accepts key_from=None
└── Scenario: two slots through the real engine (test_render_row_multi_slot_engine.py, slow)
    └── ✅ MS-V-P1 at 25 and 60 fps: duration = template + both extensions and gaps (within 0.15 s),
                   320x240, frame rate kept, audio kept, bubble present (single draw: see MS-P6/P7)
```

Expected red state: MS-P1..P12, MS-N1..N5, MS-E1..E4 and MS-V-P1 fail because the feature is
missing (the snapshot has no `extra_slots`; one lip sync pass and one encode pass run). MS-P13,
MS-P14 pass today and guard the single-slot path. MS-K-P1..P6 fail for the missing key source.

# Test tree: lip sync starts at the slot, name in the middle (DD-39 part B, task MID-RED)

The lip sync used to start at 0:00 of the template. `LipSyncer.sync` now takes an optional
`start_s` (default 0.0 = today's behaviour). The lip sync touches only the segment from `start_s`
and the output is spliced back: original 0..start_s, blended frames, original from
start_s + frames/25. Face boxes are cached per (template, start_s) through `landmark_key`.

Test files:
- `tests/unit/ai_local/test_mid_slot_support.py` (ML-F, ML-X, ML-A tests on real ffmpeg)
- `tests/unit/ai_local/test_mid_slot_adapter.py` (ML-P, ML-N adapter and fake syncer)
- `tests/integration/worker/test_render_row_mid_slot.py` (ML-R row pipeline)

```
Feature: lip sync starts at the template slot (DD-39 part B)
├── Scenario: landmark_key keeps the cache apart per start  (test_mid_slot_support.py)
│   ├── ✅ ML-F-P1 start 0.0 returns the fingerprint unchanged
│   ├── ✅ ML-F-P2 start 2.5 appends "-s2500"
│   ├── ✅ ML-F-P3 start 1.0 appends "-s1000"; start 10.0 appends "-s10000"
│   ├── ⚠️ ML-F-E1 starts 1.2 and 1.3 give different keys (different starts, different boxes)
│   └── ⚠️ ML-F-E2 the same start always gives the same key (stable across calls)
├── Scenario: extract_frames starts at start_s  (real ffmpeg, 4 s 25 fps testsrc2)
│   ├── ✅ ML-X-P1 start 2.0, count 5: five frames, first equals a direct grab at 2.0 s
│   ├── ✅ ML-X-P2 start 0.0, count 5: first frame equals the frame at 0 s (today's behaviour)
│   ├── ❌ ML-X-N1 start 10 (beyond the 4 s video) -> LocalAiError, no crash
│   └── ⚠️ ML-X-E1 start 3.9 with count 5 (runs past the end): frames returned, no error
├── Scenario: assemble_video splices the blended head into the original  (real ffmpeg)
│   ├── ✅ ML-A-P1 start 2.0: duration 4.0 within 0.1 s of the original
│   ├── ✅ ML-A-P2 start 2.0: frame at 1.0 s equals the original's frame at 1.0 s
│   ├── ✅ ML-A-P3 start 2.0: frame at 2.1 s is red (the blended head)
│   ├── ✅ ML-A-P4 start 2.0: frame at 3.0 s equals the original's frame at 3.0 s (tail in place)
│   ├── ✅ ML-A-P5 start 2.0: the audio stream is kept, duration within 0.1 s of the original
│   ├── ✅ ML-A-P6 start 0.0: old order, first 0.2 s red, frame at 1.0 s equals the original
│   ├── ⚠️ ML-A-E1 start 3.9 (blended part would end at 4.1 s): the blended part is cut at the
│   │              original end (4.0 s); no error, no third part, duration within 0.1 s of 4.0,
│   │              frame at 3.95 s is red
│   └── ⚠️ ML-A-E2 start 0.0 and start 2.0 both keep the video stream at the original frame rate
├── Scenario: MuseTalkLipSyncer passes the start to the model  (test_mid_slot_adapter.py)
│   ├── ✅ ML-P1 default call passes 0.0 as the 4th positional argument of run
│   ├── ✅ ML-P2 start 2.5 is passed as the 4th positional argument of run
│   ├── ❌ ML-N1 start -1 -> ValueError; the model is not loaded; no output file
│   ├── ❌ ML-N2 start nan -> ValueError; the model is not loaded; no output file
│   ├── ❌ ML-N3 start inf -> ValueError; the model is not loaded; no output file
│   └── ⚠️ ML-E1 start 0.0 passes 0.0 (not None, not missing)
├── Scenario: FakeLipSyncer and the port stay compatible  (test_mid_slot_adapter.py)
│   ├── ✅ ML-P3 FakeLipSyncer copies the video when given start_s=2.0
│   ├── ✅ ML-P4 the old three-argument call still copies the video
│   └── ⚠️ ML-E2 the copy is byte-identical for start_s=2.0
└── Scenario: the row pipeline passes the template slot start  (test_render_row_mid_slot.py)
    ├── ✅ ML-R-P1 slot (4.5, 5.4) -> lip sync receives start_s 4.5
    ├── ✅ ML-R-P2 slot (0.0, 1.0) -> lip sync receives start_s 0.0
    ├── ✅ ML-R-P3 stage order unchanged: tts, lipsync, encode, check; output published
    └── ⚠️ ML-R-E1 the lip sync gets the slot start, not the slot end or the duration
```

## Acceptance criteria mapped to tests

| Criterion (plan) | Tests |
|------------------|-------|
| AC5 default `start_s` is today's behaviour | ML-P1, ML-P4, ML-A-P6, ML-R-P2 |
| AC5 negative or non-finite start is rejected, no output | ML-N1, ML-N2, ML-N3 |
| AC5 start beyond the video is rejected with a typed error | ML-X-N1 |
| AC6 only the segment from start_s changes; duration and audio kept | ML-A-P1, ML-A-P2, ML-A-P4, ML-A-P5, ML-A-E2 |
| AC7 face boxes cached per (template, start_s) | ML-F-P1, ML-F-P2, ML-F-P3, ML-F-E1, ML-F-E2 |
| R4 additive optional argument on the port | ML-P3, ML-P4 |
| R5 segment spliced back | ML-A-P1..P5, ML-A-E1 |
| R6 cache key per start | ML-F-* |
| Render row passes the slot start | ML-R-P1, ML-R-P2, ML-R-E1 |

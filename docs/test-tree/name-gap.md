# Test tree: name gap after the new name (DD-34, task NG-RED)

After the new name, everything later in the video starts `gap_s` seconds later. The output is
`gap_s` longer than the template. Video: the last slot frame is held for `gap_s`. Audio: the
region that replaces the slot is `gap_s` longer (silence padded) and the tail keeps its place,
shifted later by `gap_s`. Defaults: `Settings.name_gap_s` 0.25 s (env `VIDGEN_NAME_GAP_S`,
range 0 to 1.0), `RenderConfig.name_gap_s` 0.0, `plan_timing(gap_s=0.0)`.

```
Feature: name gap after the new name (DD-34)
├── Scenario: the planner adds the gap to the timing plan  (tests/unit/domain/test_name_gap.py)
│   ├── ✅ NG-D-P1 gap 0 gives the same plan as before; gap_s == 0.0; delta == extension
│   ├── ✅ NG-D-P2 gap changes only gap_s (stretch, absorbed, extension, padding unchanged)
│   ├── ✅ NG-D-P3 short name, gap 0.25: extension 0, delta 0.25, padding about 0.1
│   ├── ✅ NG-D-P4 long name: delta == extension + gap
│   ├── ✅ NG-D-P5 output length = template + gap within 40 ms
│   ├── ❌ NG-D-N1 gap < 0 or > 1.0 raises ValueError (-0.1, -1e-6, 1.0001, 2.0)
│   ├── ❌ NG-D-N2 a name too long with gap 0 is too long with gap 0.25 (no new way to fail)
│   └── ⚠️ NG-D-E1 gap is not counted against max_extension_s; exactly 1.0 s is accepted
├── Scenario: the graph holds the last slot frame  (tests/unit/infra/test_ffmpeg_graph_gap.py)
│   ├── ✅ NG-G-P1 region length = slot + absorbed + extension + gap
│   ├── ✅ NG-G-P2 audio region apad/atrim use the longer length; tail start unchanged
│   ├── ✅ NG-G-P3 slot segment ends with tpad clone of 0.250000 s (gap 0.25, no extension)
│   ├── ✅ NG-G-P4 gap without extension still uses split + concat
│   ├── ✅ NG-G-P5 slot with 1.5x slow-down and hold: setpts first, then tpad
│   ├── ✅ NG-G-N1 gap 0 has no tpad
│   └── ⚠️ NG-G-E1 gap 0 and extension 0: graph string identical to today
├── Scenario: the Admin sets the gap  (tests/unit/infra/test_name_gap_setting.py)
│   ├── ✅ NG-S-P1 default 0.25 s
│   ├── ✅ NG-S-P2 VIDGEN_NAME_GAP_S=0.5 overrides the default
│   ├── ✅ NG-S-P3 render_config copies the setting (default and 0.5)
│   ├── ✅ NG-S-P4 RenderConfig built directly has name_gap_s 0.0
│   ├── ❌ NG-S-N1 -0.1, 1.5 and 1.0001 rejected (name_gap_s in the message)
│   └── ⚠️ NG-S-E1 0.0 and 1.0 accepted (inclusive range)
├── Scenario: the row pipeline passes the gap to the encoder  (tests/integration/worker/test_render_row_name_gap.py)
│   ├── ✅ NG-R-P1 name_gap_s 0.25 reaches plan.gap_s of the encoder call
│   ├── ✅ NG-R-P2 default config gives plan.gap_s 0.0
│   └── ⚠️ NG-R-E1 gap 1.0 still completes the row and stores the output
└── Scenario: the rendered file is longer by the gap  (tests/integration/ffmpeg/test_name_gap_output.py)
    ├── ✅ NG-O-P1 duration = template + 0.25 s within 50 ms
    ├── ✅ NG-O-P2 frame count = round((template + 0.25) * fps) within 1 frame
    ├── ✅ NG-O-P3 audio length equals video length within 60 ms
    ├── ✅ NG-O-P4 speech after the name is silent at 2.3-2.8 s and audible at 2.95-3.2 s
    ├── ✅ NG-O-P5 last slot frame held: N = round(gap * fps) - 1 = 5 frames from the slot end differ from the held frame by <= 0.5 and <= motion / 5 (tolerance, see below)
    ├── ❌ NG-O-N1 control with gap 0: at least one of the same N frames differs by > 5.0 (proves P5 detects a missing hold)
    └── ⚠️ NG-O-E1 gap 0 keeps the template length within 50 ms
```

## Hold thresholds (CEO, DD-34)

The 10-frame figure was wrong: at 25 fps a 0.25 s gap is about 6 frames. Frames are decoded to
RGB; the difference d is the mean absolute pixel difference on the 0-255 scale.

1. Motion floor: d(output frame 10, frame 11) >= 2.0 (measured 4.34; first limit was 5.0).
2. Hold: every d(held frame at output frame 50, each of frames 50..54) <= 0.5 AND <= motion / 5
   (measured largest 0.009).
3. Gap-0 control: at least one of frames 50..54 has d > 5.0 (measured largest 17.46).

The codec makes the held frames not bit-identical (libx264 CRF 18 chroma noise), so the hold uses
a tolerance instead of exact hashes.

## Conventions

- Failing reasons at RED: `plan_timing(gap_s=...)`, `TimingPlan.gap_s`, `Settings.name_gap_s`,
  `RenderConfig.name_gap_s` and the `tpad` string are missing. No test relies on a typo.
- The output checks use the same synthetic template as the neighbours (`make_template`, 4 s,
  25 fps, testsrc2 motion, 880 Hz name at 1-2 s, silence 2.0-2.6 s, 440 Hz speech after).

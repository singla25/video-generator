# Test tree: output quality checks (BL-14)

```
Feature: Real output quality checks
├── Scenario: QualityIssue codes and expected timeline (unit)
│   ├── ✅ Positive  — 9 codes, value = name; one slot and two slots give shifted regions and delta
│   ├── ❌ Negative  — slots/plans of different length -> ValueError; dataclasses are frozen
│   └── ⚠️ Edge      — zero delta keeps regions; absorbed pause moves template/output regions, not delta
├── Scenario: Checker format checks, no expectation (integration, real ffmpeg)
│   ├── ✅ Positive  — output equals template -> []; unicode/emoji file name
│   ├── ❌ Negative  — resolution, fps, codec, sample rate, channels, silent track, no audio, several at once
│   └── ⚠️ Edge      — duration/loudness ignored without expectation; logs hold no file names
├── Scenario: Checker with expectation (duration, loudness)
│   ├── ✅ Positive  — same length; longer by known delta; multi-slot; 0.5 LU off passes
│   ├── ❌ Negative  — 200 ms off; 2 LU louder/quieter; silent output; 2nd region off
│   └── ⚠️ Edge      — tolerance boundaries (ms and LU), defaults, loudness outside slot ignored, no regions
├── Scenario: Broken media and tools
│   ├── ✅ Positive  — wrong extension but real content judged by content
│   ├── ❌ Negative  — 0 byte -> EMPTY_OUTPUT; garbage, truncated, missing -> UNREADABLE_OUTPUT; no ffprobe/ffmpeg binary, no crash
│   └── ⚠️ Edge      — audio-only file, unreadable template, no path in logs
├── Scenario: Render check stage (unit, fakes)
│   ├── ✅ Positive  — check gets expected_output(slots, plans)
│   ├── ❌ Negative  — any issue -> OUTPUT_CHECK_FAILED; Latin and Devanagari names absent from logs
│   └── ⚠️ Edge      — success path also logs no name
└── Scenario: Wiring and temp cleanup (unit)
    ├── ✅ Positive  — fake mode -> fake checker; else real with settings; job removes old .tmp-* only; defaults 3600
    ├── ❌ Negative  — interval/max-age 0 or negative rejected
    └── ⚠️ Edge      — nothing stale -> 0, repeatable; custom max age; PeriodicTask start in main is a manual check
```

# Whisper size setting (WS-T1)

```
Feature: Whisper size (small locally, medium on the GPU app)
├── Scenario: Settings
│   ├── ✅ whisper_size defaults small, modal_whisper_size medium; env overrides work
│   ├── ❌ unknown value (large, tiny, "", Medium, " small") refused, error names the field
│   └── ⚠️ the two fields are independent
├── Scenario: whisper_weights_dir(root, size)
│   ├── ✅ small prefers whisper-small, falls back to legacy whisper; medium is whisper-medium
│   ├── ❌ unknown size raises ValueError
│   └── ⚠️ neither folder gives legacy path; unicode/space root; never creates anything
├── Scenario: build_ai_adapters (local mode)
│   ├── ✅ STT adapter gets the folder for the chosen size; other adapters unchanged; fake mode unchanged
│   ├── ❌ missing whisper-medium: clear error naming "whisper-medium" and how to fix, no root path
│   └── ⚠️ error appears on warm_up and on first transcribe
└── Scenario: Modal app
    ├── ✅ default repo Systran/faster-whisper-medium; env small gives small
    ├── ❌ invalid env value raises ValueError at import
    └── ⚠️ empty string, wrong case, path-like value rejected; import stays offline
```

Tests: tests/unit/infra/test_whisper_size_setting.py, tests/unit/ai_local/test_whisper_size.py,
tests/unit/modal_mode/test_modal_whisper_size.py.

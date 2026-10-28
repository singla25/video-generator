# Test tree: M2-local real AI (AI_MODE switch + real adapters)

Plan: docs/plans/m2-local-real-ai.md. Tests: `tests/unit/ai_local/`. All real adapters are tested with
stubbed models injected through a `loader(weights_dir) -> model` seam. No torch, weights or network in
default or CI runs. Real-model tests carry `@pytest.mark.local_ai` and run only with `RUN_LOCAL_AI=1`.

## Expected API (the developer creates these)

| Module | Names |
|--------|-------|
| `vidgen.settings.Settings` | `ai_mode: Literal["fake","local"] = "fake"` (env `VIDGEN_AI_MODE`), `local_ai_weights_dir: Path` |
| `vidgen.infrastructure.local_ai.errors` | `LocalAiError` (base), `ModelWeightsMissingError`, `EmptyAudioError`, `OfflineViolationError`, `AiBusyError`, `NameSlotNotFoundError` |
| `vidgen.infrastructure.local_ai.factory` | `build_ai_adapters(settings)` returning an object with `.stt .transliterator .voice .lipsync`; `effective_worker_threads(settings)`; `describe_mode(settings)`; `local_label_band_height(settings, frame_h)` |
| `vidgen.infrastructure.local_ai.stt` | `FasterWhisperSpeechToText(weights_dir, loader=...)` |
| `vidgen.infrastructure.local_ai.transliterate` | `QwenTransliterator(weights_dir, loader=...)`; model has `generate(prompt) -> str` |
| `vidgen.infrastructure.local_ai.tts` | `ChatterboxVoiceCloner(weights_dir, loader=...)`; model has `generate(text, voice_sample) -> (samples, rate)` |
| `vidgen.infrastructure.local_ai.lipsync` | `MuseTalkLipSyncer(weights_dir, loader=..., guard=None)`; model has `run(video, audio, out)` |
| `vidgen.infrastructure.local_ai.name_slot` | `detect_name_slot(words, placeholder, manual=None, min_confidence=0.6) -> NameSlot(start_s, end_s, source, ambiguous)` |
| `vidgen.infrastructure.local_ai.guard` | `SingleRenderGuard().acquire()` context manager, raises `AiBusyError` when held |
| `vidgen.infrastructure.local_ai.offline` | `offline_only()` context manager patching socket connect and DNS |

Rules the tests pin: weights checked on first use (not at construction); model loaded once; weights
missing -> `ModelWeightsMissingError` naming the folder; empty audio -> `EmptyAudioError` before the
model is called; a failed call leaves no output file; local mode sets `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`; heavy imports happen only inside default loaders.

```
Feature: Run real AI locally
├── Scenario: Choose the mode (AC1, AC2, AC9)            test_mode_switch.py
│   ├── ✅ default is fake; VIDGEN_AI_MODE=local selected; fake builds Fake* adapters; local builds real ones lazily; banner text per mode
│   ├── ❌ unknown value (real, "LOCAL ", gpu, empty) -> ValidationError naming ai_mode
│   └── ⚠️ importing the factory in fake mode does not import torch / faster_whisper / transformers (subprocess check)
├── Scenario: Worker concurrency (AC7)                   test_mode_switch.py
│   ├── ✅ fake mode keeps worker_threads
│   └── ⚠️ local mode forces 1 for requested 1, 2, 8
├── Scenario: No network (AC8)                           test_mode_switch.py, test_errors_and_guards.py, test_adapters.py
│   ├── ✅ stubbed pass works inside offline_only(); local mode sets the two offline env vars
│   ├── ❌ socket.create_connection and getaddrinfo raise OfflineViolationError inside the guard
│   └── ⚠️ guard is removed on exit even after an exception
├── Scenario: Speech to text (AC3)                       test_adapters.py
│   ├── ✅ words, times, confidence mapped; lazy single load
│   ├── ❌ missing weights -> ModelWeightsMissingError; empty WAV -> EmptyAudioError (model never called); missing file -> FileNotFoundError
│   └── ⚠️ silence returns []
├── Scenario: Transliterate a name (AC3, AC5)
│   ├── ✅ cleaned answer returned; prompt contains the name
│   ├── ❌ missing weights -> ModelWeightsMissingError
│   └── ⚠️ 1-char names (A, ए, Ng); Hindi input kept intact; blank -> "" without model call; chatty multi-line answer -> first line only
├── Scenario: Clone the voice (AC3)
│   ├── ✅ WAV written, duration returned equals file duration
│   ├── ❌ missing weights; empty voice sample -> EmptyAudioError; blank text -> ValueError; model failure leaves no partial file
│   └── ⚠️ 1-char, Hindi, multi-word Hindi, accented text; a failing row does not poison the next row (one load)
├── Scenario: Lip sync (AC3, AC7)
│   ├── ✅ output written through the model
│   ├── ❌ missing weights; empty audio; model failure leaves no partial video
│   └── ⚠️ second concurrent run refused by SingleRenderGuard (AiBusyError)
├── Scenario: Detect the name slot (AC4)                 test_name_slot.py
│   ├── ✅ placeholder found -> auto slot; case and punctuation ignored
│   ├── ❌ not found and no manual slot -> NameSlotNotFoundError; inverted manual slot -> ValueError
│   └── ⚠️ not found -> manual fallback; empty transcript; two hits -> first, ambiguous=True; manual wins over two hits; low confidence -> ambiguous
├── Scenario: Memory guard and batch isolation (AC7)     test_errors_and_guards.py
│   ├── ✅ guard released after success and after failure
│   ├── ❌ second render (same or other thread) -> AiBusyError
│   └── ⚠️ every LocalAiError subclass is classified by classify_failure into a row failure code, so one row never stops the batch
├── Scenario: AI label size (AC6)                        test_label_height.py
│   ├── ✅ band >= 10 % of 1300 and 1920; rendered PNG matches
│   └── ⚠️ odd heights (1081, 1279, 2); local_label_band_height keeps the same rule
├── Scenario: Preview confirmation of the spoken name (AC5)
│   └── Backend part is covered by existing ADR-010 override tests; UI part goes to the L5 frontend tree.
└── Scenario: Real-model smoke (@local_ai, skipped by default)
    └── ✅ real Whisper runs on a synthetic clip (L6 adds the 2-video run)
```

## Acceptance criteria map
AC1 mode switch; AC2 lazy import + default install; AC3 adapter contracts; AC4 name slot; AC5 transliterator
pre-fill (human confirmation tested in L5/L6); AC6 label; AC7 guard, concurrency, isolation; AC8 offline;
AC9 `describe_mode` (UI part in L5).

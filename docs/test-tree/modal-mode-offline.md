# Test tree: Modal mode without live calls (track B)

Plan: `docs/plans/modal-mode-offline.md`. All tests live in `tests/unit/modal_mode/` and run with sockets blocked
(`tests/fixtures/network.py`), without `modal` installed (stub in `tests/fixtures/modal_stub.py`).

## Contract chosen (the developer implements these names)
- `vidgen.infrastructure.modal_ai.protocol`: `DEFAULT_APP_NAME="vidgen-ai"`, `FN_TRANSCRIBE`, `FN_HAS_SAMPLE`,
  `FN_UPLOAD_SAMPLE`, `FN_SYNTHESIZE`; stdlib only; `modal_client.py` imports them (no string literals left).
- `backend/modal_app/app.py` imports the names from `protocol`; four functions (module-level `app.function` or
  `modal.method` in the one `app.cls`); every image entry `name==version`; no `modal` in the image; no secrets.
- `RemoteModelClient.transcribe(audio, hint=None)`; `ModalRemoteClient` sends `(audio, hint)`; the fake records `transcribe_hints`.
- `Settings.ai_mode: Literal["fake","local","modal"]`, `Settings.modal_app_name = "vidgen-ai"`.
- `vidgen.infrastructure.modal_ai.factory.build_modal_adapters(settings, client=None)` returns an object with
  `.stt` (ModalSpeechToText), `.voice` (ModalVoiceCloner), `.lipsync` (UnavailableLipSyncer); the container and
  `worker.runner.build_renderer` use it when `ai_mode == "modal"`.
- `vidgen.infrastructure.modal_ai.lipsync.UnavailableLipSyncer.sync(...)` raises `DomainError` with message
  "Lip sync on the cloud is not available yet." and a code other than `LIPSYNC_LOW_QUALITY`. No existing
  FailureCode fits: a new one (e.g. `LIPSYNC_UNAVAILABLE`) is needed.
- Fallback provider with `ai_mode == "modal"`: kind remote_function, demo_only, requires both token names, with a
  positive `spend_cap_usd` and `rate_per_second` (a remote provider needs a cap by existing validation).

```
Feature: Modal mode without live calls
├── Scenario: shared names (AC1)                         test_protocol_names.py
│   ├── ✅ constants have the agreed values, are distinct; modal_client re-uses them
│   ├── ❌ client redefines or hard-codes a name literal; protocol imports a third-party package
│   └── ⚠️ importing protocol in a fresh process loads no heavy module
├── Scenario: Modal app source (AC2)                     test_modal_app_source.py, test_app_isolation.py
│   ├── ✅ four functions with client signatures, one warm class, pinned image, imports names from protocol
│   ├── ❌ checker catches: missing/renamed function, missing hint, unpinned or range entry, modal in image, secret-like text
│   └── ⚠️ stub removed from sys.modules after load; token env values ignored; nothing in vidgen imports modal_app or modal at top level; syntax error fails loudly
├── Scenario: hint travels (AC6)                         test_hint_forwarding.py
│   ├── ✅ adapter -> client -> remote call with hint
│   ├── ❌ (none: a missing hint is sent as None, not dropped)
│   └── ⚠️ unicode (Devanagari, emoji), empty, 5000 characters, None
├── Scenario: settings (AC3)                             test_settings_modal.py
│   ├── ✅ modal accepted; app name default and env override
│   ├── ❌ cloud / "MODAL " / empty / remote refused
│   └── ⚠️ no token field in Settings
├── Scenario: installer (AC3)                            test_installer_modal_mode.py, meta/test_setup_mode_gate.py
│   ├── ✅ real Settings annotation lists modal; prompt offers three modes; tokens collected
│   ├── ❌ declined demo-data confirmation writes nothing; empty token refused
│   └── ⚠️ (existing meta suite keeps covering literal parsing)
├── Scenario: factory (AC4)                              test_factory.py
│   ├── ✅ builds Modal STT and TTS around injected or real client with settings.modal_app_name
│   ├── ❌ lip sync raises the clear domain error, writes no file
│   └── ⚠️ no modal import on build or on import (fresh process); remote call without package -> ImportError
├── Scenario: container and worker (AC4)                 test_container_modal.py
│   ├── ✅ container uses ModalSpeechToText; renderer uses ModalVoiceCloner + UnavailableLipSyncer
│   └── ⚠️ builds with modal blocked and no tokens; no faster_whisper/torch loaded
├── Scenario: registry, chooser, guard (AC5)             test_registry_chooser_modal.py
│   ├── ✅ fallback is demo-only remote function; ready with tokens + heartbeat; demo batch allowed
│   ├── ❌ real data refused; not ready (token missing or empty, no heartbeat); worker guard pauses real batch
│   └── ⚠️ spend cap pauses at the cap; cost = seconds x rate; fake/local fallbacks unchanged
└── Scenario: no network (AC7)                           test_network_guard.py + autouse fixture
    └── ❌ connect, getaddrinfo and create_connection raise
```
- B-V1: fixed 5 outdated/defective modal-mode tests (exit code, getsource loader, LIPSYNC_UNAVAILABLE, hint arg).

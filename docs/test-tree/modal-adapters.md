# Test tree: Modal adapters (ADR-013 decisions 2-4, 6a, 7; plan AC4, P6, Q2)

Scope: adapters only, against `tests/fixtures/modal_fake.py`. No network, no `modal` import. Not covered here:
`ai_mode == "modal"` wiring, installer gate, lip sync (ADR-012), the real Modal-backed client.

## Contract pinned (package `vidgen.infrastructure.modal_ai`)
- `client.RemoteModelClient` Protocol: `transcribe(audio: bytes) -> list[dict]` (keys text, start_s, end_s, confidence),
  `has_sample(sample_hash) -> bool`, `upload_sample(sample_hash, data) -> None`, `synthesize(text, sample_hash) -> bytes` (wav).
- `errors`: `RemoteAuthError` (has `.code`, not retryable, fixed message, raised without cause),
  `RemoteTimeoutError(TimeoutError)` -> TIMEOUT, `RemoteCrashError(WorkerCrashedError)` -> CRASH.
- `stt.ModalSpeechToText(client)` and `tts.ModalVoiceCloner(client)`, both with `bytes_sent` / `bytes_received`.
- Bad remote result: `DomainError` with `STT_FAILED` / `TTS_FAILED`. Missing file: `FileNotFoundError`; empty audio: `EmptyAudioError`.
- Concurrency decision: one cloner instance uploads a new sample exactly once (lock); separate instances rely on `has_sample`.

```
Feature: Modal speech-to-text adapter
├── Scenario: transcribe a file
│   ├── ✅ words mapped to Word, one remote call with the file bytes
│   ├── ✅ silence -> []
│   ├── ⚠️ Devanagari text kept
│   ├── ⚠️ missing file / empty file -> clear error, no remote call
│   └── ❌ malformed result (8 variants) -> STT_FAILED
├── Scenario: remote failures
│   ├── ❌ timeout -> TIMEOUT, retryable
│   ├── ❌ crash -> CRASH, retryable
│   └── ❌ auth -> not retryable, message and repr free of token
├── Scenario: accounting and privacy
│   ├── ✅ bytes_sent / bytes_received counted
│   └── ✅ no text or token in log records
Feature: Modal voice cloner adapter
├── Scenario: synthesize rows
│   ├── ✅ wav written, duration returned
│   ├── ✅ sample uploaded once over 5 rows; rows send text + sha256 only
│   ├── ✅ remote already has the sample -> no upload
│   ├── ⚠️ two adapters, one client -> one upload
│   ├── ⚠️ concurrent calls, same new sample -> exactly one upload
│   ├── ⚠️ changed sample content -> uploaded again
│   ├── ⚠️ Devanagari text; 20k-char text
│   └── ✅ bytes accounting: sample counted once, wav counted per row
├── Scenario: failures
│   ├── ❌ missing sample -> FileNotFoundError, no remote call
│   ├── ❌ empty / garbled / zero-frame wav -> TTS_FAILED, no out file, no temp file
│   ├── ❌ remote error keeps an existing out untouched
│   ├── ❌ timeout / crash retryable; auth not, no token leak
│   └── ✅ no name text or token in logs
Feature: Dependency and import safety
├── ✅ pyproject extra `cloud` has `modal==X.Y.Z`
├── ❌ modal not in base dependencies
└── ⚠️ adapters import with `modal` blocked
```

Feature: ModalRemoteClient (stubbed `modal` module via sys.modules; no network)
├── ✅ each of 4 methods looks up the right function name in the app and passes the right args
├── ✅ synthesize returns bytes (bytearray coerced); has_sample returns bool
├── ❌ AuthError -> RemoteAuthError, fixed message, no __cause__, token absent from traceback
├── ❌ FunctionTimeoutError -> RemoteTimeoutError; other modal Error -> RemoteCrashError (no details)
├── ❌ failure inside Function.from_name is translated the same way
├── ❌ non-modal exception (ValueError) is not swallowed
└── ⚠️ empty bytes / unicode text pass through unchanged

Feature: ModalVoiceCloner extras
├── ⚠️ bytes_sent counts UTF-8 bytes (Devanagari + emoji), not characters
├── ⚠️ second cloner on the same remote re-checks has_sample but does not re-upload or recount the sample
├── ⚠️ failed synthesis (bad wav) books no per-row bytes
└── ⚠️ empty text sent with the hash only

Feature: RemoteAuthError carries no link to the original exception (tests/unit/modal_ai/test_no_exception_link.py)
├── ❌ _guard.call_remote: auth error with token via STT transcribe, TTS synthesize, TTS upload -> __cause__ None AND __context__ None, token absent from whole chain and traceback
├── ❌ modal_client._translate: stub modal AuthError -> same assertions
└── ⚠️ EXTRA SCOPE (tester proposal): _translate Timeout/Crash errors -> same "no context" (tests named *_extra_scope)

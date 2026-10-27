# Test tree — FIX-UPLOAD-1: uploads must never fail silently

Bug: in the dashboard an upload showed no progress and no error when Postgres was down and the API answered 500. Plan: `docs/plans/m3-dashboard.md` UI-AC5 and UI-AC10 (every screen shows error states). Branch `fix/upload-feedback`.

Tests: `tests/frontend/unit/upload-feedback.test.tsx` (Vitest, MSW, controllable fake XHR in `tests/frontend/support/fake-xhr.ts`) and `tests/unit/api/test_dependency_outage.py` (pytest, no real DB or Redis). The upload surfaces covered: wizard sheet (inspect), wizard Validate sheet, new template, consent. The wizard has no video upload; the template video is the "video" case.

```
Feature: Upload feedback (frontend, per surface)
├── Scenario: file is being sent
│   ├── ✅ TT-UP-P1  progressbar with aria-valuemin 0, max 100, now = percent, text "40%"
│   ├── ✅ TT-UP-P2  bar disappears when the upload succeeds
├── Scenario: the upload fails
│   ├── ❌ TT-UP-N1  500 with API body -> role=alert with that message + Retry
│   ├── ❌ TT-UP-N2  503 DB_UNAVAILABLE -> API message shown
│   ├── ❌ TT-UP-N3  503 HTML proxy page -> plain words, no markup leaked, Retry
│   ├── ❌ TT-UP-N4  network failure -> "could not reach the server" + Retry
│   ├── ❌ TT-UP-N5  connection dropped after progress -> alert, bar cleared
│   ├── ❌ TT-UP-N6  timeout -> "took too long" alert + Retry
│   ├── ❌ TT-UP-N7  Retry resends the same file; success clears the alert
│   ├── ❌ TT-UP-N8  form stays usable, no stale success state (per-surface check)
│   └── ❌ TT-UP-N9  repeated failure shows one alert, not a pile
└── Scenario: edges
    ├── ⚠️ TT-UP-E1  413 without JSON body -> "too large"
    ├── ⚠️ TT-UP-E2  413 with API body -> API message
    ├── ⚠️ TT-UP-E3  401 mid-upload -> login screen
    ├── ⚠️ TT-UP-E4  page left mid-upload -> request aborted
    ├── ⚠️ TT-UP-E5  double submit -> one request
    ├── ⚠️ TT-UP-E6  0-byte template video refused, no request
    ├── ⚠️ TT-UP-E7  0-byte consent file refused, no request
    ├── ⚠️ TT-UP-E8  Cancel on template form aborts the upload
    └── ⚠️ TT-UP-E9  late answer after abort shows nothing

Feature: Dependency outage (backend)
├── Scenario: database unreachable (OperationalError / InterfaceError)
│   ├── ✅ GET /templates, GET /batches, POST /templates -> 503 {code DB_UNAVAILABLE, message}
│   ├── ❌ no connection string, host, password or trace in the body or the log
│   ├── ❌ logged at ERROR level
│   └── ⚠️ a plain bug is still 500 INTERNAL_ERROR (no over-mapping)
└── Scenario: queue unreachable on enqueue (redis ConnectionError, ConnectionRefusedError)
    ├── ✅ 503 {code QUEUE_UNAVAILABLE, message}, nothing leaked
    └── ❌ logged at ERROR level
```

Acceptance criteria map: AC1 -> P1, P2; AC2 -> N1-N7, E1, E2; AC3 -> N8, per-surface stale checks; AC4 -> backend file; AC5 -> E1-E9.

Implementation contract (from the tests): progress needs `XMLHttpRequest` (fetch has no upload progress); progress bar `role=progressbar` with `aria-valuenow`; Retry button named /retry/i; backend maps `sqlalchemy.exc.OperationalError/InterfaceError` to 503 DB_UNAVAILABLE and redis/connection-refused errors to 503 QUEUE_UNAVAILABLE in `backend/vidgen/api/errors.py`.

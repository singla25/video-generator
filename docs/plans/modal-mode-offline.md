# Plan — Modal mode without live calls (overnight track B)

**Status:** BUILT and merged into the overnight branch, then **PARKED (budget) by the Admin on 2026-11-22**: the code stays behind the `modal` flag, no Modal commands, payments or accounts. Scope given by the Admin on 2026-11-22 (overnight run, DD-41). Nothing here calls Modal: no `modal deploy`,
no `modal run`, no token, no network. Everything is tested with a fake client or a stub `modal` module.
No migration. The only dependency is the already approved `modal==1.6.4` extra.

## Goal
When the Admin adds Modal credits in the morning, the only steps left are "deploy the app" and "run the spike". All the
code that talks to Modal, and the Modal app itself, already exists and is tested offline.

## Acceptance criteria
1. AC1 One module holds the remote function names and the default app name, imported by both the client and the Modal
   app, so the two cannot drift apart (this replaces the guessed names).
2. AC2 `backend/modal_app/app.py` defines the remote functions `transcribe`, `has_sample`, `upload_sample` and
   `synthesize` with exactly the signatures the client calls, the model image (pinned) and one warm container class.
   It is never imported by the API or the worker, only by the Modal command line.
3. AC3 `ai_mode="modal"` is accepted by the settings. The installer then offers `modal` (it still needs the clear yes
   to demo data only, C5, and the token pair).
4. AC4 In modal mode the adapter factory builds the Modal speech-to-text and voice-cloning adapters around the real
   client class, importing `modal` only when a call is made. Lip sync on Modal stays unavailable (licence decision
   BL-7): a clear "not available yet" failure, never a silent fake.
5. AC5 The provider registry and the chooser work in modal mode: a Modal provider is listed as demo-only, a batch with
   real data is refused (C5), a demo batch is allowed once the provider is ready, and the spend cap still pauses.
6. AC6 The speech-to-text hint (track A) travels to the remote function.
7. AC7 Tests make zero network calls (a test fails if a socket is opened) and do not need `modal` installed.

## Out of scope
Lip sync on Modal (BL-7, licence), the CUDA image (G6), real deployment, real timings (the spike).

## Tasks
| ID | Task | Agent | Depends on | Model | Done when |
|----|------|-------|-----------|-------|-----------|
| B1 | Red tests: names module, app source with a stub `modal`, settings, installer, factory, registry/chooser, no network | tester | track A merged (port hint) | sonnet | fail for the right reasons |
| B2 | Build: names module, `backend/modal_app/app.py`, settings, factory, registry entry, hint | backend-dev | B1 | sonnet | tests green |
| B3 | Verify, coverage | tester | B2 | sonnet | full suite green |

## Risks
| Risk | Mitigation |
|------|-----------|
| The app source cannot be run without Modal | Tests import it with a stub `modal` module and check names, signatures, image pins |
| Hidden live call | A socket-blocking test and no `modal` import at module level outside `modal_app` |
| Real data sent to the cloud | Demo-only rule and the installer confirmation stay; tests keep them |

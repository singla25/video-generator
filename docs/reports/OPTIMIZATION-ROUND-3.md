# Optimization round 3: architecture against CLAUDE.md section 4 (static, read-only)

Date: 2026-11-23. Base `origin/main` (after #41 to #48). Only this report and a proposed ADR are added.
Method: an AST pass over every `backend/vidgen` file to build the import graph between layers and list third-party imports per layer (script kept in `.dev/layers.py`, not committed), plus reading the code paths named below. Nothing was run against real models.

## What the layering looks like today (measured)

| Layer | Imports from other project layers | Third-party libraries |
|---|---|---|
| domain | nothing from other layers | `regex` only (pure text matching); no I/O imports found (no os, subprocess, time, open, datetime.now, uuid4) |
| ports | domain | none |
| services | ports, domain, logging | none |
| infrastructure | domain, ports, settings, logging, **services (1 file)** | SQLAlchemy, Pillow, numpy, cv2, redis, dramatiq, modal, torch and similar |
| api | services, ports, domain, settings, **infrastructure (1 file)** | FastAPI, argon2, itsdangerous, **sqlalchemy (4 files), redis (3), dramatiq (1)** |
| worker | ports, services, domain, infrastructure, settings, **api (1 file)** | dramatiq, sqlalchemy |

Good news first: the domain layer is clean, services have no framework or driver imports, no file in `backend/vidgen` is over 300 lines, and `tests/unit/meta/test_architecture.py` already enforces the domain rule, the file length rule, docstrings and no `print`. Jobs are retry-safe: `render_row` checks `storage.exists(key)` before rendering again (`services/render_row.py:176`), writes are atomic (temp file then publish), and a row has an attempt limit. Video work goes through ports (`VideoEncoder`, `LipSyncer`, `SpeechToText`, `Storage`). No module-level mutable state was found in `api`, `services` or `worker` (stateless API holds).

## Violations and risks, ranked

| # | Rank | Finding | Evidence | Gain if fixed | Risk of fixing | Proposed fix | Needs Admin approval |
|---|---|---|---|---|---|---|---|
| 1 | High | **Speech-to-text runs inside a web request, holding a database transaction.** `POST /templates/{id}/analyse` calls `TemplateService.analyse_with_candidates`, which opens a unit of work and, inside it, copies the whole video to a temp file and transcribes it. In `local` mode the API process builds the real Whisper adapter (`_default_stt`). Rule broken: heavy AI work must not run in a web request, and the API must stay light and scalable. The plan accepts "a few seconds on CPU" (`docs/plans/better-name-detection.md:83`), but a 300 s template with the medium model is not seconds, and the transaction stays open for the whole call. Measured: not measured here (no models). | `api/routes_templates.py:95-99`, `services/templates.py:160-190` (UoW at 160+, `_transcribe` at 261-270), `api/container.py:94-99` | The API process no longer loads models; a slow analysis cannot block API workers or hold a DB connection | Medium: the dashboard now expects a synchronous answer; it would need a status poll | Run analysis as a queued job (like previews), return 202 and poll; at minimum, move `_transcribe` outside the transaction | Yes (architecture, ADR) |
| 2 | High | **The whole template video is read into memory for every row.** The worker does `template.write_bytes(source.read())`: up to 500 MB (`max_video_bytes`) held in RAM, and copied once per row (fetch stage). Rule broken: large files are streamed, never fully loaded. With `worker_threads=2` that is up to 1 GB at once on one worker. | `services/render_row.py:239` | Peak worker memory down by the template size per thread (measured size: up to 500 MB per row; an estimate of the real saving needs a real template) | Very low (one line: `shutil.copyfileobj`) | Stream with `shutil.copyfileobj(source, handle)`; later, cache the template per batch on the worker's local disk so rows do not copy it again | No for the one-line change (it is a refactor), yes for the cache |
| 3 | Medium | **`infrastructure` imports `services`.** The login state store uses the `AttemptState` and related types defined in `services/login_guard.py`, which points the dependency the wrong way (infrastructure should depend on domain and ports). | `infrastructure/db/login_state.py` | Layering rule restored; services stay replaceable | Low | Move `AttemptState`, `LoginRules` and the store protocol to `domain` and `ports` | Yes (moving more than 3 symbols between files; per CLAUDE.md section 2.7 only if it also moves files) |
| 4 | Medium | **The API layer knows database and queue drivers.** `api` imports `sqlalchemy` (4 files), `redis` (3) and `dramatiq` (1) to catch their exceptions and to map them to "dependency unavailable" responses. | `api/errors.py`, `api/login_tolerance.py`, `api/routes_system.py`, `api/schema_gate.py`, `api/container.py` | The API could change drivers without edits; the error mapping becomes testable without drivers | Low to medium | Let adapters raise one domain error (`DependencyUnavailableError(kind)`) and have `api/errors.py` map that | Yes (new exception contract) |
| 5 | Medium | **The composition root lives inside `api`, and the worker imports it.** `worker/runner.py` imports `vidgen.api.container`, so a worker process depends on the API package (and its FastAPI imports). The composition root also builds adapters for the worker. | `worker/runner.py:20`, `api/container.py` (236 lines) | Worker image no longer needs the web stack; clearer ownership | Medium (folder move: more than 3 files) | Create `vidgen/bootstrap/` for wiring shared by `api` and `worker`; keep `api/` for routes | Yes (folder structure) |
| 6 | Low | **Hard-coded tool names and a path constant in code**: `FFMPEG = "ffmpeg"` (worker), `DEFAULT_FFPROBE = "ffprobe"`, timeouts as module constants (30 s probe, 600 s quality). Rule: no hard-coded paths, URLs, keys or magic numbers; use settings. They are overridable in tests only through arguments. | `worker/runner.py` (`FFMPEG`), `infrastructure/ffmpeg/probe.py:24-25` | Operators can point to another ffmpeg without a code change | Low | Add `ffmpeg_path` / `ffprobe_path` settings with the same defaults | Yes (new settings) |
| 7 | Low | **Storage is local-only.** The `Storage` port exists and is used everywhere, but there is no S3-compatible adapter, so horizontal scaling across machines needs a shared disk. This is planned (G6/G8 in the plans), not a violation. | `ports/interfaces.py` (Storage), `infrastructure/storage/local.py` | n/a | n/a | Keep on the backlog | No |
| 8 | Info | A second guard: `consent.py:33` reads a whole PDF (`handle.read()`); it is limited to `max_consent_bytes` (10 MB), so it is acceptable. `modal_ai/stt.py:63` and `tts.py:73` read call-sized audio clips fully, documented in ADR-013. | files named | n/a | n/a | None | No |

## Proposed target architecture

See the proposal `docs/decisions/ADR-014-target-architecture-proposal.md` (status: PROPOSED, needs the Admin). In short: heavy work only in workers (template analysis becomes a job), driver exceptions stay inside infrastructure, one composition root shared by `api` and `worker`, and the existing architecture test gets three new rules so the layering cannot drift again.

## What I changed

Only this report and the proposed ADR, on branch `optimizer/report-round-3`.

## What I recommend next

1. Approve finding 2 as a small refactor PR (one line plus a test that fails above a memory bound): it is the cheapest and removes a memory spike for every row.
2. Decide on finding 1: queue the template analysis (needs an ADR and a dashboard change), or keep it synchronous but move the transcription outside the transaction as a first step.
3. Then rounds 5 (dashboard) and 6 (top 10).

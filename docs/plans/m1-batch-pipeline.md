# Plan — M1: Batch pipeline on fake AI models

**Status:** Approved (Admin, 2026-10-18) · **Date:** 2026-10-18 · **Requirements:** `docs/requirements/REQ-001-requirement-tree.md`
**ADRs:** 001 (Python 3.11 + uv) · 002 (Dramatiq) · 003 (Postgres) · 004 (FFmpeg) · 005 (PII encryption) · 006 (auth) · 007 (sheet parsing) · 008 (ports + fakes)

## Goal
Build and fully test the complete backend flow of REQ-001 (upload → validate → template + consent → preview → approve → queued rendering → output folder + manifest → status/analytics → downloads, retries, deletion), running end-to-end on a Mac CPU. Every AI step sits behind its port with a deterministic **fake** adapter, so M2 only has to plug in the real models.

## Acceptance criteria (each has ≥1 automated test)
1. **AC1 Video upload** — MP4/MOV with H.264/H.265 within the size/duration limits (settings) is accepted. Any other container or codec, a renamed non-video, a corrupt file, or a file over the limits is rejected with a coded, plain-language error, and nothing is stored. The type is checked with `ffprobe`, not the file extension.
2. **AC2 Sheet upload** — `.xlsx` and `.csv` are accepted. Headers match case-insensitively with whitespace trimmed (`VID ` = `vid`). The user maps Name, ID and an optional Spoken name. A missing mapped column gives a clear error and creates no batch.
3. **AC3 Row validation** — empty name, empty ID, duplicate ID (first row kept; the error names the earlier row), name > 40 chars, and characters outside Latin/Devanagari/space/`.`/`-`/`'` each give their R8 code. Invalid rows are `SKIPPED` and never rendered. All limits come from settings.
4. **AC4 Validation speed** — a 1,000-row sheet validates in < 3 s. A 100,000-row sheet is processed in a stream (memory stays flat, tested via a bound on peak memory).
5. **AC5 Consent gate (C1)** — a template is usable only after a consent file (PDF/PNG/JPG, type-checked) is uploaded and confirmation is ticked. Otherwise rows fail `CONSENT_MISSING`. Consent is stored with the template profile and logged in the audit log.
6. **AC6 Template profile (R2.1/2.3/2.4)** — analysis runs the `SpeechToText` port (fake in M1) and locates the target word with timestamps. Low confidence or no match means the user must mark the slot manually. A manual slot outside the video duration is rejected. The profile is stored and reused by later batches with no re-analysis.
7. **AC7 Preview gate** — a preview of row 1 is rendered through the queue. A batch cannot start until that preview is approved. Approval and start are audited.
8. **AC8 Output format (R6.1, Q7)** — every output keeps the template's resolution, fps, video codec family and audio format. Duration = template + name delta (D16) ±50 ms.
9. **AC9 Audio splice (R3.4/R3.5, D16)** — only the slot audio changes. Audio outside the slot (minus the crossfade zones) matches the template. Crossfades are 20–50 ms, and loudness of the spliced slot is within ±1 LU. Timing: time-stretch ≤ ±15 %, then pause absorption, then extension ≤ 1.5 s. Beyond that, the row fails `NAME_TOO_LONG_TO_SPEAK`. Shorter names pad the pause.
10. **AC10 AI label + metadata (C2/C3, Q8)** — every frame carries the "AI-Generated / एआई-जनित" label at the top, covering ≥ 10 % of the frame area. MP4 metadata contains the creator entity (setting), generation date and batch ID.
11. **AC11 Output folder & files (R6.2–R6.4, Q9)** — the default folder is `YYYY-MM-DD-<valid rows>`, or a custom name. An existing folder gets a `-2`/`-3` suffix; nothing is ever overwritten. Path traversal and illegal characters are rejected. Files are named `<ID>.mp4` with unsafe chars → `_`. `manifest.csv` has one line per input row, and its statuses add up to the total.
12. **AC12 Queue reliability** — rows are independent Dramatiq jobs. A crash, timeout or storage error is retried exactly once automatically. Quality failures are not retried. A re-delivered job produces no duplicate file. Disk full → `STORAGE_ERROR` with no partial file. Temp files are removed on success and on failure.
13. **AC13 Batch control** — pause stops new rows from starting and resume continues. Cancel marks unstarted rows `CANCELLED`. Retry-failed re-queues only failed rows. Submitting the same batch twice is idempotent.
14. **AC14 Status & analytics API (R7)** — overview counts (Total, Completed, Processing, Queued, Failed, Skipped, Cancelled) always add up to the total. Also: progress + ETA, failure breakdown by code, rows list with status filter, search and paging, batch history with success rate, and time-series stats (videos/day, average render time).
15. **AC15 Downloads** — a single video, ZIP of all outputs (streamed), and a failures CSV.
16. **AC16 Auth (ADR-006)** — every endpoint except login/health requires the session cookie. State-changing calls require the CSRF token. Wrong password returns 401 and repeated failures are rate-limited.
17. **AC17 Privacy (C5)** — names and IDs are encrypted at rest (no plaintext in DB rows). No fixture name or ID appears in captured logs. Deleting a batch removes its rows, files and personal data. The retention job deletes data older than N days (default 30). Audit entries survive deletion without personal data.
18. **AC18 Content lock (C6)** — the pipeline can only change the slot range. Attempting to set a slot outside the confirmed profile is rejected.
19. **AC19 Quality** — `uv run pytest` passes; `ruff check`, `ruff format --check` and `mypy --strict backend` are clean. Coverage is ≥ 85 % overall and 100 % on `domain/` and on the `render_row` pipeline service.

## Requirement tree
See `docs/requirements/REQ-001-requirement-tree.md` (confirmed by Admin 2026-10-18, decisions D1–D17). M1 covers every item tagged `[M1]` plus the API parts of R2.4 and R7. Real AI models, the quality checks Q1–Q6 and the spoken disclosure are M2. The UI is M3.

## Test tree outline (tester expands into `docs/test-tree/m1-batch-pipeline.md`)
```
M1 batch pipeline
├── Domain rules: header normalisation · row validation (each code) · ID→file name · folder name/suffix/traversal
│     · status transitions · timing plan (stretch / absorb / extend / fail) · retry policy · count invariants
│     (+ positive / negative / edge each: unicode, Devanagari, 40/41 chars, "RJ/12/097/183866", empty sheet, 1 row)
├── Ingestion: xlsx + csv streaming · mapping · BOM · extra columns · empty middle rows · 0 / 1 / 1k / 100k rows
├── Video probe: valid MP4/MOV · H.265 · renamed .txt · corrupt · over size/duration · zero-length · no audio track
├── Storage + crypto: atomic write · never overwrite · disk full · encrypt/decrypt round-trip · wrong key · blind index
├── FFmpeg engine: splice + crossfade · loudness · stretch · extension · label overlay (Devanagari) · metadata · format kept
├── API + auth: login/CSRF/rate limit · templates + consent · slot auto/manual · batches · preview gate · control · stats
│     · downloads · delete · retention · audit
├── Worker pipeline: happy path 10 rows · consent missing · TTS fake failure · timeout · crash → 1 retry
│     · redelivery idempotent · pause/resume/cancel · temp cleanup · PII-free logs · manifest
└── E2E (CPU, docker compose): synthetic 10-row batch through API + worker → folder + manifest correct
```
All fixtures are synthetic: test videos are generated with `ffmpeg -f lavfi` (testsrc + tone + silence gaps; 1080×1300 @ 60 fps, plus small/fast variants) and the names are fake. Real `samples/` are never used in automated tests.

## Tasks
Branch rule: a slice = one branch, sequential tester → developer on the same branch. Worktrees only where two agents run at the same time.

| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| T0 | Install uv, ffmpeg, Docker; move old `.venv` aside (ADR-001 steps) | **Admin** | System installs and moving folders are outside every agent's rights | Plan approval | — | — | `uv`, `ffmpeg`, `docker` on PATH |
| T1 | Write M1 test tree `docs/test-tree/m1-batch-pipeline.md` from AC1–AC19 | tester | Owns test trees; designing pos/neg/edge cases is its specialty | — | sonnet | yes `feat/tester/m1-test-tree` (parallel with T2) | Every AC maps to scenarios with pos/neg/edge |
| T2 | Tooling + skeleton: pyproject (3.11, approved deps, ruff/mypy/pytest/cov config), `uv.lock`, `.python-version`, `docker-compose.yml` (Postgres 16 + Redis 7, placeholder creds), `backend/vidgen` package with empty ports, `settings.py`, PII-free JSON logging, Alembic init (no migration) | backend-dev | Builds backend structure; D17 grants it these 4 root files | T0 | sonnet | yes `feat/backend/m1-skeleton` (parallel with T1) | `uv run pytest -q` runs; ruff + mypy clean |
| — | **Merge gate 1** (T1+T2 → main) | CEO → Admin | | T1, T2 | | | Admin says Merge |
| T3 | RED: domain unit tests (AC3, AC9 timing math, AC11 naming, statuses, retry policy, count invariants) | tester | TDD red step belongs to tester | Gate 1 | sonnet | no — `feat/m1-domain` | Tests fail for missing behaviour only |
| T4 | GREEN+REFACTOR: `domain/` | backend-dev | Pure Python business rules | T3 | sonnet | no — `feat/m1-domain` | T3 green; 100 % domain coverage |
| T5 | RED: ingestion, video probe, local storage, cipher + blind index (AC1, AC2, AC4, AC17 crypto) | tester | | Gate 1 | sonnet | yes `feat/tester/m1-ingest` (parallel with T4) | Failing tests committed |
| T6 | GREEN+REFACTOR: SheetReader, VideoProbe, LocalStorage, Cipher adapters | backend-dev | Infrastructure adapters | T4, T5 | sonnet | no — continues on `feat/m1-ingest` | T5 green |
| T7 | RED: FFmpeg engine — splice/crossfade/loudness/stretch/extension, label PNG + overlay, metadata, format preservation (AC8–AC10) | tester | | T6 | sonnet | yes `feat/tester/m1-ffmpeg` (parallel with T6 tail) | Failing tests committed |
| T8 | GREEN+REFACTOR: `infrastructure/ffmpeg/` VideoEncoder + label renderer | backend-dev | Core media code | T7 | sonnet | no — `feat/m1-ffmpeg` | T7 green; 100 % coverage on timing/splice planning |
| — | **Merge gate 2** (domain + ingest + ffmpeg → main) | CEO → Admin | | T4, T6, T8 | | | Admin says Merge |
| T9 | RED: DB models/repos, auth, templates + consent + slot API, audit (AC5, AC6, AC16, AC18) | tester | | Gate 2 | sonnet | no — `feat/m1-api-core` | Failing tests committed |
| T10 | GREEN+REFACTOR: SQLAlchemy models, **Alembic migration 0001 (created, not run)**, repositories, auth, template endpoints, audit | backend-dev | API + persistence | T9 | sonnet | no | T9 green; migration file for review |
| T11 | RED: batch API — create, validate report, preview gate, start, pause/resume/cancel, retry, stats/analytics, history, downloads, delete, retention (AC7, AC11, AC13–AC15, AC17) | tester | | T10 | sonnet | no — `feat/m1-api-batches` | Failing tests committed |
| T12 | GREEN+REFACTOR: batch services + endpoints | backend-dev | | T11 | sonnet | no | T11 green |
| T13 | RED: worker pipeline — Dramatiq actors (StubBroker), `render_row` with fakes, retries, idempotency, timeouts, disk full, cleanup, PII-free logs, manifest, per-stage timings, queue-depth metric (AC12, AC17 logs) | tester | | T12 | sonnet | no — `feat/m1-pipeline` | Failing tests committed |
| T14 | GREEN+REFACTOR: fakes, `render_row` service, Dramatiq actors | backend-dev | | T13 | sonnet | no | T13 green; 100 % coverage on `render_row` |
| T15 | VERIFY: full suite, add missing edge cases, E2E synthetic 10-row batch on CPU via docker compose, `COVERAGE.md` | tester | Independent verification | T14 | sonnet | no | All AC ✅, coverage targets met, defects reported |
| T16 | Review diff, run checks, report | CEO | | T15 | — | — | Report to Admin → **Merge gate 3** |

### Frontend (M3) — planned now, starts after M1 backend is verified
Blocked until: (a) TrustVest screenshots are in `docs/design/reference/`, and (b) **ADR-009 frontend stack** is approved (I'll present options: React + TypeScript + Vite + Tailwind + chart library vs. alternatives). These tasks get their own detailed plan `docs/plans/m3-dashboard.md`. It can run in parallel with M2 backend work in separate worktrees.

| ID | Task | Agent | Why | Depends on | Model | Worktree? |
|----|------|-------|-----|------------|-------|-----------|
| F1 | UI test tree + failing component / E2E tests | tester | TDD red | M1 merged, ADR-009 | sonnet | yes |
| F2 | App shell, design tokens from TrustVest, login screen | frontend-dev | Owns `frontend/` | F1 | sonnet | yes |
| F3 | Overview dashboard (KPI cards, progress ring, charts, recent batches) | frontend-dev | | F2 | sonnet | yes |
| F4 | New-batch wizard (upload, mapping/validation, slot + preview, folder + start) | frontend-dev | | F2 | sonnet | yes |
| F5 | Batch detail, Templates, History screens | frontend-dev | | F2 | sonnet | yes |
| F6 | Verify: UI tests, reduced-motion, empty/error states, tablet width, Hindi text | tester | | F3–F5 | sonnet | yes |

### Next milestone (M2) — separate plan
Real adapters (STT with word timestamps, Hindi transliteration, voice cloning, lip sync) with **mandatory commercial-licence checks**, vocal/music separation (see risk R1), quality gate Q1–Q6, S3 storage adapter, spoken disclosure option, GPU worker image.

## Order (TDD)
T0 → (T1 ∥ T2) → Gate 1 → T3 → T4 (∥ T5) → T6 → T7 → T8 → Gate 2 → T9 → T10 → T11 → T12 → T13 → T14 → T15 → T16 → Gate 3.
`main` only ever receives slices whose tests are green.

## Risks and mitigations
| # | Risk | Mitigation |
|---|------|------------|
| R1 | **Background music is mixed into the speech track.** Splicing a new name also cuts the music under it, so the music can "jump" (breaks R3.5). | M1 splices the mixed track (synthetic fixtures make this measurable). M2 adds vocal/music separation (e.g. a source-separation model, licence-checked): replace vocals only, then remix. Flagged now so M2 budgets for it. |
| R2 | Devanagari label shaping in Pillow needs `libraqm` | T8 test renders and checks shaped glyph width; fallback is a pre-rendered label asset |
| R3 | Root-file exception (D17) misused | Briefs list the 4 files explicitly; CEO reviews every diff to them |
| R4 | CPU encoding of 1080×1300 @ 60 fps is slow in tests | Most tests use small, short synthetic clips; one slow E2E marked `@pytest.mark.slow` |
| R5 | Fakes hide real-model problems | Ports are shaped from real model APIs (word timestamps, durations); M2 adds real quality checks |
| R6 | PII leaking into logs or errors | Log-scanning test; logging helper takes row UUIDs only |
| R7 | M1 is large | 3 merge gates with smaller reviews; 2 failed rounds on any task → stop and report to Admin |
| R8 | Docker/ffmpeg missing on the Mac | T0 is done by the Admin first |

## Migrations / dependencies (need separate approval)
**Migration:** `0001_initial` (campaigns, templates, consent, batches, rows, audit_log, stats) — created in T10, **run by the Admin** (`uv run alembic upgrade head`) only after approval.

**System tools (Admin installs, T0):** uv, ffmpeg (Homebrew, GPL build — see ADR-004), Docker Desktop. Docker images: `postgres:16`, `redis:7`.

**Font asset:** Noto Sans Devanagari (SIL OFL-1.1) → `backend/vidgen/assets/fonts/`. The Admin downloads it from Google Fonts, or approves backend-dev downloading it.

**Python packages (added in T2 via `uv add`):**
| Package | Purpose | Licence |
|---------|---------|---------|
| fastapi, uvicorn[standard] | API + server | MIT / BSD |
| python-multipart | File uploads | Apache-2.0 |
| pydantic-settings | Config from environment | MIT |
| sqlalchemy (2.x), alembic | ORM + migrations | MIT |
| psycopg[binary] (3.x) | Postgres driver | LGPL-3.0 (used as a library; fine) |
| dramatiq[redis], redis | Queue | LGPL-3.0 (library use) / MIT |
| openpyxl | .xlsx reading | MIT |
| cryptography | AES-GCM, HMAC | Apache-2.0 / BSD |
| argon2-cffi, itsdangerous | Password hash, signed cookie | MIT / BSD |
| pillow | Label PNG rendering | MIT-CMU |
| regex (+ dev: types-regex) | Grapheme-cluster counting for A1 — **approved by Admin 2026-10-18, added in T2** | Apache-2.0 |
| **dev:** pytest, pytest-cov, httpx, ruff, mypy, types-openpyxl | Tests, lint, types | MIT / BSD / Apache |

## Addendum A — clarifications from T1 review (Admin approved 2026-10-18)
These close the gaps the tester found while drafting the test tree. They are binding for all M1 tests and code.

| # | Topic | Rule |
|---|-------|------|
| A1 | Name length (AC3) | 40 = **grapheme clusters** (user-perceived characters), not code points. ZWJ (U+200D) and ZWNJ (U+200C) are allowed inside Devanagari. |
| A2 | Duplicate ID (AC3, AC11) | Compare IDs after trim → case-fold → **file-name sanitising** (R6.3). `RJ/12/097` and `rj_12_097` are duplicates, because they would produce the same file. The first row is kept. |
| A3 | Existing codes | Empty name / empty ID / duplicate → `INVALID_ROW_EMPTY_NAME`, `INVALID_ROW_EMPTY_ID`, `DUPLICATE_ID` (already in R8). |
| A4 | New codes | Upload errors: `UNSUPPORTED_VIDEO`, `CORRUPT_VIDEO`, `UNSUPPORTED_SHEET`, `COLUMN_NOT_FOUND`. Template errors: `SLOT_NOT_FOUND`, `STT_FAILED`. Row errors: `CONTENT_LOCK_VIOLATION`, `INTERNAL_ERROR` (catch-all; never retried automatically unless it is a crash). |
| A5 | Preview approval (AC7) | Changing the slot, template or column mapping after a preview **invalidates the approval**; a new preview + approval is required. |
| A6 | Cancel (AC13) | Rows already `PROCESSING` finish and are delivered. Only `QUEUED` rows become `CANCELLED`. |
| A7 | Manifest (AC11) | `manifest.csv` contains row number, name, ID, status, file name, failure code + message, render time. It is personal data: covered by retention and batch deletion. |
| A8 | Retention (AC17) | The retention job skips batches that are not finished (queued / running / paused). |
| A9 | Thresholds | AC4: peak memory for 100k-row validation ≤ 200 MB above baseline. AC9: outside the slot (excluding crossfade zones) the audio difference vs. template ≤ −40 dB RMS. AC10: label is a full-width band, height ≥ 10 % of frame height, at the top, in every sampled frame. AC16: 5 failed logins within 15 min → locked (HTTP 429) for 15 min. |
| A10 | Worktrees | The guard blocks writes under `.claude/worktrees/`. Until the Admin changes that, tasks run **sequentially in the main project folder**, one branch at a time. T1 runs on `feat/tester/m1-tree`. |

## Addendum B — closes test-tree open issues OI-1…OI-13 (Admin approved 2026-10-18)

| # | Issue | Rule |
|---|-------|------|
| B1 | OI-1 multiple faults | One primary code by priority: empty name → empty ID → bad characters → too long → duplicate. The validation report also lists every fault. |
| B2 | OI-2 codes | `CONSENT_FILE_INVALID` (consent upload wrong type/corrupt); empty or silent TTS output → `TTS_FAILED`; `OUTPUT_CHECK_FAILED` (row: output format/duration mismatch); `INVALID_FOLDER_NAME` (request error). |
| B3 | OI-3 minimum video | Must have ≥1 video and ≥1 audio stream and duration ≥ 1 s (setting); otherwise `UNSUPPORTED_VIDEO`. |
| B4 | OI-4 empty folder name | Empty/whitespace custom folder name → default name. |
| B5 | OI-5 empty ZIP | No completed rows → HTTP 409 `NO_COMPLETED_ROWS`. |
| B6 | OI-6 names in API | Logged-in admin receives decrypted name + ID in the rows API. Search by name or ID within one batch, done in the service layer (ADR-005). Never in logs or error messages. |
| B7 | OI-7 stats | ETA = remaining rows × mean render time of the last 20 completed rows (null until the first completes). Success rate = completed ÷ (completed + failed); skipped/cancelled excluded. Stored and returned in UTC; UI shows Asia/Kolkata. Previews are excluded from stats. |
| B8 | OI-8 timeouts/retries | Row render timeout 600 s (setting). Retryable = crash, `RENDER_TIMEOUT`, `STORAGE_ERROR`; 1 retry after 10 s → 2 attempts in total. `STORAGE_ERROR` = `OSError` (ENOSPC, EACCES, EIO…) or storage-adapter errors while writing outputs. |
| B9 | OI-9 sheets | First worksheet only (its name shown in the report). CSV delimiter sniffed among `,` `;` tab; otherwise `UNSUPPORTED_SHEET`. |
| B10 | OI-10 audio | Loudness per ITU-R BS.1770 / EBU R128. "Audio format" = codec + sample rate + channel layout. |
| B11 | OI-11 idempotency | `POST …/start` requires an `Idempotency-Key` header; repeating the same key returns the same result. Starting an already-started batch is a no-op returning current state. |
| B12 | OI-12 retention clock | Counts from batch finish or cancel time. Never-started drafts are deleted N days after creation. |
| B13 | OI-13 AC19 | Verified in T15 and CEO review, not by a self-referential test. |

## Addendum C — CEO engineering clarifications (test-tree NA-1…NA-3, 2026-10-18; Admin informed, may override)

| # | Issue | Rule |
|---|-------|------|
| C1 | NA-1 ETA "remaining" | remaining = `QUEUED` + `PROCESSING` rows |
| C2 | NA-2 key reuse | Same `Idempotency-Key` on a different batch → HTTP 409 `IDEMPOTENCY_KEY_CONFLICT` |
| C3 | NA-3 STT matches | Several matches → highest confidence, then earliest. Threshold is inclusive (`confidence >= threshold` counts as found). |

## Addendum D — domain contract choices from T3 (CEO accepted 2026-10-18)

| # | Rule |
|---|------|
| D-1 | A slot shorter than 2 × crossfade → `SlotTooShortError`. A zero-length manual slot is rejected. |
| D-2 | `plan_timing` only compresses longer audio (≤ 15 %); it never slows speech down. Shorter audio pads the pause (D16). |
| D-3 | Folder names are NFC-normalised; Windows reserved names (`CON`, `NUL`, …) are rejected as `INVALID_FOLDER_NAME`. |
| D-4 | Output file names: spaces and other unsafe characters → `_` (R6.3); the name is capped at 255 bytes. |
| D-5 | Accented Latin letters (é, ñ…) are **invalid** name characters (D9: ASCII A–Z/a–z only). Corrected in T3 round 2. |
| D-7 | T4 gap-fillers (CEO accepted): ZWJ/ZWNJ only between Devanagari characters · Devanagari digits and dandas are not name characters · only valid rows register their ID for duplicate detection (an invalid earlier row never blocks a later valid one) · header ambiguity → `UNSUPPORTED_SHEET`, duplicate mapping → `COLUMN_NOT_FOUND` · too-short slot → `SLOT_NOT_FOUND` · state-machine errors are plain exceptions (programming errors, not user-facing) · a quality failure without a specific code → `OUTPUT_CHECK_FAILED`. |
| D-8 | T5 infrastructure contracts (CEO accepted): separate `VideoProbe` port (`FfprobeVideoProbe`, `VideoLimits`, `VideoInfo`) instead of `VideoEncoder.probe` · unreadable media → `CORRUPT_VIDEO`; wrong container/codec, no audio, too short/long/big → `UNSUPPORTED_VIDEO`; ffprobe timeout or missing binary → `INTERNAL_ERROR` · storage key collision → `name-2.ext`… (never overwrite); `OSError` → `STORAGE_ERROR`; delete is idempotent · cipher: 32-byte AES keys, index key ≥ 32 bytes, empty string allowed, blind index = hex HMAC-SHA256 over `id_key(value)`, `repr` never shows keys · reader: missing/empty/non-UTF-8/undetectable-delimiter → `UNSUPPORTED_SHEET`. **Max-rows check moves to the batch service (T11).** Odd-dimension video not tested (ffmpeg cannot produce it). |
| D-9 | T6 accepted: `ports/models.py` (SheetRow, VideoInfo, VideoLimits) · first *visible* xlsx sheet · rows padded to header width · mp4/mov told apart by `major_brand` · storage publishes via `os.link` (cannot overwrite; needs a hard-link-capable filesystem; the S3 adapter in M2 uses conditional put instead). |
| D-10 | **AI label style (Admin 2026-10-18):** opaque solid band across the full width at the top, height ≥ 10 % of frame height (e.g. 130 px on 1080×1300), light text on a dark band, bilingual "AI-Generated / एआई-जनित", on every frame. It covers the top of the template; the resolution never changes (R6.1). |
| D-11 | **Video extension in M1 (Admin 2026-10-18):** when the timing plan extends the video (D16), the video frames under the slot are retimed (played slower) to cover slot + extension; no frozen frame. M2 lip sync replaces these frames. |
| D-12 | **Devanagari text shaping (Admin 2026-10-19):** the label renderer requires Pillow's complex-text layout (raqm). New **system dependency `libraqm`** (dev: `brew install libraqm` + symlink the dylibs into `/usr/local/lib`, see ADR-001 "Devanagari text shaping"; GPU worker image in M2: the distro's libraqm package). A test asserts shaping is active, so the label never ships unshaped. Speech stretch uses `atempo` in M1 (this FFmpeg build has no rubberband); revisit in M2 with the real voice. |
| D-13 | **The target word is per template (CEO, 2026-10-19, from REQ-001 §1):** each template stores `original_name`, the spoken voter name to replace ("Krishan" in the sample). It is given at template creation and used by slot detection. It is not a global setting, and never "ji". |
| D-14 | **Migration 0001 rules (Admin 2026-10-19):** (1) upgrade only creates tables and indexes: no drop, alter or data changes; (2) downgrade drops exactly those tables in reverse order; (3) PII columns (name, spoken_name, voter_id) are encrypted bytes, plus a blind-index column; no plaintext PII columns; (4) an automated test (Admin-approved) runs upgrade → downgrade → upgrade on a separate throwaway DB `vidgen_migration_test` (name guard: must end in `_test`) and asserts that the migrated schema matches the models (autogenerate diff empty); it never touches the `vidgen` dev DB; (5) `migrations/env.py` needs **only** the DB URL (no secrets/full Settings); (6) the Admin runs it on the dev DB after CEO review and explicit approval. |
| D-15 | **Login protection (Admin 2026-10-19, revised the same day), refines A9:** (1) **Per client:** 5 failures from one client within 15 min lock that client for 15 min (HTTP 429 + Retry-After; the correct password is refused too). (2) **Global cap → throttle, not lock:** after 50 failures from all clients within 15 min, *all* login attempts are rate-limited for 15 min to 1 attempt per 5 s globally (429 + short Retry-After). A correct password inside the allowed rate still succeeds, so an attacker can slow the admin's login but never block it. (3) **Existing sessions are never affected** by either rule; only `/auth/login` is limited. (4) **Alert:** crossing the global cap writes one `SECURITY_LOGIN_THROTTLED` audit event per window (no passwords, no PII), shown on the dashboard in M3. (5) **Client address:** the direct peer address, unless the peer is in the setting `trusted_proxies` (list of IPs/CIDRs, **empty by default**). Only then is `X-Forwarded-For` used, taking the right-most address that is not itself a trusted proxy. Thresholds, throttle rate and window are settings. |
| D-16 | T9 contracts accepted: API codes `UNAUTHENTICATED`, `INVALID_CREDENTIALS`, `CSRF_FAILED`, `RATE_LIMITED`, `NOT_FOUND`, `VALIDATION_ERROR` · oversize upload 413, storage failure 507, STT failure 502 · template `usable` = consent confirmed + slot confirmed; editing the slot un-confirms it · no transliteration in M1, so a Latin `original_name` vs a Devanagari transcript → manual slot (M2 adds transliteration). |
| D-17 | **T10 review fixes (CEO, 2026-10-19):** (1) login-protection state (per-client failures, global throttle window, alert window) is persisted in Postgres (a table in 0001), not in-process (stateless API rule), and shared across API instances and restarts; (2) a partial unique index on `batch_rows(batch_id, voter_id_index) WHERE status <> 'SKIPPED'`, so the DB itself prevents two renderable rows with the same ID; (3) an index on `batches(finished_at)` for the retention job. Migration 0001 is amended before anyone runs it. |
| D-18 | T10 round-2 choices (CEO accepted; **Admin confirmed 2026-10-19**): `login_attempts(campaign_id, client_key, window_started_at, failure_count, locked_until, last_allowed_at)`, PK (campaign_id, client_key), global row key `*`, row-locked per attempt, stale rows pruned on write · failure counting uses a **fixed window from the first failure** (not sliding). Same long-run rate; at most a short burst across a window boundary. Acceptable for M1; revisit if needed · the repository raises the raw `IntegrityError` for a live duplicate. **The batch service (T12) must map it to `DUPLICATE_ID`** so the API never returns a 500 for it (T11 tests will check this). |
| D-6 | The public domain API (module + function names) is the one defined by the T3 tests (`vidgen.domain.{codes,headers,validation,naming,status,timing,retry,stats,slot_match}`). |

## Admin approval
- [x] Plan approved (includes ADR-001 + ADR-008) — 2026-10-18
- [x] Dependencies, system tools and font approved — 2026-10-18 (Admin downloads the font)
- [ ] Task assignment approved
- [x] Migration 0001 run approved — 2026-10-19 (Admin runs it; final file reviewed: 7 tables, create-only, reverse downgrade, encrypted PII, migration test 9/9)
- [ ] Merge gates 1 / 2 / 3 approved

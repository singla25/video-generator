# Tester — Coverage (M1 verification, 2026-10-19)

Command: `uv run pytest tests -q -m "slow or not slow" --cov=vidgen --cov-branch`
Result: **1611 passed, 1 xfailed** (148 s, after the file split). Also clean: `ruff check`, `ruff format --check`, `mypy --strict backend` (86 files).

## Coverage

Total: **98.2 %** (lines + branches: 4044 of 4099 statements, 457 of 484 branches). Targets: 85 % overall, 100 % on domain and `render_row`.

| Layer | Coverage | Lines | Branches |
|-------|----------|-------|----------|
| domain | **100 %** | 462/462 | 64/64 |
| ports | 100 % | 292/292 | 2/2 |
| worker | **100 %** | 79/79 | 6/6 |
| services (incl. `render_row`, 100 %) | 98.7 % | 1186/1199 | 138/142 |
| infrastructure | 97.5 % | 1248/1272 | 172/184 |
| api | 97.1 % | 664/679 | 65/72 |
| root (`settings`, `logging`) | 94.6 % | 113/116 | 10/14 |

### Modules below 100 % and why

| Module | % | Uncovered | Reason |
|--------|---|-----------|--------|
| infrastructure/consent.py | 88.9 | 24-25, 42 | error branches of the content sniffer (wrong types are covered) |
| api/container.py | 89.2 | 48, 69-77 | "not configured" placeholders (real STT/queue arrive in M2/ops wiring) |
| infrastructure/sheets/reader.py | 93.3 | 42, 80, 90, 134-135 | defensive branches (unusual workbook states) |
| settings.py | 93.8 | 88, 103, 118 | key-decoding error branches |
| api/uploads.py | 94.3 | 117, 146-149, 173 | size-limit and stream-closing branches that need a real network client |
| infrastructure/ffmpeg/probe.py | 94.3 | 39-40, 114-115, 132-133 | OS-level error branches of the tool runner |
| infrastructure/db/uow.py, logging.py | 95-96 | branches only | rollback and handler-reuse branches |
| infrastructure/storage/local.py | 96.1 | 40, 63, 129 | OS error branches |
| services/templates.py | 96.1 | 98-100, 126-128 | defensive branches |
| 10 more modules | 96-99.4 | 1-4 lines each | one-line defensive branches |

No uncovered line is on the happy path of a feature; all are error or defensive branches.

## Tests

| Kind | Count |
|------|-------|
| Test functions | 875 (about 1600 cases with parametrisation) |
| tagged positive (first tree ID is `P`) | 248 |
| tagged negative (`N`) | 194 |
| tagged edge (`E`) | 264 |
| other (domain rules, contracts, helpers without a tree ID) | 169 |
| xfail (strict, documented limit: range requests) | 1 |

Tree: 374 cases from `docs/test-tree/m1-batch-pipeline.md` (105 P, 98 N, 171 E); 17 further cases were added in T15; every ID is either referenced by a test or listed with a reason under "Verification status" in the tree (n/a, M2, covered by named test, procedure).

## Acceptance criteria

| AC | Status | Key test files |
|----|--------|----------------|
| AC1 Video upload | ✅ | integration/ingest/test_video_probe.py, api/test_templates.py |
| AC2 Sheet upload | ✅ | ingest/test_sheet_reader.py, api/test_batches_create.py |
| AC3 Row validation | ✅ | unit/domain/test_row_validation.py, api/test_batches_create.py |
| AC4 Validation speed | ✅ | ingest/test_sheet_scale.py (100k rows, slow), api/test_batches_extra.py |
| AC5 Consent gate | ✅ | api/test_templates.py, worker/test_render_row.py |
| AC6 Template profile | ✅ | api/test_template_profile.py |
| AC7 Preview gate | ✅ | api/test_batches_start.py, worker/test_preview_job.py |
| AC8 Output format | ✅ | ffmpeg/test_output_format.py, test_output_extra.py |
| AC9 Audio splice | ✅ | ffmpeg/test_audio_splice.py, unit/domain/test_timing_plan.py |
| AC10 Label + metadata | ✅ | ffmpeg/test_label_overlay.py, test_metadata.py, unit/infra/test_label_renderer.py (shaping: raqm) |
| AC11 Folder and files | ✅ | unit/domain/test_folder_names.py, test_file_names.py, worker/test_completion.py |
| AC12 Queue reliability | ✅ | worker/test_render_row.py, test_row_states.py, test_worker.py |
| AC13 Batch control | ✅ | api/test_batches_control.py, worker/test_row_states.py |
| AC14 Status and analytics | ✅ | api/test_batches_status.py |
| AC15 Downloads | ✅ (range requests: known limit) | api/test_batches_downloads.py, test_batches_extra.py |
| AC16 Auth | ✅ | api/test_auth.py, test_login_persistence.py |
| AC17 Privacy | ✅ | db/test_repositories.py, worker/test_render_row.py (logs), api/test_batches_delete_retention.py, e2e |
| AC18 Content lock | ✅ | unit/domain/test_content_lock.py, worker/test_render_row.py |
| AC19 Quality | ✅ | pytest, ruff, mypy and coverage above; unit/meta/test_architecture.py |

**19 of 19 ✅.** Also green: end-to-end run (`tests/e2e`, 10-row batch, crash retry, deletion).

## Defects and known limits

| ID | Kind | Detail |
|----|------|--------|
| V1 | code rule, resolved | `batch_store.py` (384 lines) and `render_row.py` (330) were split (a11472d); every source file is now at most 300 lines (`unit/meta/test_architecture.py`). |
| V2 | limit | Byte-range requests on single-video download are not supported (`test_range_requests_on_a_single_video_return_partial_content`, strict xfail). Needed for a seeking player in M3. |
| V3 | limit (ADR-006) | The signed session cookie is stateless: a copied cookie works until it expires or `session_version` is bumped. |

No functional defect was found in the M1 flows during verification.

## Known M1 limitations (by design)

- All AI is fake: speech-to-text, voice (a tone whose length follows the text), lip sync (pass-through), quality checks Q1-Q6. Real models, music separation and the spoken disclosure are M2.
- Speech stretch uses `atempo`; this FFmpeg build has no rubberband.
- The pause after the name is a configured value (`pause_seconds`); measuring it per template is M2.
- Lip sync does not exist yet; the slot frames are only retimed (D-11). The 25-fps lip-sync model constraint is an M2 topic.
- Latin names are not transliterated to match Devanagari transcripts (manual slot instead).
- Devanagari shaping needs `libraqm` on the machine (a test enforces it).
- Odd-dimension videos cannot be produced with the test tooling and are not tested.


---

# M3 operator dashboard — verification (F6, 2026-10-19)

Stack used: throwaway database `vidgen_e2e_<hex>_test` (Alembic `upgrade head`), API (uvicorn, `ai_backend=fake`), one Dramatiq worker (own queue name, Redis db 7), Vite dev server, Playwright Chromium. Started and stopped by `tests/frontend/e2e/run_stack.py` (run with `PYTHONPATH=. uv run python tests/frontend/e2e/run_stack.py`); database dropped, no process left. Screenshots: `media/review/ui/` (overview, wizard-step3, batch-detail, templates, security).

## Results

| Suite | Result |
|---|---|
| Vitest | **178 / 178** pass (8 files + new-template) |
| Vitest coverage (`frontend/src`) | **93.35 % lines**, 91.97 % statements, 83.77 % branches, 88.92 % functions (target 85 %) |
| Playwright, real stack (desktop + reduced-motion + tablet) | **43 pass, 2 fail** (same axe case on the Overview in two projects, defect D-F6-3) |
| Main flow (desktop) | pass: login, template + consent upload, wizard (sheet with 2 invalid rows, mapping, preview, approval, start), progress to Completed, batch detail, ZIP (200, `PK`), 3 videos rendered |
| axe | no serious/critical on Templates, History, Security, New batch; **Overview with data: color-contrast serious** (status chips) |
| Privacy (running app) | no request to a host other than 127.0.0.1; no names/IDs in local/session storage; no TrustVest text (also source scan in unit tests) |

Coverage per folder (lines): src 79 % (main.tsx is the bootstrap, not covered), api 100 %, components 95 %, pages 91 %, pages/batch 94 %, pages/templates 100 % (after the new form tests), pages/wizard 92 %. Gaps: `main.tsx` 13-28, `PlaceholderPage.tsx` (Settings/Help stub), `TemplatesPage` 19-26/34, `StepUpload` 45-51/85-88 (drag and drop), `ConfirmDialog` line 28, `CurrentBatchPanel` 57-66.

## UI acceptance criteria

| AC | Status | Evidence / note |
|---|---|---|
| UI-AC1 Design fidelity | ⏳ Admin sign-off | Screenshots in `media/review/ui/`. Observed: the weekly chart bar renders solid emerald although a hatch pattern is defined in `VideosChart.tsx`; check in F7 |
| UI-AC2 Layout | ✅ | shell unit tests, tablet E2E (no horizontal overflow, header action visible) |
| UI-AC3 Overview | ✅ | KPI sum, polling every 2 s, error/empty/skeleton, reduced motion; real data screenshot |
| UI-AC4 Rows table | ✅ | chips, Devanagari, search/filter/paging, per-row retry, 1,000-row paging |
| UI-AC5 Wizard | ✅ with defect D-F6-1 | whole flow works on the real stack; a new template cannot become usable from the UI (no slot confirm) |
| UI-AC6 Batch detail | ✅ | actions, confirmations, failure filter (server side), ZIP download on the real stack |
| UI-AC7 Templates | ✅ | consent badge, consent upload (real stack), new template form (unit + real stack) |
| UI-AC8 History / Security | ✅ | audit list, filter, throttle banner (unit); real audit entries shown |
| UI-AC9 Auth | ✅ | login, 401, 429 countdown, CSRF header (unit); real login |
| UI-AC10 States and motion | ✅ | skeleton, empty, error, reduced motion (unit + real stack) |
| UI-AC11 Hindi | ✅ | `lang="hi"`, Devanagari rows in table and ZIP flow; font face loads locally |
| UI-AC12 Privacy | ✅ | see Results |
| UI-AC13 Quality | ❌ until D-F6-3 | coverage 93 %, typecheck/lint green; axe has one serious violation on the Overview |

## Defects found

| ID | Severity | Description |
|---|---|---|
| D-F6-1 | high (blocks real use with the fake/any STT that finds no slot) | A new template cannot become usable from the UI. The slot editor only does `PUT slot`; the backend needs `POST slot/confirm` before `usable` is true, and the Templates page and wizard offer no confirm or analyse action. The step 1 list therefore keeps the template disabled. The E2E test seeds the slot through the API to continue |
| D-F6-2 | medium (dev setup) | The Vite dev proxy forwards `/templates`, `/batches` and `/audit` to the API for every request, including browser page loads. A refresh or a pasted deep link on the Templates, New batch or Batch detail page returns API JSON/401 instead of the app. Needs a proxy `bypass` for requests that accept `text/html` (or an API prefix such as `/api`) |
| D-F6-3 | serious (axe) | Colour contrast on the Overview with data: status chips (`.bg-blue-50`, `.bg-slate-100`, `.bg-red-50`, `.bg-amber-50.text-status-skipped`) are below 4.5:1 |

## Observations (not defects)

- The "vs last week" pill shows "-" when there is no earlier week; fine, but the label reads oddly.
- Concurrent pytest runs share nothing now (DD-20); the E2E runner uses its own database and queue name.


## M3 re-verification (F6 round 2, 2026-10-20)

Fixes verified: slot confirm in the UI, API under the api prefix, AA chip colours, hatched bars. Same real stack as before (throwaway DB `vidgen_e2e_<hex>_test`, stopped and dropped at the end).

| Suite | Result |
|---|---|
| Python | **1745 passed** (full suite, ruff clean) |
| Vitest | **207 / 207**; coverage `frontend/src` **92.98 % lines** (91.44 % statements, 84.39 % branches) |
| Playwright, real stack (desktop 1440x900, reduced-motion, tablet 768) | **47 pass, 1 fail** |
| Main flow | pass: template + consent, slot set and **confirmed in the UI**, wizard, preview, approval, start, Completed, ZIP |
| Deep link / refresh on Templates, New batch, History | pass (app renders, not JSON) |
| API only under the api prefix | pass |
| axe (Overview with data, Templates, History, Security, New batch; all three projects) | **0 serious/critical** |
| Requests to hosts other than 127.0.0.1 | none |
| Names/IDs in browser storage, TrustVest text | none |

Screenshots (1440x900, plus tablet): `media/review/ui/` overview, overview-tablet, wizard-step3, batch-detail, templates, security.

### Defect found

| ID | Severity | Description |
|---|---|---|
| D-F6-4 | medium | Overview at 768 px width with data scrolls horizontally: the chart, current batch and rows cards are wider than the header (page width about 946 px, `scrollWidth > innerWidth`). The KPI grid wraps correctly; the cards below it do not shrink. Test: `TT-UI-E2E-E1` (tablet project). It passed earlier only because the page had no data yet |

D-F6-1, D-F6-2 and D-F6-3 are fixed and verified.

### UI acceptance criteria (updated)

| AC | Status |
|---|---|
| UI-AC1 Design fidelity | awaiting visual sign-off (hatched bars now present; screenshots ready) |
| UI-AC2 Layout | ❌ tablet width overflows with data (D-F6-4); desktop ✅ |
| UI-AC3 Overview | ✅ |
| UI-AC4 Rows table | ✅ |
| UI-AC5 Wizard | ✅ (template made usable in the UI) |
| UI-AC6 Batch detail | ✅ |
| UI-AC7 Templates | ✅ |
| UI-AC8 History / Security | ✅ |
| UI-AC9 Auth | ✅ |
| UI-AC10 States and motion | ✅ |
| UI-AC11 Hindi | ✅ |
| UI-AC12 Privacy | ✅ |
| UI-AC13 Quality | ✅ (coverage 93 %, axe 0 serious/critical) |


## M3 final verification (2026-10-20, after D-F6-4 and the visual polish)

| Suite | Result |
|---|---|
| Playwright, real stack (desktop 1440x900, reduced-motion, tablet 768; throwaway DB dropped, nothing left running) | **48 / 48 pass**, including `TT-UI-E2E-E1` (no horizontal scroll at 768 px with data) |
| axe on all pages, all projects | 0 serious/critical |
| Requests to hosts other than 127.0.0.1 | none |
| Python (`-m "slow or not slow"`) | **1745 passed**; ruff check and format clean |
| Vitest | **207 / 207**; coverage `frontend/src` **93.07 % lines** (91.53 % statements, 84.75 % branches) |
| Typecheck, ESLint, Prettier | clean |

Screenshots refreshed in `media/review/ui/`: overview, overview-tablet, wizard-step3, batch-detail, templates, security.

D-F6-4 is fixed and verified. No open defects.

| AC | Status |
|---|---|
| UI-AC1 Design fidelity | awaiting Admin visual sign-off |
| UI-AC2 Layout | ✅ (tablet overflow fixed) |
| UI-AC3 to UI-AC13 | ✅ |

## M2-local real AI (L1, L1b, L6a, L6b), 2026-10-28

Run: `pytest --ignore=tests/unit/infra/ai --ignore=tests/e2e` = 2002 passed, 1 skipped (local_ai smoke). e2e not run (only Postgres is up in Docker, no full stack). `ruff check`, `ruff format --check` clean; `mypy --strict backend/vidgen/infrastructure/local_ai` clean (13 files). Total backend line+branch coverage 97 %.

| Area | Tests (approx) | Notes |
|---|---|---|
| Mode switch, errors, guards, name slot, adapters (tests/unit/ai_local) | positive ~30, negative ~25, edge ~30 | stubbed models, no torch |
| MuseTalk support + model (test_musetalk_support, test_musetalk_model) | 37 | real ffmpeg on tiny clips; fake torch/musetalk/cv2 modules |
| confirm-spelling API (tests/integration/api/test_confirm_spelling.py) | 28 | encrypted storage, no log leak, 409/422 paths |
| SqlRowStore._spoken_name | 9 | preview row vs others, blank fallback |
| ai_mode status, UI (ai-mode.test.tsx) | 7 + 17 | |

local_ai coverage per file: errors, guard, lipsync, name_slot, stt 100 %; musetalk_support 94 %; tts 94 %; _common 93 %; factory 92 %; transliterate 90 %; loaders 86 %; offline 84 %. Package about 92 %. Uncovered: real Whisper/Qwen/Chatterbox loader bodies (loaders.py 38-102, covered only by `@local_ai` smoke tests), offline.py 39-50 (IPv6/edge socket paths), musetalk_support.py 62-65, 78 (bad frame-rate text, no-frames branch).

Defects: none open. Notes: tests/unit/infra/ai (G3 set, other module layout) is excluded and not part of this run. `running_batch`/`approve_preview` helpers do not confirm spelling, so they cannot be used in local mode.

## 2026-11-13 - Docker and cloud setup, Stage 1 (T1-T3) verified
- Full suite (not slow, not e2e): 2653 passed, 2 skipped, 12 deselected. tests/unit/meta: 634 passed.
- Docker e2e (project vidgen-t3test): 2 passed; no containers, volumes or networks of that project remain.
- Coverage: scripts/setup.py 99 % (uncovered: line 267, the `__main__` guard), scripts/dev_setup.py hash-password part 100 % (file total 53 %: older commands out of scope).
- Counts (new tests): installer positive ~33, negative ~40, edge ~30; static Docker checks ~35; rendered compose 6; e2e 2.
- Lint: ruff check and format clean; mypy --strict backend/vidgen + scripts/setup.py clean.
- Defects found in verify: none. Earlier (T1c/T3 reviews): key loss on overwrite, Ctrl-D traceback, token message, null Modal vars in compose, unpinned uv; all fixed.
- Not covered yet: Modal adapters (T4, held), port-in-use, multi-arch build, restart-keeps-data.

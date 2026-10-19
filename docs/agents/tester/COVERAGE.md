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

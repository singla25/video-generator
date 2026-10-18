# Test tree — M1 batch pipeline (AC1–AC19)

**Plan:** `docs/plans/m1-batch-pipeline.md` (incl. Addendum A, binding) · **Requirements:** `docs/requirements/REQ-001-requirement-tree.md` · **ADRs:** 001–008
**Author:** tester · **Task:** T1 · **Date:** 2026-10-18

## Conventions
- **ID format:** `TT-AC<n>-<P|N|E><k>` (Positive / Negative / Edge).
- **Level:** U = unit (fakes, seconds), I = integration (real FFmpeg / DB / StubBroker / FastAPI TestClient), E = e2e (docker compose, `@pytest.mark.slow`).
- **File:** planned path under `tests/`. Several cases may share a file.
- Failure codes come from R8 + Addendum A3/A4. Codes marked `(code?)` are still unnamed (see Open Issues).
- All data is synthetic (see "Fixtures"). No `samples/` files. Names are fake.
- Fakes: `FakeVideoEngine`, `FakeStorage`, `FakeSTT`, `FakeTTS`, `FakeClock`, Dramatiq `StubBroker`.

Planned layout: `tests/unit/{domain,services,infra,meta}/`, `tests/integration/{ingest,ffmpeg,storage,db,api,worker}/`, `tests/e2e/`, `tests/conftest.py`, `tests/fixtures/` (generators only, no binaries).

---

## Feature: AC1 — Video upload and probe

### Scenario: user uploads a template video
| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC1-P1 | ✅ | MP4 H.264+AAC within limits → accepted; probe returns container, codec, size, fps, duration, has_audio | I | integration/ingest/test_video_probe.py |
| TT-AC1-P2 | ✅ | MOV H.264 → accepted | I | same |
| TT-AC1-P3 | ✅ | MP4 H.265 → accepted | I | same |
| TT-AC1-P4 | ✅ | MOV H.265 → accepted | I | same |
| TT-AC1-N1 | ❌ | WebM/VP9 or MKV → `UNSUPPORTED_VIDEO`, storage empty | I | integration/api/test_template_upload.py |
| TT-AC1-N2 | ❌ | MP4 with MPEG-4 Part 2 (or ProRes) codec → `UNSUPPORTED_VIDEO` | I | integration/ingest/test_video_probe.py |
| TT-AC1-N3 | ❌ | text file renamed `clip.mp4` → `CORRUPT_VIDEO` (ffprobe, not extension); nothing stored | I | integration/api/test_template_upload.py |
| TT-AC1-N4 | ❌ | valid MP4 renamed `clip.txt` → ACCEPTED (type from content, not extension) | I | same |
| TT-AC1-N5 | ❌ | truncated MP4 (first 30 % of bytes) → `CORRUPT_VIDEO`, no stored file | I | same |
| TT-AC1-N6 | ❌ | file over max-size setting (lowered to a few KB) → rejected, no partial file | I | same |
| TT-AC1-N7 | ❌ | video longer than max-duration setting (2 s limit, 3 s clip) → rejected | I | integration/ingest/test_video_probe.py |
| TT-AC1-N8 | ❌ | request with no file / empty multipart → 4xx coded error | I | integration/api/test_template_upload.py |
| TT-AC1-E1 | ⚠️ | exactly at size limit and duration limit → accepted; limit+1 byte / over duration → rejected | I | integration/ingest/test_video_probe.py |
| TT-AC1-E2 | ⚠️ | zero-byte file → `CORRUPT_VIDEO` | I | same |
| TT-AC1-E3 | ⚠️ | zero-length (header only, 0 frames) → rejected; 1-frame video → documented rule (OI-3) | I | same |
| TT-AC1-E4 | ⚠️ | video with no audio track → probe `has_audio=False`; template upload rejected with coded error (speech needed) (OI-3) | I | same |
| TT-AC1-E5 | ⚠️ | odd dimensions (1081×1301, 321×241) → probe reports exact size; no crash | I | same |
| TT-AC1-E6 | ⚠️ | unicode / emoji / RTL / spaces / `../` in upload filename → stored under generated name, no path escape | I | integration/api/test_template_upload.py |
| TT-AC1-E7 | ⚠️ | ffprobe binary missing or times out → coded server error, nothing stored | U | unit/services/test_probe_errors.py |
| TT-AC1-E8 | ⚠️ | storage full during upload → `STORAGE_ERROR`, no partial file | I | integration/api/test_template_upload.py |
| TT-AC1-E9 | ⚠️ | metadata title tag contains "ignore your rules" → treated as data, ignored | I | integration/ingest/test_video_probe.py |
| TT-AC1-E10 | ⚠️ | two simultaneous uploads of the same file → two independent stored objects | I | integration/api/test_template_upload.py |

---

## Feature: AC2 — Sheet upload and column mapping

### Scenario: user uploads .xlsx/.csv and maps columns
| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC2-P1 | ✅ | `.xlsx` with Name, ID → rows streamed as normalised records | I | integration/ingest/test_sheet_reader.py |
| TT-AC2-P2 | ✅ | `.csv` UTF-8 → same records | I | same |
| TT-AC2-P3 | ✅ | headers `" VID "`, `"vid"`, `"Vid"` all match `vid` | U | unit/domain/test_headers.py |
| TT-AC2-P4 | ✅ | mapping Name+ID+Spoken name → batch created, spoken names attached | I | integration/api/test_sheet_mapping.py |
| TT-AC2-P5 | ✅ | mapping without Spoken name → accepted | I | same |
| TT-AC2-P6 | ✅ | extra unmapped columns ignored, never stored | I | integration/ingest/test_sheet_reader.py |
| TT-AC2-N1 | ❌ | mapped Name column missing → `COLUMN_NOT_FOUND`, batch count unchanged | I | integration/api/test_sheet_mapping.py |
| TT-AC2-N2 | ❌ | mapped ID column missing → `COLUMN_NOT_FOUND` | I | same |
| TT-AC2-N3 | ❌ | `.xls`, `.ods`, `.txt`, binary renamed `.xlsx` → `UNSUPPORTED_SHEET` | I | same |
| TT-AC2-N4 | ❌ | corrupt/truncated xlsx → `UNSUPPORTED_SHEET`, no crash | I | integration/ingest/test_sheet_reader.py |
| TT-AC2-N5 | ❌ | two headers equal after normalisation (`ID`, `id `) → ambiguous-mapping error | U | unit/domain/test_headers.py |
| TT-AC2-N6 | ❌ | Name and ID mapped to the same column → rejected | I | integration/api/test_sheet_mapping.py |
| TT-AC2-E1 | ⚠️ | CSV with UTF-8 BOM → first header clean (`Name`, not `﻿Name`) | I | integration/ingest/test_sheet_reader.py |
| TT-AC2-E2 | ⚠️ | CSV with quoted commas and embedded newline in a cell | I | same |
| TT-AC2-E3 | ⚠️ | empty file; headers only (0 data rows) → zero-rows error, no batch | I | same |
| TT-AC2-E4 | ⚠️ | empty rows in the middle and at the end → skipped; reported row numbers match sheet rows | I | same |
| TT-AC2-E5 | ⚠️ | 1 data row → batch of 1 | I | same |
| TT-AC2-E6 | ⚠️ | numeric ID cell `183866.0` → `183866`; formula cell → cached value | I | same |
| TT-AC2-E7 | ⚠️ | multi-sheet xlsx → first sheet used; hidden sheet ignored (OI-9) | I | same |
| TT-AC2-E8 | ⚠️ | Devanagari header `नाम` selectable in mapping | I | integration/api/test_sheet_mapping.py |
| TT-AC2-E9 | ⚠️ | cells like `=HYPERLINK(...)` or "ignore rules" → plain data; never executed | I | integration/ingest/test_sheet_reader.py |
| TT-AC2-E10 | ⚠️ | sheet filename with unicode / `../` → sanitised | I | integration/api/test_sheet_mapping.py |
| TT-AC2-E11 | ⚠️ | CSV with `;` or tab delimiter → documented outcome (OI-9) | I | integration/ingest/test_sheet_reader.py |

---

## Feature: AC3 — Row validation (A1, A2, A3)

### Scenario: each row is validated against settings
| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC3-P1 | ✅ | `Rajesh Kumar`, ID `RJ12` → VALID | U | unit/domain/test_row_validation.py |
| TT-AC3-P2 | ✅ | `राजेश कुमार` → VALID | U | same |
| TT-AC3-P3 | ✅ | `Dr. Anne-Marie O'Neil` → VALID | U | same |
| TT-AC3-P4 | ✅ | mixed `Smt. सुनीता Devi` → VALID | U | same |
| TT-AC3-P5 | ✅ | first of two rows with same ID stays VALID | U | same |
| TT-AC3-P6 | ✅ | validation report API returns valid/skipped counts and per-row code + message | I | integration/api/test_validation_report.py |
| TT-AC3-P7 | ✅ | Devanagari name with ZWJ/ZWNJ inside (conjunct) → VALID (A1) | U | unit/domain/test_row_validation.py |
| TT-AC3-N1 | ❌ | empty / whitespace-only name → `INVALID_ROW_EMPTY_NAME`, row SKIPPED | U | same |
| TT-AC3-N2 | ❌ | empty ID → `INVALID_ROW_EMPTY_ID` | U | same |
| TT-AC3-N3 | ❌ | later duplicate ID → `DUPLICATE_ID`; message names the earlier row number | U | same |
| TT-AC3-N4 | ❌ | name of 41 graphemes → `INVALID_ROW_NAME_TOO_LONG` | U | same |
| TT-AC3-N5 | ❌ | digits, `@`, `_`, `/`, `<script>`, emoji, Arabic, CJK letters → `INVALID_ROW_BAD_CHARACTERS` | U | same |
| TT-AC3-N6 | ❌ | row with several faults reports one deterministic primary code (OI-1) | U | same |
| TT-AC3-N7 | ❌ | SKIPPED rows never enqueue a job (queue empty) | I | integration/worker/test_skipped_never_rendered.py |
| TT-AC3-N8 | ❌ | ZWJ/ZWNJ between Latin letters or standing alone → `INVALID_ROW_BAD_CHARACTERS` (allowed only inside Devanagari) | U | unit/domain/test_row_validation.py |
| TT-AC3-E1 | ⚠️ | exactly 40 graphemes (Latin) valid; 41 invalid | U | same |
| TT-AC3-E2 | ⚠️ | Devanagari 40 graphemes (~55+ code points with matras/virama) valid; 41 graphemes invalid (proves grapheme not code-point counting) | U | same |
| TT-AC3-E3 | ⚠️ | limit set to 10 in settings → rule follows setting | U | same |
| TT-AC3-E4 | ⚠️ | surrounding whitespace trimmed before checks; stable handling of inner double spaces | U | same |
| TT-AC3-E5 | ⚠️ | duplicates by A2: `RJ/12/097` vs `rj_12_097`, `RJ12` vs ` rj12 ` → `DUPLICATE_ID`; `RJ12` vs `RJ012` not duplicates | U | same |
| TT-AC3-E6 | ⚠️ | ID `RJ/12/097/183866` valid | U | same |
| TT-AC3-E7 | ⚠️ | NBSP, full-width Latin, RTL override, zero-width space → bad characters | U | same |
| TT-AC3-E8 | ⚠️ | 10,000-char name → too-long code, fast, no regex blow-up | U | same |
| TT-AC3-E9 | ⚠️ | same ID three times → rows 2 and 3 both name row 1 | U | same |
| TT-AC3-E10 | ⚠️ | invalid Spoken name → same code family; empty Spoken name falls back to name | U | same |
| TT-AC3-E11 | ⚠️ | all rows invalid → batch cannot start; report still produced | I | integration/api/test_validation_report.py |
| TT-AC3-E12 | ⚠️ | IDs with Devanagari characters casefold/sanitise consistently | U | unit/domain/test_row_validation.py |

---

## Feature: AC4 — Validation speed and streaming

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC4-P1 | ✅ | 1,000-row xlsx validates in < 3 s | I | integration/ingest/test_sheet_scale.py |
| TT-AC4-P2 | ✅ | 1,000-row csv < 3 s | I | same |
| TT-AC4-P3 | ✅ | 100,000-row csv: peak memory ≤ 200 MB above baseline (A9) and 10k→100k growth is bounded (flat) | I | same (slow) |
| TT-AC4-P4 | ✅ | 100,000-row xlsx read-only: ≤ 200 MB above baseline | I | same (slow) |
| TT-AC4-N1 | ❌ | corrupt cell data at row 50,000 → coded error, no partial batch committed | I | same |
| TT-AC4-N2 | ❌ | rows above configurable max-rows → rejected early | I | same |
| TT-AC4-E1 | ⚠️ | 0 rows → zero-rows error | I | same |
| TT-AC4-E2 | ⚠️ | 1 row | I | same |
| TT-AC4-E3 | ⚠️ | 1,000 rows all duplicates / all invalid still < 3 s (O(n) duplicate detection) | I | same |
| TT-AC4-E4 | ⚠️ | reader is lazy: first row available before whole file read | U | unit/services/test_streaming_reader.py |
| TT-AC4-E5 | ⚠️ | exception mid-stream → file handles closed, temp upload removed | I | integration/ingest/test_sheet_scale.py |

---

## Feature: AC5 — Consent gate (C1)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC5-P1 | ✅ | PDF consent + tick → template usable | I | integration/api/test_consent.py |
| TT-AC5-P2 | ✅ | PNG and JPG consent → usable | I | same |
| TT-AC5-P3 | ✅ | consent stored with profile; audit `CONSENT_UPLOADED` with actor, template id, time, no personal data | I | same |
| TT-AC5-P4 | ✅ | batch on consented template renders | I | integration/worker/test_consent_missing.py |
| TT-AC5-N1 | ❌ | no consent file → template unusable; batch start refused | I | integration/api/test_consent.py |
| TT-AC5-N2 | ❌ | file but no tick → unusable | I | same |
| TT-AC5-N3 | ❌ | tick but no file → unusable | I | same |
| TT-AC5-N4 | ❌ | rows of a consent-less template fail `CONSENT_MISSING` in worker, not retried | I | integration/worker/test_consent_missing.py |
| TT-AC5-N5 | ❌ | `.exe`, `.txt`, `.docx`, binary renamed `.pdf` → rejected by content type, nothing stored (error code OI-2) | I | integration/api/test_consent.py |
| TT-AC5-E1 | ⚠️ | zero-byte PDF, corrupt PNG, truncated JPG → rejected | I | same |
| TT-AC5-E2 | ⚠️ | consent over size limit → rejected | I | same |
| TT-AC5-E3 | ⚠️ | replacing consent keeps old audit entry and adds new | I | same |
| TT-AC5-E4 | ⚠️ | consent removed after batch queued → pending rows `CONSENT_MISSING` | I | integration/worker/test_consent_missing.py |
| TT-AC5-E5 | ⚠️ | PDF containing JavaScript/instruction text → opaque data, never executed | I | integration/api/test_consent.py |
| TT-AC5-E6 | ⚠️ | unicode consent filename → generated storage name | I | same |
| TT-AC5-E7 | ⚠️ | second batch on same profile inherits consent | I | same |

---

## Feature: AC6 — Template profile and slot analysis

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC6-P1 | ✅ | FakeSTT returns word + timestamps + high confidence → slot set, source `AUTO` | U | unit/services/test_template_analysis.py |
| TT-AC6-P2 | ✅ | manual slot inside duration → accepted, source `MANUAL` | I | integration/api/test_template_profile.py |
| TT-AC6-P3 | ✅ | second batch with same template → STT spy called 0 times | I | same |
| TT-AC6-P4 | ✅ | analysis uses only the `SpeechToText` port | U | unit/services/test_template_analysis.py |
| TT-AC6-N1 | ❌ | confidence below threshold → `SLOT_NOT_FOUND` path: needs manual slot, profile unconfirmed | U | same |
| TT-AC6-N2 | ❌ | target word not found → `SLOT_NOT_FOUND`, manual marking required | U | same |
| TT-AC6-N3 | ❌ | manual slot end > video duration → rejected | I | integration/api/test_template_profile.py |
| TT-AC6-N4 | ❌ | start ≥ end, negative, NaN/inf, missing fields → 422 | I | same |
| TT-AC6-N5 | ❌ | STT port raises → `STT_FAILED`, profile unconfirmed, no crash | U | unit/services/test_template_analysis.py |
| TT-AC6-N6 | ❌ | batch start on unconfirmed profile refused | I | integration/api/test_template_profile.py |
| TT-AC6-E1 | ⚠️ | slot [0, duration] boundary; zero-length slot | U | same |
| TT-AC6-E2 | ⚠️ | multiple matches → documented pick (highest confidence, then first) | U | unit/services/test_template_analysis.py |
| TT-AC6-E3 | ⚠️ | confidence exactly at threshold → documented side (accepted) | U | same |
| TT-AC6-E4 | ⚠️ | template without audio → analysis refuses | U | same |
| TT-AC6-E5 | ⚠️ | re-analysis replaces profile and is audited | I | integration/api/test_template_profile.py |
| TT-AC6-E6 | ⚠️ | concurrent analysis requests → one profile | I | same |
| TT-AC6-E7 | ⚠️ | ms vs s confusion blocked by explicit unit in schema | I | same |

---

## Feature: AC7 — Preview gate (A5)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC7-P1 | ✅ | preview requested → runs via queue/worker; status `PREVIEW_READY` | I | integration/worker/test_preview_render.py |
| TT-AC7-P2 | ✅ | approve → start allowed → rows queued | I | integration/api/test_preview_gate.py |
| TT-AC7-P3 | ✅ | audit has `PREVIEW_APPROVED` and `BATCH_STARTED` (actor, time) | I | same |
| TT-AC7-P4 | ✅ | preview uses first VALID row | U | unit/services/test_batch_state.py |
| TT-AC7-N1 | ❌ | start without preview → 409, no jobs | I | integration/api/test_preview_gate.py |
| TT-AC7-N2 | ❌ | start with unapproved preview → 409 | I | same |
| TT-AC7-N3 | ❌ | preview render fails → batch not startable | I | integration/worker/test_preview_render.py |
| TT-AC7-N4 | ❌ | approve before preview ready → rejected | I | integration/api/test_preview_gate.py |
| TT-AC7-N5 | ❌ | engine spy has 0 calls inside the HTTP handler | I | same |
| TT-AC7-N6 | ❌ | slot change after approval → approval invalidated, start → 409 until new preview + approval | I | same |
| TT-AC7-N7 | ❌ | template change after approval → invalidated | I | same |
| TT-AC7-N8 | ❌ | column mapping change after approval → invalidated | I | same |
| TT-AC7-E1 | ⚠️ | batch with exactly 1 valid row | I | same |
| TT-AC7-E2 | ⚠️ | double approval / double start → idempotent, one audit entry each | I | same |
| TT-AC7-E3 | ⚠️ | preview file excluded from output folder and manifest | I | integration/worker/test_preview_render.py |
| TT-AC7-E4 | ⚠️ | preview worker crash → one retry, then failure surfaced | I | same |
| TT-AC7-E5 | ⚠️ | preview artefact deleted with batch | I | integration/api/test_delete_batch.py |
| TT-AC7-E6 | ⚠️ | re-approval after invalidation audited as separate entry | I | integration/api/test_preview_gate.py |

---

## Feature: AC8 — Output format preserved

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC8-P1 | ✅ | H.264 template → output same width, height, fps, codec family, audio codec/sample rate/channels | I | integration/ffmpeg/test_output_format.py |
| TT-AC8-P2 | ✅ | H.265 template → H.265 output | I | same |
| TT-AC8-P3 | ✅ | MOV template → `.mp4` output with same stream properties | I | same |
| TT-AC8-P4 | ✅ | duration = template + name delta ±50 ms for longer, shorter and equal names | I | same |
| TT-AC8-P5 | ✅ | full-size 1080×1300 @ 60 fps keeps resolution and fps (slow) | I | same |
| TT-AC8-N1 | ❌ | engine (fake) returns wrong resolution/fps → row fails format check (code OI-2), output removed | U | unit/services/test_render_row_format_check.py |
| TT-AC8-N2 | ❌ | duration off by > 50 ms → check fails, no output delivered | U | unit/domain/test_duration_delta.py |
| TT-AC8-E1 | ⚠️ | variable-frame-rate template → no drift beyond 50 ms | I | integration/ffmpeg/test_output_format.py |
| TT-AC8-E2 | ⚠️ | odd dimensions preserved or clear error | I | same |
| TT-AC8-E3 | ⚠️ | delta 0 and exactly ±50 ms boundary | U | unit/domain/test_duration_delta.py |
| TT-AC8-E4 | ⚠️ | frame-rounding at 60, 25, 29.97 fps | U | same |
| TT-AC8-E5 | ⚠️ | colour range / primaries / rotation tag preserved | I | integration/ffmpeg/test_output_format.py |

---

## Feature: AC9 — Audio splice and timing plan (A9)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC9-P1 | ✅ | new audio = slot length → no stretch, absorb or extension | U | unit/domain/test_timing_plan.py |
| TT-AC9-P2 | ✅ | 10 % longer → stretch within ±15 % only | U | same |
| TT-AC9-P3 | ✅ | longer than stretch allows but fits pause → max stretch + absorb, no extension | U | same |
| TT-AC9-P4 | ✅ | longer than stretch+pause → extension ≤ 1.5 s, video grows by delta | U | same |
| TT-AC9-P5 | ✅ | shorter name → pause padded, duration unchanged | U | same |
| TT-AC9-P6 | ✅ | order is exactly stretch → absorb → extend | U | same |
| TT-AC9-P7 | ✅ | outside slot (excluding crossfade zones) audio difference vs template ≤ −40 dB RMS | I | integration/ffmpeg/test_audio_splice.py |
| TT-AC9-P8 | ✅ | crossfade 20–50 ms, verified in plan and waveform | I | same |
| TT-AC9-P9 | ✅ | slot loudness within ±1 LU of template (ebur128) | I | same |
| TT-AC9-N1 | ❌ | extension needed > 1.5 s → `NAME_TOO_LONG_TO_SPEAK`, no output, no retry | U | unit/domain/test_timing_plan.py |
| TT-AC9-N2 | ❌ | via worker with FakeTTS emitting very long audio → row FAILED with that code, no partial file | I | integration/worker/test_name_too_long.py |
| TT-AC9-N3 | ❌ | TTS returns empty/zero-length audio → coded failure (OI-2) | U | unit/services/test_render_row_tts.py |
| TT-AC9-N4 | ❌ | crossfade setting outside 20–50 ms → settings validation error | U | unit/domain/test_timing_plan.py |
| TT-AC9-E1 | ⚠️ | stretch exactly 15 % → stretch only; 15.01 % → absorb used | U | same |
| TT-AC9-E2 | ⚠️ | extension exactly 1.5 s ok; +1 ms fails | U | same |
| TT-AC9-E3 | ⚠️ | max extension changed via settings | U | same |
| TT-AC9-E4 | ⚠️ | zero-length pause after slot | U | same |
| TT-AC9-E5 | ⚠️ | slot at 0 s and at end of template (no room for crossfade) | I | integration/ffmpeg/test_audio_splice.py |
| TT-AC9-E6 | ⚠️ | slot shorter than 2 × crossfade | U | unit/domain/test_timing_plan.py |
| TT-AC9-E7 | ⚠️ | mono/stereo, 44.1/48 kHz | I | integration/ffmpeg/test_audio_splice.py |
| TT-AC9-E8 | ⚠️ | silent TTS output → loudness undefined handled (fail with code) | I | same |
| TT-AC9-E9 | ⚠️ | music bed under slot: documents known limit (plan risk R1) | I | same |
| TT-AC9-E10 | ⚠️ | property test: random lengths → plan components always sum to target length | U | unit/domain/test_timing_plan.py |

---

## Feature: AC10 — AI label and metadata (A9)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC10-P1 | ✅ | label "AI-Generated / एआई-जनित": full-width band at top, height ≥ 10 % of frame height | I | integration/ffmpeg/test_label_overlay.py |
| TT-AC10-P2 | ✅ | sampled frames (first, middle, last, around crossfade) all have the band | I | same |
| TT-AC10-P3 | ✅ | Devanagari shaped (rendered width differs from unshaped, or fallback asset used) | I | unit/infra/test_label_renderer.py |
| TT-AC10-P4 | ✅ | MP4 tags: creator entity, ISO generation date, batch ID | I | integration/ffmpeg/test_metadata.py |
| TT-AC10-N1 | ❌ | creator-entity setting empty → config error, no render | U | unit/infra/test_metadata_settings.py |
| TT-AC10-N2 | ❌ | overlay step fails → row FAILED, no unlabelled output delivered | I | integration/ffmpeg/test_label_overlay.py |
| TT-AC10-N3 | ❌ | missing font asset → clear error, not blank label | U | unit/infra/test_label_renderer.py |
| TT-AC10-E1 | ⚠️ | 320×240, portrait, landscape, 1080×1300 → band ≥ 10 % height in each | I | integration/ffmpeg/test_label_overlay.py |
| TT-AC10-E2 | ⚠️ | band exactly 10 % passes, 9.9 % fails | U | unit/infra/test_label_renderer.py |
| TT-AC10-E3 | ⚠️ | bright / dark top region → label readable (luminance contrast) | I | integration/ffmpeg/test_label_overlay.py |
| TT-AC10-E4 | ⚠️ | unicode / Devanagari / RTL creator string round-trips in metadata | I | integration/ffmpeg/test_metadata.py |
| TT-AC10-E5 | ⚠️ | very long creator string → truncated or rejected, no crash | U | unit/infra/test_metadata_settings.py |
| TT-AC10-E6 | ⚠️ | metadata holds no voter name/ID | I | integration/ffmpeg/test_metadata.py |
| TT-AC10-E7 | ⚠️ | label present in extension region (video grown) | I | integration/ffmpeg/test_label_overlay.py |
| TT-AC10-E8 | ⚠️ | file still probe-valid after metadata written | I | integration/ffmpeg/test_metadata.py |

---

## Feature: AC11 — Output folder and files (A2, A7)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC11-P1 | ✅ | no custom name, 2026-10-18, 7 valid rows → `2026-10-18-7` (FakeClock) | U | unit/domain/test_folder_names.py |
| TT-AC11-P2 | ✅ | custom folder `Ward 12 Campaign` accepted | U | same |
| TT-AC11-P3 | ✅ | existing folder → `-2`, then `-3`; originals untouched | I | integration/storage/test_local_storage.py |
| TT-AC11-P4 | ✅ | ID `183866` → `183866.mp4` | U | unit/domain/test_file_names.py |
| TT-AC11-P5 | ✅ | ID `RJ/12/097/183866` → `RJ_12_097_183866.mp4` | U | same |
| TT-AC11-P6 | ✅ | manifest.csv: one line per input row (incl. skipped/failed) with row number, name, ID, status, file name, code + message, render time (A7) | I | integration/worker/test_manifest.py |
| TT-AC11-P7 | ✅ | manifest status counts sum to total rows | I | same |
| TT-AC11-N1 | ❌ | folder `../../etc`, `/abs`, `..\\x`, `a/../b`, `.`, `..` → rejected | U | unit/domain/test_folder_names.py |
| TT-AC11-N2 | ❌ | `<>:"|?*`, NUL, control chars, trailing dot/space, reserved names (`CON`) → rejected | U | same |
| TT-AC11-N3 | ❌ | empty / whitespace custom name → documented outcome (OI-4) | U | same |
| TT-AC11-N4 | ❌ | symlink in output root pointing outside → refused | I | integration/storage/test_local_storage.py |
| TT-AC11-N5 | ❌ | IDs `A/1` and `A_1` map to same file → second is `DUPLICATE_ID` (A2), so no overwrite is possible | U | unit/domain/test_file_names.py |
| TT-AC11-E1 | ⚠️ | folders up to `-50` exist → next `-51` | I | integration/storage/test_local_storage.py |
| TT-AC11-E2 | ⚠️ | name longer than 255 bytes, Devanagari multi-byte → deterministic truncate or reject | U | unit/domain/test_file_names.py |
| TT-AC11-E3 | ⚠️ | unicode / emoji / RTL / spaces in custom folder → allowed, NFC-normalised | U | unit/domain/test_folder_names.py |
| TT-AC11-E4 | ⚠️ | ID `///` → `___.mp4`; `.hidden` → not a hidden file | U | unit/domain/test_file_names.py |
| TT-AC11-E5 | ⚠️ | case-insensitive FS: `abc` vs `ABC` are duplicates (casefold, A2) | U | same |
| TT-AC11-E6 | ⚠️ | 0 valid rows → folder `…-0` never created | U | unit/domain/test_folder_names.py |
| TT-AC11-E7 | ⚠️ | midnight rollover: date taken at batch start | U | same |
| TT-AC11-E8 | ⚠️ | two batches pick same folder concurrently → distinct folders (atomic mkdir) | I | integration/storage/test_local_storage.py |
| TT-AC11-E9 | ⚠️ | atomic write: crash mid-write leaves no `<ID>.mp4` | I | same |
| TT-AC11-E10 | ⚠️ | manifest escapes commas, quotes, newlines; leading `= + - @` neutralised; Devanagari names intact | I | integration/worker/test_manifest.py |
| TT-AC11-E11 | ⚠️ | manifest removed with batch deletion and retention (personal data, A7) | I | integration/api/test_delete_batch.py |

---

## Feature: AC12 — Queue reliability

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC12-P1 | ✅ | 10-row happy path → 10 independent jobs, all COMPLETED | I | integration/worker/test_retry_policy.py |
| TT-AC12-P2 | ✅ | crash → exactly one automatic retry → success | I | same |
| TT-AC12-P3 | ✅ | timeout → exactly one retry | I | same |
| TT-AC12-P4 | ✅ | storage error → exactly one retry | I | same |
| TT-AC12-P5 | ✅ | temp files removed after success | I | integration/worker/test_temp_cleanup.py |
| TT-AC12-P6 | ✅ | re-delivered job → one output file, one COMPLETED, one manifest line | I | integration/worker/test_idempotency.py |
| TT-AC12-P7 | ✅ | pure retry policy: failure kind → retryable / attempts left | U | unit/domain/test_retry_policy.py |
| TT-AC12-N1 | ❌ | crash twice → FAILED after exactly 2 attempts | I | integration/worker/test_retry_policy.py |
| TT-AC12-N2 | ❌ | quality failures (`NAME_TOO_LONG_TO_SPEAK`, `CONSENT_MISSING`, `CONTENT_LOCK_VIOLATION`) → zero retries | I | same |
| TT-AC12-N3 | ❌ | disk full (ENOSPC) → `STORAGE_ERROR` after retry, no partial file | I | integration/worker/test_disk_full.py |
| TT-AC12-N4 | ❌ | temp files removed on failure and timeout | I | integration/worker/test_temp_cleanup.py |
| TT-AC12-N5 | ❌ | non-crash unexpected exception → `INTERNAL_ERROR`, not auto-retried (A4), logged without PII | I | integration/worker/test_retry_policy.py |
| TT-AC12-E1 | ⚠️ | timeout mid-FFmpeg → subprocess killed, no orphan, temp cleaned | I | integration/worker/test_timeout.py |
| TT-AC12-E2 | ⚠️ | worker dies after output written, before status saved → redelivery marks COMPLETED, no duplicate | I | integration/worker/test_idempotency.py |
| TT-AC12-E3 | ⚠️ | worker dies mid-render → redelivery cleans stale temp, renders | I | same |
| TT-AC12-E4 | ⚠️ | 2 workers on 20 rows → each rendered exactly once; counts invariant | I | integration/worker/test_concurrency.py |
| TT-AC12-E5 | ⚠️ | same message to 2 workers simultaneously → second is a no-op (row lock) | I | same |
| TT-AC12-E6 | ⚠️ | backoff is a setting; zero in tests | U | unit/domain/test_retry_policy.py |
| TT-AC12-E7 | ⚠️ | storage unavailable → retried once, then `STORAGE_ERROR` | I | integration/worker/test_disk_full.py |
| TT-AC12-E8 | ⚠️ | job for deleted batch → dropped quietly | I | integration/worker/test_idempotency.py |
| TT-AC12-E9 | ⚠️ | queue-depth metric and per-stage timings emitted | I | integration/worker/test_metrics.py |
| TT-AC12-E10 | ⚠️ | restart with COMPLETED rows → untouched | I | integration/worker/test_idempotency.py |
| TT-AC12-E11 | ⚠️ | only legal status transitions; terminal states immutable | U | unit/domain/test_status_transitions.py |

---

## Feature: AC13 — Batch control (A6)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC13-P1 | ✅ | pause → no new row starts; QUEUED stay QUEUED | I | integration/worker/test_pause_cancel.py |
| TT-AC13-P2 | ✅ | resume → remaining rows complete | I | same |
| TT-AC13-P3 | ✅ | cancel → QUEUED rows `CANCELLED`; completed files kept | I | same |
| TT-AC13-P4 | ✅ | retry-failed → only FAILED rows re-queued | I | integration/api/test_batch_control.py |
| TT-AC13-P5 | ✅ | same batch submitted twice → one batch, one set of jobs | I | same |
| TT-AC13-P6 | ✅ | cancel while rows PROCESSING → they finish and are delivered (A6) | I | integration/worker/test_pause_cancel.py |
| TT-AC13-N1 | ❌ | pause finished/cancelled batch → 409 | I | integration/api/test_batch_control.py |
| TT-AC13-N2 | ❌ | resume a non-paused batch → 409 | I | same |
| TT-AC13-N3 | ❌ | retry-failed with no failed rows → no jobs, clear message | I | same |
| TT-AC13-N4 | ❌ | unknown batch → 404 | I | same |
| TT-AC13-N5 | ❌ | retry of `CONSENT_MISSING` rows while consent missing → fail again, no loop | I | same |
| TT-AC13-E1 | ⚠️ | PROCESSING rows never end `CANCELLED` | I | integration/worker/test_pause_cancel.py |
| TT-AC13-E2 | ⚠️ | pause→cancel works; cancel→resume rejected | I | same |
| TT-AC13-E3 | ⚠️ | repeated pause/resume/cancel → idempotent | I | integration/api/test_batch_control.py |
| TT-AC13-E4 | ⚠️ | cancel with 0 QUEUED rows | I | same |
| TT-AC13-E5 | ⚠️ | retry-failed twice quickly → queued once | I | same |
| TT-AC13-E6 | ⚠️ | retried row reuses its file name; no `-2` duplicates | I | same |
| TT-AC13-E7 | ⚠️ | after cancel manifest/count sums = total | I | integration/worker/test_manifest.py |
| TT-AC13-E8 | ⚠️ | paused batch survives worker restart | I | integration/worker/test_pause_cancel.py |
| TT-AC13-E9 | ⚠️ | cancel on 1,000-row batch is a bulk operation (fast) | I | integration/api/test_batch_control.py |

---

## Feature: AC14 — Status and analytics API

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC14-P1 | ✅ | overview Total/Completed/Processing/Queued/Failed/Skipped/Cancelled; parts sum to Total at every sampled moment | I | integration/api/test_batch_status.py |
| TT-AC14-P2 | ✅ | progress % and ETA (FakeClock) | I | same |
| TT-AC14-P3 | ✅ | failure breakdown by code | I | same |
| TT-AC14-P4 | ✅ | rows list: status filter, ID search, paging, stable order | I | integration/api/test_batch_rows.py |
| TT-AC14-P5 | ✅ | batch history with success rate | I | integration/api/test_history_stats.py |
| TT-AC14-P6 | ✅ | time series: videos/day, average render time | I | same |
| TT-AC14-N1 | ❌ | bad filter / page=0 / huge page size / negative → 422 | I | integration/api/test_batch_rows.py |
| TT-AC14-N2 | ❌ | unknown batch → 404 | I | integration/api/test_batch_status.py |
| TT-AC14-N3 | ❌ | search by name is unsupported (ID blind index only) → documented response (OI-6) | I | integration/api/test_batch_rows.py |
| TT-AC14-E1 | ⚠️ | 0 completed → ETA null, no division by zero | I | integration/api/test_batch_status.py |
| TT-AC14-E2 | ⚠️ | all rows skipped | I | same |
| TT-AC14-E3 | ⚠️ | property test: invariants over random status mixes | U | unit/domain/test_count_invariants.py |
| TT-AC14-E4 | ⚠️ | polling while counts change → each response self-consistent (single snapshot) | I | integration/api/test_batch_status.py |
| TT-AC14-E5 | ⚠️ | ID search with slashes and Devanagari (URL-encoding) | I | integration/api/test_batch_rows.py |
| TT-AC14-E6 | ⚠️ | day boundary for videos/day (UTC, FakeClock) | I | integration/api/test_history_stats.py |
| TT-AC14-E7 | ⚠️ | empty history; 1,000 batches paged | I | same |
| TT-AC14-E8 | ⚠️ | 100k-row batch status via aggregate query (constant query count, slow) | I | integration/api/test_batch_status.py |
| TT-AC14-E9 | ⚠️ | decrypted name only on explicit rows endpoint (OI-6) | I | integration/api/test_batch_rows.py |

---

## Feature: AC15 — Downloads

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC15-P1 | ✅ | single video: bytes equal file, `video/mp4`, safe Content-Disposition | I | integration/api/test_downloads.py |
| TT-AC15-P2 | ✅ | ZIP has exactly COMPLETED files (+ manifest); streamed, memory bounded | I | same |
| TT-AC15-P3 | ✅ | failures CSV: one line per FAILED/SKIPPED row with code + message | I | same |
| TT-AC15-N1 | ❌ | row not completed → coded 404/409 | I | same |
| TT-AC15-N2 | ❌ | ZIP with zero completed → documented (OI-5) | I | same |
| TT-AC15-N3 | ❌ | failures CSV with no failures → header only | I | same |
| TT-AC15-N4 | ❌ | `../` in path params → 404/422 | I | same |
| TT-AC15-E1 | ⚠️ | Devanagari / slash IDs → RFC 5987 filename, safe ZIP entry names, no zip-slip | I | same |
| TT-AC15-E2 | ⚠️ | file missing on disk but row COMPLETED → clear error, ZIP skips with note | I | same |
| TT-AC15-E3 | ⚠️ | 1,000 files streamed; client abort closes handles (slow) | I | same |
| TT-AC15-E4 | ⚠️ | Range request on single video | I | same |
| TT-AC15-E5 | ⚠️ | >4 GiB ZIP uses zip64 (simulated sizes) | U | unit/services/test_zip_stream.py |
| TT-AC15-E6 | ⚠️ | failures CSV cells starting `= + - @` neutralised | I | integration/api/test_downloads.py |
| TT-AC15-E7 | ⚠️ | download mid-render includes only completed rows | I | same |

---

## Feature: AC16 — Authentication (A9: 5 failures / 15 min → 429 for 15 min)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC16-P1 | ✅ | correct password → 200 + session cookie (HttpOnly, SameSite) | I | integration/api/test_auth.py |
| TT-AC16-P2 | ✅ | `/health`, `/login` open | I | same |
| TT-AC16-P3 | ✅ | cookie + valid CSRF → POST/PUT/PATCH/DELETE succeed | I | same |
| TT-AC16-P4 | ✅ | GET with cookie works without CSRF | I | same |
| TT-AC16-P5 | ✅ | logout invalidates session | I | same |
| TT-AC16-P6 | ✅ | iterate `app.routes`: all except login/health → 401 without cookie | I | same |
| TT-AC16-N1 | ❌ | wrong password → 401, generic message | I | same |
| TT-AC16-N2 | ❌ | missing/wrong CSRF on state-changing call → 403 | I | same |
| TT-AC16-N3 | ❌ | tampered / expired / garbage cookie → 401 | I | same |
| TT-AC16-N4 | ❌ | 5 failed logins within 15 min → 6th returns 429 with Retry-After; correct password also blocked during lockout | I | same |
| TT-AC16-N5 | ❌ | password stored only as argon2 hash, never logged | U | unit/services/test_auth.py |
| TT-AC16-E1 | ⚠️ | 4 failures still 401; 5th triggers lock; lock lifts after 15 min (FakeClock); failures older than 15 min don't count | I | integration/api/test_auth.py |
| TT-AC16-E2 | ⚠️ | unicode / 1 MB / empty password → 401/422, no crash | I | same |
| TT-AC16-E3 | ⚠️ | concurrent failed logins (2 threads) counted correctly | I | same |
| TT-AC16-E4 | ⚠️ | cookie replay after logout → 401 | I | same |
| TT-AC16-E5 | ⚠️ | CSRF token from another session rejected | I | same |
| TT-AC16-E6 | ⚠️ | missing admin-password config → app refuses to start (no default) | U | unit/services/test_auth.py |
| TT-AC16-E7 | ⚠️ | multipart uploads also require CSRF | I | integration/api/test_auth.py |

---

## Feature: AC17 — Privacy (C5; A7, A8)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC17-P1 | ✅ | AES-GCM round trip for name, spoken name, ID (incl. Devanagari) | U | unit/infra/test_cipher.py |
| TT-AC17-P2 | ✅ | raw SELECT / DB dump has no plaintext fixture names or IDs | I | integration/db/test_pii_at_rest.py |
| TT-AC17-P3 | ✅ | blind index deterministic for the same A2-normalised ID, different for different ID | U | unit/infra/test_cipher.py |
| TT-AC17-P4 | ✅ | `caplog` over whole 10-row run (API + worker) holds no `PII_CANARIES` | I | integration/worker/test_pii_free_logs.py |
| TT-AC17-P5 | ✅ | delete batch → rows, files, preview, manifest, personal data gone (DB + disk) | I | integration/api/test_delete_batch.py |
| TT-AC17-P6 | ✅ | retention deletes finished batches older than N days (default 30), keeps newer | I | integration/api/test_retention.py |
| TT-AC17-P7 | ✅ | audit entries survive deletion/retention without personal data | I | integration/api/test_audit.py |
| TT-AC17-N1 | ❌ | wrong key → `DecryptionError`, no plaintext | U | unit/infra/test_cipher.py |
| TT-AC17-N2 | ❌ | tampered ciphertext/tag/nonce → auth failure | U | same |
| TT-AC17-N3 | ❌ | missing/short key → startup error; keys not in logs or `repr(settings)` | U | same |
| TT-AC17-N4 | ❌ | exceptions from validation/render contain no name/ID | I | integration/worker/test_pii_free_logs.py |
| TT-AC17-N5 | ❌ | delete unknown batch → 404; without auth → 401 | I | integration/api/test_delete_batch.py |
| TT-AC17-N6 | ❌ | no API to modify/delete audit entries | I | integration/api/test_audit.py |
| TT-AC17-N7 | ❌ | retention skips queued / running / paused batches even if old (A8) | I | integration/api/test_retention.py |
| TT-AC17-E1 | ⚠️ | 10,000 encryptions of same value → all ciphertexts differ | U | unit/infra/test_cipher.py |
| TT-AC17-E2 | ⚠️ | key rotation: old key-id rows still decrypt | U | same |
| TT-AC17-E3 | ⚠️ | empty, 40-char, 1 MB, NUL-containing inputs | U | same |
| TT-AC17-E4 | ⚠️ | blind index uses same trim→casefold→sanitise as AC3-E5 | U | same |
| TT-AC17-E5 | ⚠️ | retention exactly N days vs N days + 1 s | I | integration/api/test_retention.py |
| TT-AC17-E6 | ⚠️ | batch finishes later: becomes eligible only then | I | same |
| TT-AC17-E7 | ⚠️ | file already missing / storage unavailable on delete → DB purge still done, error reported | I | integration/api/test_delete_batch.py |
| TT-AC17-E8 | ⚠️ | delete while worker holds job → job drops, no output resurrected | I | same |
| TT-AC17-E9 | ⚠️ | temp dirs and ZIP caches purged | I | same |
| TT-AC17-E10 | ⚠️ | FFmpeg stderr / temp paths use row UUIDs, never names/IDs | I | integration/worker/test_pii_free_logs.py |
| TT-AC17-E11 | ⚠️ | log helper takes row UUID only; passing a name is an error | U | unit/infra/test_logging.py |

---

## Feature: AC18 — Content lock (C6)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC18-P1 | ✅ | edit plan inside confirmed slot (+ extension region) allowed | U | unit/services/test_content_lock.py |
| TT-AC18-P2 | ✅ | output outside slot (excl. crossfade, label, extension) equals template (frame hashes / PSNR) | I | integration/ffmpeg/test_content_lock.py |
| TT-AC18-N1 | ❌ | range outside slot → `CONTENT_LOCK_VIOLATION` | U | unit/services/test_content_lock.py |
| TT-AC18-N2 | ❌ | API: slot outside confirmed profile → 4xx | I | integration/api/test_content_lock.py |
| TT-AC18-N3 | ❌ | engine port called with out-of-slot range → guard raises before any file written | U | unit/services/test_content_lock.py |
| TT-AC18-E1 | ⚠️ | range equals slot boundaries exactly | U | same |
| TT-AC18-E2 | ⚠️ | 1 ms outside slot rejected | U | same |
| TT-AC18-E3 | ⚠️ | multiple ranges, one bad → whole plan rejected | U | same |
| TT-AC18-E4 | ⚠️ | after re-confirming a new slot the old slot is no longer allowed | I | integration/api/test_content_lock.py |
| TT-AC18-E5 | ⚠️ | lip-sync fake touches only mouth region within slot frames | I | integration/ffmpeg/test_content_lock.py |
| TT-AC18-E6 | ⚠️ | profile slot fields cannot be patched once batches exist | I | integration/api/test_content_lock.py |

---

## Feature: AC19 — Quality gates (meta)

| ID | Type | Input → expected | Level | File |
|----|------|------------------|-------|------|
| TT-AC19-P1 | ✅ | `uv run pytest` exit 0 | E | command, checked in T15 |
| TT-AC19-P2 | ✅ | `ruff check`, `ruff format --check` clean | E | tests/unit/meta/test_quality_gates.py (slow) |
| TT-AC19-P3 | ✅ | `mypy --strict backend` clean | E | same |
| TT-AC19-P4 | ✅ | coverage ≥ 85 % overall; 100 % `domain/` and `render_row` (parse coverage JSON) | E | same |
| TT-AC19-N1 | ❌ | planted lint/type violation in temp copy is detected (sanity) | E | same |
| TT-AC19-E1 | ⚠️ | `domain/` imports no framework or I/O modules (AST test) | U | tests/unit/meta/test_architecture.py |
| TT-AC19-E2 | ⚠️ | no `print(` or bare `except:` in `backend/` | U | same |
| TT-AC19-E3 | ⚠️ | no hard-coded absolute paths/URLs/keys in `backend/` | U | same |
| TT-AC19-E4 | ⚠️ | files ≲ 300 lines; public symbols have docstrings | U | same |
| TT-AC19-E5 | ⚠️ | tests hermetic: network and `samples/` access fail the test (guard fixture) | U | tests/conftest.py |
| TT-AC19-E6 | ⚠️ | marker audit: tests over 1 s are `slow`/integration | U | tests/unit/meta/test_quality_gates.py |

---

## Cross-cutting E2E (`tests/e2e/test_synthetic_batch_e2e.py`, slow, docker compose, CPU)

| ID | Type | Input → expected | Level |
|----|------|------------------|-------|
| TT-E2E-P1 | ✅ | 10-row batch (8 valid, 1 duplicate, 1 too long): login → upload video, consent, sheet → map → analyse → preview → approve → start → folder `YYYY-MM-DD-8` has 8 `.mp4`, manifest has 10 lines summing to 10, labels + metadata present, ZIP + failures CSV download | E |
| TT-E2E-E1 | ⚠️ | kill a worker container mid-batch → one retry, batch completes, no duplicates | E |
| TT-E2E-E2 | ⚠️ | delete batch → disk and DB free of personal data; audit remains | E |

---

## Fixtures (synthetic only, generated into `tmp_path`, never committed)
Generators live in `tests/fixtures/` (code, not binaries).

**Video** (`make_video(duration, size, fps, vcodec, container, with_audio)` via `ffmpeg -f lavfi`)
- Picture: `testsrc2` with running frame counter so frames hash differently. Audio: `sine` tone with silent gaps; the "name slot" (about 1.0–1.6 s) holds a distinct frequency followed by silence (the pause). Default small: 320×240 @ 25 fps, 3–4 s, mono 16 kHz. Full-size variant: 1080×1300 @ 60 fps, 4 s (slow).
- Variants: H.265 (`hvc1`), MOV, no audio, variable frame rate, odd dimensions, quiet music-bed tone under speech (AC9-E9, risk R1), bright and dark top bands.
- Broken files: truncated copy (30 % of bytes), zero-byte, text named `clip.mp4`, real MP4 named `clip.txt`, WebM/VP9, MKV, MPEG-4 Part 2, header-only (0 frames), metadata title with an instruction string.
- Limit probes: a few-KB file with a lowered size setting; 3 s clip with a 2 s limit.

**Sheets** (builders for csv and xlsx via stdlib/openpyxl)
- csv UTF-8, UTF-8-BOM, quoted comma/newline, `;` and tab; xlsx with 0, 1, 1,000, 100,000 rows (100k streamed to disk, slow); headers `" VID "`, `Name`, `नाम`, post-normalisation duplicates; empty middle/trailing rows; numeric ID cells; formula and multi-sheet workbooks; formula-injection cells.
- Fake names: `Rajesh Kumar`, `राजेश कुमार`, `Smt. सुनीता Devi`, `Dr. Anne-Marie O'Neil`, 40/41-grapheme Latin and Devanagari (with matras/virama/ZWJ), bad-character names (`Raj3sh`, `A_B`, `<b>x</b>`, emoji, Arabic, CJK), 10,000-char name, NBSP / full-width / RTL-override variants.
- Fake IDs: `183866`, `RJ/12/097/183866`, `RJ/12/097` + `rj_12_097`, `RJ12` + ` rj12 `, `RJ012`, `///`, `.hidden`, `A/1` + `A_1`.

**Other**
- Consent: minimal hand-written PDF bytes, 1×1 PNG and JPG from Pillow, zero-byte PDF, corrupt PNG, PDF with JavaScript marker text, executable-like bytes named `.pdf`.
- Fakes: `FakeSTT` (words/confidence/raise), `FakeTTS` (sine proportional to text length; too-long, empty, silent modes), `FakeStorage` (ENOSPC, unavailable, atomic-write recorder), `FakeClock`, pass-through lip-sync fake, StubBroker with crash/timeout injectors.
- `PII_CANARIES`: single list of fixture names/IDs used by log, DB, metadata and file-name assertions.
- Keys and passwords: random per session from `secrets`; never real values.

---

## Traceability: AC → case IDs

| AC | Positive | Negative | Edge |
|----|----------|----------|------|
| AC1 | P1–P4 | N1–N8 | E1–E10 |
| AC2 | P1–P6 | N1–N6 | E1–E11 |
| AC3 | P1–P7 | N1–N8 | E1–E12 |
| AC4 | P1–P4 | N1–N2 | E1–E5 |
| AC5 | P1–P4 | N1–N5 | E1–E7 |
| AC6 | P1–P4 | N1–N6 | E1–E7 |
| AC7 | P1–P4 | N1–N8 | E1–E6 |
| AC8 | P1–P5 | N1–N2 | E1–E5 |
| AC9 | P1–P9 | N1–N4 | E1–E10 |
| AC10 | P1–P4 | N1–N3 | E1–E8 |
| AC11 | P1–P7 | N1–N5 | E1–E11 |
| AC12 | P1–P7 | N1–N5 | E1–E11 |
| AC13 | P1–P6 | N1–N5 | E1–E9 |
| AC14 | P1–P6 | N1–N3 | E1–E9 |
| AC15 | P1–P3 | N1–N4 | E1–E7 |
| AC16 | P1–P6 | N1–N5 | E1–E7 |
| AC17 | P1–P7 | N1–N7 | E1–E11 |
| AC18 | P1–P2 | N1–N3 | E1–E6 |
| AC19 | P1–P4 | N1 | E1–E6 |
| E2E | P1 | — | E1–E2 |

Required-edge checklist: unicode + Devanagari (AC3-P2/P4/P7, E2, E12; AC11-E2/E3; AC17-P1) · 40/41 (AC3-N4, E1, E2) · slashes (AC3-E6, AC11-P5, AC14-E5) · BOM (AC2-E1) · empty middle rows (AC2-E4) · 0/1/1k/100k rows (AC4) · zero-length/corrupt/no-audio video (AC1-E2/E3/E4/N5) · disk full (AC1-E8, AC12-N3) · timeout (AC12-P3, E1) · crash + single retry (AC12-P2, N1) · redelivery idempotency (AC12-P6, E2) · 2 workers (AC12-E4/E5) · path traversal (AC11-N1) · PII never in logs (AC17-P4, N4, E10).

---

## Open issues (not settled by Addendum A)
- **OI-1 (AC3)** Primary code when a row has several faults. Proposed order: empty name, empty ID, bad characters, too long, duplicate.
- **OI-2 (codes)** Still unnamed: consent file rejected (wrong type), TTS empty/silent output, output format/duration mismatch, folder-name rejection. Tests assert on a code constant imported from one module; CEO to fix names.
- **OI-3 (AC1)** Is a 1-frame video valid? Is a template without audio rejected (assumed yes)? Minimum duration not defined.
- **OI-4 (AC11)** Empty/whitespace custom folder name: reject or fall back to default?
- **OI-5 (AC15)** ZIP with no completed rows: 409 or empty ZIP?
- **OI-6 (AC14/AC17)** Does the rows API return decrypted names, masked, or never? Name search assumed out of scope (ID only).
- **OI-7 (AC14)** Formulas for ETA and success rate; stats time zone (assumed UTC); previews excluded from stats (assumed).
- **OI-8 (AC12)** Timeout length, backoff, which OS errors count as "storage error"; "exactly once" = 2 attempts total (assumed). AC12 `INTERNAL_ERROR` "unless it is a crash": tests treat an injected crash exception type as retryable.
- **OI-9 (AC2)** Multi-sheet workbooks (first sheet assumed) and non-comma CSV delimiters (expected outcome not defined).
- **OI-10 (AC9)** Loudness measurement standard (assumed ITU-R BS.1770 / ebur128). "Audio format" in AC8 assumed = codec + sample rate + channel layout.
- **OI-11 (AC13)** Idempotency key for "same batch submitted twice" (client key vs content hash).
- **OI-12 (AC17)** Retention age counts from batch creation or completion? (Tests assume completion.)
- **OI-13 (AC19)** AC19 is a repository gate, not behaviour; pytest/coverage results are verified in T15 rather than by a self-referential test.

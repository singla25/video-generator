# REQ-001 — Personalized Video Batch Generator (MVP)

**Owner:** Admin · **Status:** Draft for CEO discovery · **Date:** 2026-10-18
**Inputs provided by Admin:** `samples/template_video.mp4`, `samples/source_list.xlsx`, design reference (Dribbble — TrustVest FinTech Dashboard Animation)

> CEO: this is the Admin's brief. Treat it as the starting point for Phase 1. Restate it, cross-question with MCQs (see §11 for the open questions I already know about), then plan. Do not start work without approval.

---

## 1. Goal (one sentence)

A user uploads **one template video** and **one Excel list**. The system produces **one personalized video per Excel row**. In each video, the **voter's name spoken at the start** is replaced with the name from the Excel row, in the speaker's own voice, with **lip movement synchronized**. Each video is saved with the **person's ID as its file name**. The result must look and sound like the original.

### Confirmed by Admin (2026-10-18)
- **Two names are in the video:**
  - **Voter name (changes):** the speaker opens with *"**Krishan** ji, Ram Ram, main Amit Dighal …"*. Only the word **"Krishan"** is replaced by the Excel `Name`.
  - **Speaker / admin name (never changes):** *"Amit Dighal"*, the candidate himself, who is the person speaking in the video.
- "ji", "Ram Ram" and every other word stay exactly as in the original.
- The **ID is not spoken and not shown**. It is only used to name the output file.
- The name is only **spoken**, not written on screen. Text replacement (R5) is therefore **not needed for MVP**.

## 2. What the sample inputs look like

### Template video (`samples/template_video.mp4`)
| Property | Value |
|---|---|
| Duration | 26.2 s |
| Resolution | 1080 × 1300 (portrait, non-standard) |
| Frame rate | 60 fps |
| Video codec | H.264 |
| Audio | AAC, 44.1 kHz, stereo |
| Language | Hindi |
| Content | Election campaign video: a speaker talks to camera, framed by a campaign graphic (party/candidate banner on top, ballot and EVM graphic, bottom ticker). The last ~4 s are a full-screen static poster. |

### Excel list (`samples/source_list.xlsx`)
- One sheet, 2 columns, 10 data rows.
- Headers: `Name`, `VID ` (**note the trailing space**). The values look like **Voter ID (EPIC) numbers**.
- Value patterns seen:
  - Full names in title case: `Rahul Sharma`, `Gurpreet Singh`
  - Names in ALL CAPS: `JAVED HUSSAIN`, `SANTOSH DEVI`
  - Single-word names: `MUMTAAJ`, `SITA`, `PAPPU`
  - IDs in two formats: `ALC1761949`, and with slashes `RJ/12/097/183866`

---

## 3. Users and the main flow

**User:** campaign operator (logged-in user of the dashboard).

1. **Create batch.** Upload the template video and the Excel file.
2. **Validate.** The system validates both files instantly and shows the row count, invalid rows and duplicates.
3. **Mark the slots (one time per template).** The system *auto-detects* where the name/ID is **spoken** (speech-to-text with word timestamps) and where it is **shown** (on-screen text detection). The user confirms or adjusts on a timeline. See §11, Q1.
4. **Preview.** Generate **1 preview video** from row 1. The user watches it and approves.
5. **Output folder.** The user types a folder name, or accepts the default `YYYY-MM-DD-<rowcount>` (for example `2026-10-18-10`).
6. **Start.** Rows go to the render queue and the dashboard shows live progress.
7. **Review.** Watch any video, download one, all (ZIP) or only failed rows (CSV), and retry failed rows.

---

## 4. Functional requirements

### R1 — Upload and validation
- R1.1 Video: MP4/MOV, H.264/H.265, ≤ 500 MB, ≤ 5 min (limits configurable). Reject other files with a clear message.
- R1.2 Excel: `.xlsx` and `.csv`. Header matching is **case-insensitive and whitespace-trimmed** (`VID ` = `vid` = `VID`).
- R1.3 Column mapping screen: the user picks which column is *Name* and which is *ID*, so other sheets with different headers still work.
- R1.4 Row checks, each shown with a clear reason:
  - empty name
  - empty ID
  - duplicate ID (keep the first, flag the rest)
  - name too long for the text box (configurable, e.g. > 30 chars)
  - unsupported characters
- R1.5 Invalid rows are **not rendered**. They appear in analytics as *Skipped* with the reason.

### R2 — Template analysis
- R2.1 **Audio:** transcribe the template with word-level timestamps and locate the spoken name/ID segment(s).
- R2.2 **Visual:** detect on-screen text regions (OCR with Hindi + English) where the name/ID appears, with frame ranges.
- R2.3 Save the result as a reusable **Template profile**: slots, timings, text box position/size, font, colour and face region. The same template is analysed once and reused for every row and every future batch.
- R2.4 If auto-detection fails or confidence is low, the user marks slots manually on a timeline (start/end time plus a drawn box).

### R3 — Personalized audio (voice)
- R3.1 Generate the new name/ID speech **in the original speaker's voice** (voice cloning from the template audio).
- R3.2 Names written in English letters must be **pronounced correctly in Hindi** (e.g. `Rahul Sharma` is spoken as राहुल शर्मा). Transliterate names before speech synthesis. The user can override the pronunciation per row.
- R3.3 Only the voter's name is synthesized. The ID is never spoken. Names have very different lengths: "Krishan" is ~0.5 s, while "Gurpreet Singh" or "Santosh Devi" are much longer. So the replaced segment must flow naturally into "ji, Ram Ram…" (see R3.5).
- R3.4 Only the name/ID segment is replaced. The rest of the original audio stays untouched. Splice with crossfades of ~20–50 ms so there are no clicks, and match loudness to the original (±1 LU).
- R3.5 If the new name is longer or shorter, adjust timing smoothly: time-stretch within ±15 %, otherwise extend or shorten the pause around it. The background music must not jump.

### R4 — Lip sync (video)
- R4.1 Re-render the **mouth region only for the replaced segment(s)** so lips match the new audio. All other frames stay byte-identical in content (re-encode is fine).
- R4.2 Keep the face identity, skin tone, lighting and 60 fps motion. No visible seam, blur box or flicker at segment boundaries (blend over 3–5 frames).
- R4.3 If lip-sync quality is below threshold (§8), mark the row **Failed: LIPSYNC_LOW_QUALITY** instead of delivering a bad video.

### R5 — On-screen text (NOT in MVP; keep the port so it can be added later)
- R5.0 The sample template has no on-screen name. Build the `TextRenderer` interface only; implement it in a later version if a template needs it.
- R5.1 Replace the name/ID text in the detected region with matching font, size, colour, weight, outline/shadow and position. Hindi (Devanagari) and English must both render correctly.
- R5.2 Long names: auto-shrink the font down to a minimum size, then wrap to 2 lines. If it still doesn't fit, fail with `TEXT_TOO_LONG`.
- R5.3 The text appears in exactly the same frame range as the original.

### R6 — Output
- R6.1 Same resolution, fps, codec family, duration (±50 ms) and audio format as the template.
- R6.2 Folder: user-given name, or the default `YYYY-MM-DD-<number of valid rows>`. If the folder already exists, add a suffix (`-2`, `-3`). **Never overwrite.**
- R6.3 File name: **`<ID>.mp4`**, made filesystem-safe. Slashes, spaces and special characters become `_`, so `ALC1761949` becomes `ALC1761949.mp4` and `RJ/12/097/183866` becomes `RJ_12_097_183866.mp4`. Because the ID is the file name, duplicate IDs must be caught at validation (R1.4).
- R6.4 Each folder also contains `manifest.csv`, with one row per input row: name, ID, status, file name, failure reason, quality scores and render time.

### R7 — Dashboard and analytics
- R7.1 **Batch overview cards:** Total rows · Completed · Processing · Queued (left) · Failed · Skipped (invalid).
- R7.2 Progress ring or bar plus ETA, updated live (WebSocket or polling every 2 s).
- R7.3 **Failure breakdown:** a chart of failure reasons with counts. Clicking a reason shows those rows.
- R7.4 **Rows table:** search and filter by status. Each row has a status chip, a reason, a preview, download and retry.
- R7.5 **History:** all past batches with date, template, totals and success rate.
- R7.6 Charts: videos generated over time, average render time per video, success rate.
- R7.7 Actions: pause or resume a batch, cancel a batch, retry failed rows, download ZIP, export failures as CSV.

### R8 — Failure reasons (fixed list, shown in plain words)
| Code | Shown to user as |
|---|---|
| `INVALID_ROW_EMPTY_NAME` / `_EMPTY_ID` | Name / ID is missing in the sheet |
| `DUPLICATE_ID` | This ID already appears in row N |
| `TEXT_TOO_LONG` | Name is too long to fit on screen |
| `TTS_FAILED` | Couldn't generate the voice for this name |
| `PRONUNCIATION_UNCERTAIN` | Pronunciation needs your check (preview and approve) |
| `LIPSYNC_LOW_QUALITY` | Lip movement didn't match well enough |
| `TEXT_RENDER_FAILED` | Couldn't place the text on the video |
| `RENDER_TIMEOUT` | Took too long; retry |
| `STORAGE_ERROR` | Couldn't save the file |
| `CONSENT_MISSING` | Speaker consent not recorded for this template |

---

## 5. Compliance and safety requirements (mandatory)

This tool changes what a real person appears to say. For election use in India, the Election Commission's October 2025 advisory requires that AI-altered campaign video be **prominently labelled**:
- The label must cover **at least 10 % of the screen at the top**.
- For audio, the disclosure must cover the first 10 % of the duration.
- The metadata must name the entity that created the content.
- Content must not misrepresent anyone's identity or voice **without their consent**.

The system must therefore enforce the following (configurable per campaign, **on by default**):

- C1 **Speaker consent gate.** A template cannot be used until the user uploads or records a consent record from the person in the video (signed form or recorded statement) and ticks a confirmation. It is stored with the template profile. Without it, every row fails with `CONSENT_MISSING`.
- C2 **AI disclosure label** burned into every output: "AI-Generated" / "एआई-जनित", at the top, ≥ 10 % of display area, for the full duration. Plus an audio disclosure option.
- C3 **Metadata.** The MP4 metadata includes the creator entity, generation date and batch ID. Optionally, add an invisible watermark.
- C4 **Audit log.** Who uploaded what, who approved, and when each video was generated. Kept for the period the Admin sets.
- C5 **Voter data protection.** Names and IDs are personal data:
  - store them encrypted at rest
  - access only for logged-in users of that campaign
  - never log them in plain text or send them to third-party services without approval
  - the Admin can delete a batch's data completely
  - samples are git-ignored
- C6 **Content lock.** Only the name/ID slots can change. The system never edits any other words the speaker says.

---

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Throughput | Target ≥ 100 videos/hour on 1 GPU worker for a ~30 s template. Scales by adding workers. |
| Batch size | MVP 1–1,000 rows; design for 100,000+. |
| Latency | Upload validation < 3 s; first preview < 2 min. |
| Reliability | Each row is an independent, idempotent job. A crash mid-render retries safely. No duplicate files. |
| Resources | Stream video; never load the whole file into RAM. Clean temp files on success and on failure. |
| Hardware | Lip sync and voice cloning need a GPU (CUDA). Dev mode must still run end-to-end on CPU with small/fake models. |
| Security | See §5. No secrets in code. Uploads are scanned for type and size. |
| Observability | Structured logs (no personal data), per-stage timings, queue depth metric. |

---

## 7. Architecture direction (CEO to propose options and get approval)

```
Frontend (dashboard) ──HTTP/WebSocket──► API (FastAPI)
                                           │ creates Batch + Row jobs
                                           ▼
                                      Job queue (Redis + RQ/Celery/Dramatiq)
                                           ▼
                          GPU workers — per-row pipeline:
   1 Validate row → 2 Transliterate → 3 TTS (cloned voice) → 4 Audio splice
   → 5 Lip-sync segment → 6 Text overlay → 7 Disclosure label + metadata
   → 8 Encode → 9 Quality checks → 10 Save + manifest
                                           ▼
                        Storage (local disk in dev / S3-compatible in prod)
                        Database (PostgreSQL) — batches, rows, templates, audit
```

Every AI step sits **behind an interface (port)** so models can be swapped without touching other code:
`SpeechToText`, `Transliterator`, `VoiceCloner/TTS`, `LipSyncer`, `TextDetector (OCR)`, `TextRenderer`, `VideoEncoder`, `QualityChecker`.

**Options the CEO should compare (2–3 each, with a recommendation):**
- Speech-to-text with word timestamps: e.g. Whisper / faster-whisper / WhisperX
- Voice cloning (Hindi): e.g. open-source XTTS-v2 or F5-TTS (self-hosted) vs. a commercial API (ElevenLabs etc.). Compare quality, Hindi support, cost per video, data privacy and licence.
- Lip sync: e.g. LatentSync / MuseTalk / Wav2Lip (open source, GPU) vs. a commercial API. Compare quality on 60 fps, speed, licence for commercial use.
- OCR (Hindi + English): e.g. PaddleOCR / EasyOCR
- Transliteration: e.g. IndicXlit / AI4Bharat tools
- Frontend stack: React + TypeScript + Tailwind + a chart library (recommended for this design) vs. Streamlit (faster but cannot match the design)
- Queue: RQ vs Celery vs Dramatiq

**Licence check is mandatory.** Several lip-sync and voice models are non-commercial only. The CEO must confirm the licence for each model and tell the Admin before choosing.

---

## 8. Quality acceptance criteria (tester measures these automatically)

| # | Check | Pass threshold |
|---|---|---|
| Q1 | Spoken name is correct: run speech-to-text on output's first seconds | Target name recognised (fuzzy match ≥ 0.85); "Krishan" no longer present; "Amit Dighal" still present |
| Q2 | Rest of speech unchanged: speech-to-text of everything after the name | Same transcript as template |
| Q3 | Lip-sync quality: SyncNet LSE-C / LSE-D on edited segment | LSE-C ≥ template baseline − 10 %; A/V offset ≤ ±1 frame |
| Q4 | Unchanged parts unchanged: SSIM outside edited regions/time | ≥ 0.98 |
| Q5 | Seam smoothness: frame difference at segment boundaries | No spike above the template's own max |
| Q6 | Audio continuity: loudness and clicks at splice points | ±1 LU; no peak > −1 dBFS |
| Q7 | Format preserved | Same resolution, fps, codecs; duration ±50 ms |
| Q8 | Disclosure label present | Present in 100 % of frames, top, ≥ 10 % area |
| Q9 | Manifest correct | One row per input row; statuses add up to total |

A row that fails Q1–Q6 is marked **Failed** with the matching reason. It is **never** silently delivered.

---

## 9. Test case tree (tester expands this)

```
Feature: Personalized batch generation
├── Upload & validation
│   ├── ✅ valid video + valid 10-row Excel → 10 rows queued
│   ├── ❌ Excel with no Name column → clear error, nothing queued
│   ├── ❌ video is a renamed .txt / corrupt MP4 → rejected with reason
│   └── ⚠️ header "VID " with trailing space · ALL CAPS names · single-word names
│       · IDs with slashes · empty rows in the middle · duplicate IDs
│       · 0 data rows · 1 row · 10,000 rows · .csv instead of .xlsx · extra columns
├── Template analysis
│   ├── ✅ sample template → name slot detected in audio and on screen
│   ├── ❌ template with no speech → asks for manual marking
│   └── ⚠️ name spoken twice · text slot moves on screen · slot at very start/end
├── Voice
│   ├── ✅ "Rahul Sharma" replaces "Krishan" → "Rahul Sharma ji, Ram Ram, main Amit Dighal…", Q1 + Q2 pass
│   ├── ❌ TTS service down → row fails TTS_FAILED, batch continues
│   └── ⚠️ very short name (SITA) · long name (GURPREET SINGH) · name with initials ("R. K. Sharma")
│       · Devanagari input · "Amit Dighal" is never touched · ID is never spoken
├── Lip sync
│   ├── ✅ edited segment passes Q3, Q4, Q5
│   ├── ❌ no face found in segment → LIPSYNC failure with reason
│   └── ⚠️ head turned / hand near mouth in segment · 60 fps preserved
├── Output
│   ├── ✅ default folder name "2026-10-18-10" · custom folder name
│   ├── ✅ files named by ID: ALC1761949.mp4 · RJ/12/097/183866 → RJ_12_097_183866.mp4
│   ├── ❌ folder name with "../" or illegal chars → rejected (path traversal)
│   └── ⚠️ folder already exists → "-2" suffix · disk full → STORAGE_ERROR, no partial files
├── Queue & reliability
│   ├── ✅ 10 rows render in parallel on 2 workers
│   └── ⚠️ worker killed mid-row → retried once, no duplicate file · pause/resume
│       · cancel mid-batch · same batch submitted twice (idempotent)
├── Dashboard
│   ├── ✅ counts update live and always add up to total
│   ├── ❌ API down → dashboard shows error state, not stale numbers
│   └── ⚠️ empty state (no batches) · 1,000-row table performance · mobile width
└── Compliance
    ├── ❌ template without consent record → all rows CONSENT_MISSING
    ├── ✅ every output has the AI label (Q8) and creator metadata
    └── ⚠️ no names/IDs appear in logs · batch deletion removes all personal data
```

All tests use **synthetic fixtures** (generated test video + fake names). The real sample files are for manual end-to-end checks only.

---

## 10. Frontend design brief

**Reference:** Dribbble — *TrustVest FinTech Dashboard Animation* (`https://dribbble.com/shots/27819158-TrustVest-FinTech-Dashboard-Animation`).
The Admin will save screenshots / a screen recording of it to `docs/design/reference/`. **frontend-dev must match that reference** for colours, card style, spacing, typography, chart style and motion. If the reference files are missing, stop and ask the CEO.

Screens:
1. **Overview dashboard.** KPI cards (Total, Completed, Processing, Queued, Failed, Skipped), a live progress ring, a "videos over time" chart, a failure-reason chart, and a recent-batches list.
2. **New batch wizard (4 steps).**
   - Upload: drag-and-drop for video and Excel, with a file preview.
   - Map columns and validate: a table of rows with invalid ones highlighted.
   - Mark slots and preview: a video player with a timeline showing the detected slots and an editable on-screen box, plus the "Generate preview" button.
   - Output folder and start: a default name pre-filled, then a confirm screen.
3. **Batch detail.** Header stats, a live progress bar and ETA, a filterable rows table, an inline video preview, download/retry per row, and Download ZIP / Export failures / Pause / Cancel.
4. **Templates.** Saved template profiles with consent status, slot summary and thumbnail.
5. **History.** All batches with success rate.

UI rules:
- Smooth number counters and chart animations as in the reference, but respect "reduce motion".
- Every screen handles loading, empty and error states.
- Responsive down to tablet width.
- Supports Hindi text display.

---

## 11. Open questions for the CEO to ask the Admin (as MCQs)

1. ~~Where is the name?~~ **Answered:** spoken only, "Krishan" at the start; ID used only as the file name.
2. ~~Who is speaking?~~ **Answered:** the candidate, Amit Dighal. Still needed: how will his **consent record** be captured (signed form / short recorded statement)? Will other candidates' templates be used later?
3. Full name or first name? Should "Rahul Sharma" be spoken in full, or only "Rahul" (more natural before "ji")? Should there be a per-row override column for pronunciation or nickname?
4. ALL-CAPS names (`JAVED HUSSAIN`): speak normally (yes by default). Any titles to drop or keep (e.g. "Smt.", "Dr.")?
5. Voice and lip-sync: **self-hosted open-source** (cheaper per video, needs a GPU server, data stays private) or **commercial API** (faster to build, cost per video, voter data leaves your servers)?
6. Where will it run: your Mac (dev only), a cloud GPU server, or a client's server? Expected batch sizes?
7. How will videos be delivered: download ZIP only, or also send via WhatsApp later? (Out of scope for MVP unless requested.)
8. User accounts: just the Admin for MVP, or multiple operators with roles?
9. How long should voter data and generated videos be kept before auto-delete?

## 12. Out of scope for MVP
WhatsApp/SMS sending, payment, multi-language templates, editing words other than name/ID, mobile app.

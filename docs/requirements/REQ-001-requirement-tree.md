# REQ-001 — Confirmed requirement tree

**Status:** Confirmed by Admin · **Date:** 2026-10-18 · **Source brief:** `REQ-001-personalized-video-batch.md`

## Discovery decisions (Admin answers, 2026-10-18)

| # | Question | Decision |
|---|----------|----------|
| D1 | Voice cloning + lip sync | Self-hosted open-source models; commercial-use licence verified per model |
| D2 | Hardware | Develop on Mac with fake/CPU models; real renders on a rented CUDA cloud GPU |
| D3 | Spoken name form | Full name as written; optional "Spoken name" column overrides per row |
| D4 | Consent capture (C1) | Signed consent form upload (PDF/image) + confirmation tick |
| D5 | Delivery slicing | 3 milestones: M1 product flow on fake models · M2 real AI on GPU + quality gate · M3 dashboard UI |
| D6 | Users | Single admin login; data model carries `campaign_id` for later multi-user |
| D7 | Retention | Configurable auto-delete, default 30 days; audit log kept separately; manual batch delete any time |
| D8 | Titles (Smt., Dr., Shri…) | Kept and spoken as written; change via "Spoken name" column |
| D9 | Allowed name characters | Latin letters, Devanagari, space, `.` `-` `'`; max 40 chars (configurable) |
| D10 | Preview approval | Required per batch before start; recorded in audit log |
| D11 | Automatic retries | 1 automatic retry for crash / timeout / storage errors only; quality failures need manual retry |
| D12 | Audio AI disclosure | M1: visual label + metadata. M2: configurable spoken disclosure. Admin confirms legal need with counsel |
| D13 | Creator entity (C3) | Configurable setting (later per campaign); real value supplied by Admin at configuration |
| D14 | Python version | Pin Python 3.11 via ADR (approved together with the plan) |
| D15 | Frontend | Planned now, scheduled after backend + tests (M3); design reference = TrustVest screenshots in `docs/design/reference/` |
| D16 | Name longer/shorter than slot | Time-stretch ±15 % + absorb in the pause after "ji" first; if still short, the video grows by the difference (max +1.5 s, configurable). Duration rule = template + delta ±50 ms. Beyond max → row fails `NAME_TOO_LONG_TO_SPEAK`. Shorter names pad the pause. |
| D17 | Root project files | `backend-dev` may edit exactly `pyproject.toml`, `uv.lock`, `.python-version`, `docker-compose.yml`, only when its task brief says so; CEO reviews every change |

**Failure codes added to R8:** `INVALID_ROW_NAME_TOO_LONG`, `INVALID_ROW_BAD_CHARACTERS` (validation), `NAME_TOO_LONG_TO_SPEAK` (D16). Row status `CANCELLED` added for cancelled batches.

## Requirement tree

```
Personalized Video Batch Generator
├── Functional
│   ├── R1 Upload & validation                                  [M1]
│   │   ├── R1.1 Video MP4/MOV, H.264/H.265, ≤500 MB, ≤5 min (configurable); real type check, not extension
│   │   ├── R1.2 .xlsx + .csv; headers case-insensitive + trimmed
│   │   ├── R1.3 Column mapping: Name, ID, optional "Spoken name"
│   │   ├── R1.4 Row checks: empty name/ID, duplicate ID (first kept), >40 chars,
│   │   │        chars outside Latin/Devanagari/space . - '
│   │   └── R1.5 Invalid rows → Skipped with reason, never rendered
│   ├── R2 Template analysis
│   │   ├── R2.1 STT with word timestamps → locate the name slot      [port M1 fake, real M2]
│   │   ├── R2.3 Reusable Template profile (slot, timings, face region, consent)  [M1]
│   │   └── R2.4 Manual slot marking when confidence is low      [API M1, timeline UI M3]
│   ├── R3 Voice
│   │   ├── R3.1 Cloned voice of the speaker                    [port M1 fake, real M2]
│   │   ├── R3.2 Transliteration to Hindi; "Spoken name" column overrides it
│   │   ├── R3.3 Full name as written, titles kept; ID never spoken
│   │   ├── R3.4 Splice only the slot; 20–50 ms crossfade; loudness ±1 LU
│   │   └── R3.5 Time-stretch ±15 %, then pause adjustment; music continuous
│   ├── R4 Lip sync: mouth region of the slot only, 3–5 frame blend,
│   │        low quality → LIPSYNC_LOW_QUALITY                  [port M1 fake, real M2]
│   ├── R5 On-screen text: TextRenderer port only (no implementation)
│   ├── R6 Output                                               [M1]
│   │   ├── R6.1 Same resolution / fps / codecs / duration = template + name delta ±50 ms (D16)
│   │   ├── R6.2 Folder: custom or YYYY-MM-DD-<valid rows>; "-2" suffix; never overwrite;
│   │   │        path traversal rejected
│   │   ├── R6.3 <ID>.mp4, unsafe chars → "_"
│   │   └── R6.4 manifest.csv (one line per input row)
│   ├── R7 Dashboard                                            [API M1, UI M3]
│   │   ├── R7.1–7.6 KPI cards, live progress/ETA (polling 2 s), failure chart,
│   │   │            rows table, history, charts
│   │   └── R7.7 Pause / resume / cancel / retry failed / ZIP / failures CSV
│   ├── R8 Fixed failure codes with plain-language messages
│   └── Flow: upload → validate → confirm slot → preview row 1 (approval REQUIRED
│            per batch, audited) → folder → render → review
├── Compliance (on by default, fixed)
│   ├── C1 Consent: signed-form upload (PDF/image) + confirmation tick; else CONSENT_MISSING
│   ├── C2 "AI-Generated / एआई-जनित" label, top ≥10 %, every frame [M1];
│   │      configurable spoken disclosure [M2]
│   ├── C3 MP4 metadata: creator entity (setting), date, batch ID
│   ├── C4 Audit log (uploads, approvals, generations)
│   ├── C5 Names/IDs encrypted at rest; never in logs; single admin login;
│   │      auto-delete after N days (default 30); delete a batch on demand
│   └── C6 Content lock: only the name slot can change
├── Non-functional
│   ├── Rendering never in a web request; queue + workers; idempotent row jobs
│   ├── Retries: 1 automatic retry for crash / timeout / storage errors only;
│   │            quality failures → manual retry
│   ├── Streaming I/O; temp files cleaned on success and failure
│   ├── Upload validation < 3 s; first preview < 2 min (GPU); ≥ 100 videos/h per GPU (M2)
│   ├── 1–1,000 rows now, designed for 100k+ (campaign_id in the data model)
│   ├── Full pipeline runs on Mac CPU with fake models (M1); CUDA cloud GPU for real renders
│   ├── Structured logs without personal data; per-stage timings; queue-depth metric
│   └── Coverage ≥ 85 % on new code, 100 % on pipeline logic; synthetic test data only
├── Constraints
│   ├── Python 3.11 (ADR), self-hosted models only, commercial-use licences verified
│   ├── Voter data never sent to third parties
│   └── Frontend matches the TrustVest reference; built after backend + tests (M3)
├── Out of scope
│   ├── WhatsApp/SMS, payments, mobile app, multi-language templates
│   ├── Editing any word other than the voter name
│   ├── R2.2 OCR detection + R5 text replacement (ports only)
│   └── Multi-user roles (data model ready, not built)
└── Open questions
    └── (none)
```

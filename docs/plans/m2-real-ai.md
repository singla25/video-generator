# Plan — M2: Real AI models + quality gate (DRAFT)

**Status:** Draft by the CEO under delegated authority (2026-10-19). **Implementation is blocked on a GPU**, which costs money and so needs the Admin. Starts after M1 gate 3.
**Inputs:** REQ-001 R2–R4, §8 (Q1–Q9), D1, D2, D12 · ADR-010 (provisional model stack) · M1 ports (`backend/vidgen/ports`)

## Goal
Replace the M1 fakes with licence-checked, self-hosted models:
- STT with word timestamps
- transliteration
- Hindi voice cloning
- lip sync
- vocal/music separation

Add the automatic quality gate Q1–Q6. Everything runs on one GPU worker, and the full suite still runs on CPU with fakes.

## Acceptance criteria (draft)
1. Every model/sub-model has a licence line (code + weights + training-data notes) in `docs/decisions/ADR-010` that is commercial-use compatible. Any NC component is replaced.
2. Template analysis finds "Krishan" in the sample with word timestamps (Devanagari or Roman match via transliteration). Low confidence → manual (unchanged API).
3. The voice is cloned from the template speaker (reference clip taken from the template, consent required). Names are transliterated, and the per-row Spoken name override works.
4. Music bed continuity (risk R1): vocals separated, name replaced in the vocal stem only, then remixed; no jump in the music (Q6).
5. The lip-synced slot keeps 60 fps output (25 fps model path resampled), passes Q3 (LSE-C ≥ template − 10 %, offset ≤ ±1 frame), Q4 (SSIM ≥ 0.98 outside the slot) and Q5 (no seam spike).
6. Q1/Q2: STT on the output finds the new name (fuzzy ≥ 0.85), "Krishan" is gone, "Amit Dighal" is present, and the rest of the transcript is unchanged.
7. A failing row gets the right code (`TTS_FAILED`, `LIPSYNC_LOW_QUALITY`, `OUTPUT_CHECK_FAILED`…) and is never delivered.
8. Throughput measured on the chosen GPU (target ≥ 100 videos/h for a 30 s template). The report states the actual number.
9. Optional configurable spoken AI disclosure (D12), off by default until the Admin confirms the legal need.
10. GPU worker image (Linux, CUDA) with pinned model versions + checksums; models are downloaded once, never at request time.

## Tasks (draft)
| ID | Task | Agent | Depends on | Model |
|----|------|-------|------------|-------|
| G1 | Full licence audit of every model + bundled sub-model (MuseTalk deps, Demucs weights, Chatterbox weights) | CEO (+ docs) | — | — |
| G2 | **GPU quality spike** on synthetic + Admin-approved sample: voice, lip sync, separation; measure Q1–Q6 and speed | backend-dev | **Admin: GPU + budget** | sonnet |
| G3 | RED: adapter contract tests (CPU, mocked models) + quality-check tests on synthetic media | tester | G1 | sonnet |
| G4 | GREEN: adapters (faster-whisper, IndicXlit, Chatterbox, MuseTalk, Demucs) behind the ports; `ai_backend=real` | backend-dev | G3 | sonnet |
| G5 | RED/GREEN: QualityChecker Q1–Q6 | tester → backend-dev | G4 | sonnet |
| G6 | GPU worker image + model download/checksum script | backend-dev | G4 | sonnet |
| G7 | Verify on GPU: E2E on the sample (Admin-run), throughput report | tester + Admin | G5, G6 | sonnet |

## Risks
| # | Risk | Mitigation |
|---|------|------------|
| R1 | 25 fps lip-sync models vs a 60 fps template | Resample the slot segment; Q3/Q5 decide; fallback LatentSync (legal review) |
| R2 | Hindi voice quality of Chatterbox on this speaker | G2 spike; fallback CosyVoice2 (verify Hindi) |
| R3 | A sub-model licence turns out NC | G1 before any code; swap components |
| R4 | GPU cost | Admin decides provider and budget; batch-oriented spot instances |
| R5 | Transliteration accuracy (~59 % top-1 on named entities) | Spoken-name override + mandatory preview; PRONUNCIATION_UNCERTAIN flag on low confidence |

## Carried over from M1
- **Per-template pause (DD-7):** measure the pause after the name from word timestamps at template analysis and store it on the template (migration **0002**: additive, created by backend-dev, run by the Admin). M1 uses the `pause_s` config fallback.
- Speech stretch: try `rubberband` on the GPU image (M1 build only has `atempo`).

## Waiting for Admin
- GPU provider and budget (paid). No GPU work starts without it.
- Use of the real `samples/` files on the GPU box (voter data stays on our own server, never with a third party).

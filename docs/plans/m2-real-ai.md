# Plan — M2: Real AI models + quality gate (Mac-first)

**Status:** Approved by the Admin on 2026-10-28 (DD-30). Supersedes the 2026-10-19 draft, which was blocked on a paid GPU. **Implemented** as the local real-AI pilot (`VIDGEN_AI_MODE=local`), merged in PR #5; pilot only until the production licence gate G8 is closed (DD-31, ADR-012). Cloud GPU rendering is planned separately in `docs/plans/docker-and-cloud-setup.md` (ADR-013).
**Note (2026-11-16):** the 16–18 GB below is the 2026-10-28 spike figure. The full app later measured a worker peak of 20–21 GB on the same 24 GB Mac (README, System requirements).
**Inputs:** REQ-001 R2–R4, §8 (Q1–Q9), D1, D2, D12 · ADR-010 (provisional model stack) · `backend/spikes/m2_mac/RESULTS.md` (Mac spike) · M1 ports (`backend/vidgen/ports/interfaces.py`)

## What changed from the draft
The Mac spike (M4 Pro, 24 GB, MPS) ran the whole stack end to end on the real sample: about 160 s per video, 16–18 GB peak, so **one MuseTalk job at a time**. M2 is therefore built and verified on the Admin's Mac. A rented GPU is only needed for production volumes (100 videos ≈ 4.5 h as measured, ≈ 1.5 h with the obvious optimisations; 1,000 ≈ 14–44 h) and is deferred (W-1 stays open, no longer blocking). The old task G2 (GPU spike) is **done** by the Mac spike.

## Goal
Replace the M1 fakes with licence-checked, self-hosted models behind the existing ports:
- STT with word timestamps (faster-whisper, CPU)
- transliteration (see D-M2-2)
- Hindi voice cloning (Chatterbox-Multilingual, MPS)
- lip sync (MuseTalk, MPS + CPU landmarks)
- vocal/music separation (Demucs, MPS)

Add the automatic quality gate Q1–Q6. The full test suite still runs on CPU with fakes and mocked models; real-model tests are `slow`/`real_ai`-marked and opt-in.

## Acceptance criteria
1. Every model and bundled sub-model has a licence line (code + weights) in ADR-010, commercial-use compatible. Any non-commercial component is replaced. Open from the spike: `face-alignment` S3FD/FAN weights and `face-parse-bisent` weights.
2. Template analysis finds the name word ("Krishan") with word timestamps. Low confidence → manual (API unchanged).
3. Voice is cloned from the template speaker (reference clip from the template's vocal stem, consent required). Names are transliterated; the per-row "Spoken name" override works and the preview step stays mandatory.
4. Music continuity (R1): name replaced in the vocal stem only, then remixed with the accompaniment; no jump (Q6).
5. The lip-synced slot keeps 60 fps output (25 fps model path resampled) and passes Q3 (LSE-C ≥ template − 10 %, offset ≤ ±1 frame), Q4 (SSIM ≥ 0.98 outside the slot) and Q5 (no seam spike).
6. Q1/Q2: STT on the output finds the new name (fuzzy ≥ 0.85), the old name is gone, the rest of the transcript is unchanged.
7. A failing row gets the right code (`TTS_FAILED`, `LIPSYNC_LOW_QUALITY`, `OUTPUT_CHECK_FAILED`…) and is never delivered.
8. Throughput is measured on the Mac and reported as videos/hour (target for the Mac: ≤ 60 s per video after landmark caching; the 100/h target applies only to a future GPU).
9. Optional configurable spoken AI disclosure (D12), off by default until the Admin confirms the legal need.
10. Model versions and checksums are pinned; models are downloaded once, never at request time. The Mac setup is a documented, reproducible script (the spike's patches to MuseTalk become a pinned patch file or a fork).

## Decisions needed inside this plan (defaults chosen; Admin can overrule)
- **D-M2-1 Separation port.** `interfaces.py` has no port for Demucs. Add `VocalSeparator` (`separate(audio, out_dir) -> (vocals, accompaniment)`) with a fake. Default: yes, additive, no existing contract changes.
- **D-M2-2 Transliteration.** IndicXlit cannot be installed on Python 3.11 (fairseq). The spike's replacement, Qwen3-4B-Instruct-2507 (Apache-2.0), is right on only ~55 % of names. Default: keep the `Transliterator` port, implement it with Qwen3-4B (+ a common-names dictionary checked first), use it only to **pre-fill** the Spoken name, and flag low-confidence rows `PRONUNCIATION_UNCERTAIN`. IndicXlit in its own Python 3.10 env stays a later option.
- **D-M2-3 Where models run.** In-process in the worker, models loaded once and kept warm, one render at a time (memory). No separate model server in M2.
- **D-M2-4 Label band.** The spike band measured ~9 % of frame height; spec is ≥ 10 %. Fix in M2 with a test.

## Tasks
| ID | Task | Agent | Depends on | Model | Status |
|----|------|-------|------------|-------|--------|
| G1 | Full licence audit of every model + bundled sub-model; update ADR-010 | CEO | — | — | ✅ Done 2026-10-28: 3 components unresolved (Demucs weights, face-parse-bisent, S3FD/FAN), see ADR-010 and W-6 |
| G2 | Quality spike | — | — | — | ✅ Done by the Mac spike (human review of the 3 videos still open, W-5) |
| G3 | RED: adapter contract tests (CPU, mocked models), `VocalSeparator` port contract, label ≥ 10 % test; test tree `docs/test-tree/m2-real-ai.md` | tester | — | sonnet | Started 2026-10-28 |
| G4 | GREEN: adapters (faster-whisper, Qwen3 transliterator, Chatterbox, MuseTalk, Demucs) behind the ports; `ai_backend=real` setting | backend-dev | G3, G1 | sonnet | Planned |
| G5 | RED/GREEN: QualityChecker Q1–Q6 | tester → backend-dev | G4 | sonnet | Planned |
| G6 | Mac model setup + pin/checksum script; landmark caching per template slot | backend-dev | G4 | sonnet | Planned |
| G7 | Verify on the Mac: E2E on the sample (Admin-run), throughput report | tester + Admin | G5, G6 | sonnet | Planned |
| G8 | **Production gate (DD-31):** replace or clear the unclear weights (Demucs htdemucs, face-parse-bisent, S3FD/FAN). Evaluate MediaPipe-based mask/landmarks and a separation alternative (or none); update ADR-010 | backend-dev + CEO | G4 | sonnet | Planned; must finish before any production run |

Until G8 is done, M2 output is **pilot-only**: runs on the Admin's Mac, results stay local, nothing is delivered to third parties (DD-31).

G1 (docs only, CEO) and G3 (`tests/`, `docs/test-tree/` only) touch disjoint folders and run in parallel on one branch with `git commit --only` (DD-5).

## Risks
| # | Risk | Mitigation |
|---|------|------------|
| R1 | 25 fps lip-sync vs a 60 fps template | Resample the slot segment; Q3/Q5 decide; fallback LatentSync (legal review) |
| R2 | Hindi voice quality of Chatterbox on this speaker | Admin reviews the 3 spike videos (W-5); fallback CosyVoice2 (verify Hindi) |
| R3 | A sub-model licence turns out non-commercial | G1 before G4; swap components |
| R4 | 16–18 GB per MuseTalk job on a 24 GB Mac | One render at a time; worker concurrency 1; document that nothing heavy runs alongside |
| R5 | Transliteration accuracy (~55 %) | Spoken-name override + mandatory preview; `PRONUNCIATION_UNCERTAIN` |
| R6 | Mac throughput too low for big batches | Landmark caching (~50 s/video estimate); rent a GPU later (W-1) |

## Carried over from M1
- **Per-template pause (DD-7):** measure the pause after the name from word timestamps at template analysis and store it on the template (migration **0002**: additive, created by backend-dev, run by the Admin). M1 uses the `pause_s` config fallback.
- Speech stretch: the M1 build only has `atempo`; try `rubberband` on the Mac.

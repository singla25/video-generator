# M2-local: real AI on this Mac (Metal/MPS)

Admin approved running the real AI locally on the Mac GPU (2026-10-28). Dev/low-volume mode; production volume still needs a rented GPU (W-1).

## Goal / acceptance criteria
1. Setting `AI_MODE=local` swaps the fake adapters for real ones; `AI_MODE=fake` (default) is unchanged and CI stays green without torch.
2. Heavy libraries are an optional extra (`local-ai`), imported lazily; the base install and CI never need them.
3. Real adapters implement the existing ports: SpeechToText (faster-whisper, CPU), Transliterator (Qwen3-4B-Instruct-2507, pre-fill only), VoiceCloner (Chatterbox-Multilingual, MPS), LipSyncer (MuseTalk v1.5, patched), plus Demucs vocal split. Model weights live outside git (`work/`-style dir from settings).
4. Name slot is detected automatically from the transcript (Krishan) with the manual slot as fallback.
5. The spoken-name field is pre-filled by the LLM and a human confirms it in the preview step (never auto-approved).
6. Preview and final videos keep the AI label (>=10 % of frame height; spike measured ~9 %, must be fixed), consent gate and encryption untouched.
7. One render at a time (16-18 GB peak); worker concurrency 1 in local mode; failure of one row never stops the batch.
8. Voter data never leaves the machine: no network calls at run time (weights are pre-downloaded; adapters fail if offline fetch is attempted).
9. UI says clearly which mode is active ("Fake AI: beep stands in" vs "Local AI").

## Test tree (tester expands)
- Mode switch: fake default / local selected / unknown value -> clear error.
- Each adapter: contract test with stubbed model (positive), missing weights (negative -> custom error), empty audio, 1-char name, Hindi unicode, timeout (edge).
- Name slot detection: found / not found -> manual fallback / two hits.
- Label: height >= 10 % on 1080x1300 and 1080x1920.
- Batch: row failure isolated; memory guard rejects a second concurrent render.
- Real-model smoke tests are marked `@pytest.mark.local_ai` and skipped by default and in CI.

## Tasks
| ID | Task | Agent | Why | Depends | Model | Done when |
|----|------|-------|-----|---------|-------|-----------|
| L0 | Licence check of every weight/library (G1) | CEO | Hard limit: no non-commercial licences | - | - | table in docs/decisions/ADR-012 |
| L1 | Red tests + test tree | tester | TDD | L0 | sonnet | tests fail for the right reason |
| L2 | Settings, optional extra, lazy loading, adapter factory | backend-dev | Backend domain | L1 | sonnet | factory tests green |
| L3 | Whisper, Qwen, Chatterbox, Demucs adapters | backend-dev | Port the spike code | L2 | sonnet | contract tests green |
| L4 | MuseTalk adapter + label height fix | backend-dev | Hardest part | L3 | sonnet (opus only after 2 fails) | tests green |
| L5 | Mode banner, spoken-name preview, Next hint | frontend-dev | UI domain | L1 | sonnet | UI tests green |
| L6 | Verify + real smoke run of 2 videos | tester | Independent check | L3-L5 | sonnet | report |

## Risks
- Weights with non-commercial licence -> excluded or swapped (L0).
- 16-18 GB RAM peak -> concurrency 1, memory guard.
- Spike patch to MuseTalk is local -> vendored as a patch file, applied by a setup script.
- Name pre-fill only ~45 % exact -> human confirmation is mandatory.

## Dependency changes (flagged)
New optional extra `local-ai` (torch, faster-whisper, chatterbox-tts, demucs, transformers, face-alignment). Covered by delegated authority as a technical choice, only if L0 passes.

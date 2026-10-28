# Spike — M2 model stack on the Admin's Mac (feasibility)

**Status:** Running under delegated authority (2026-10-20). Branch `spike/m2-mac-feasibility`. Throwaway code: nothing from this spike is merged into `main` as product code.
**Question:** Can the ADR-010 stack run locally on Apple Silicon (M4 Pro, 24 GB, torch 2.14.1 + MPS), so that M2 development and testing can start before a paid GPU (W-1)? How slow is it?

## Rules
- Separate venv `.venv-m2/` (ignored by git). The project's `uv.lock` / `pyproject.toml` stay unchanged, so this is not a project dependency change.
- **Synthetic media only.** Hindi speech comes from macOS `say -v Lekha`. Faces come from a model repo's own demo assets. No `samples/` files (W-2), and no voter data.
- Model weights are downloaded once, from official sources. Nothing is uploaded anywhere.
- Licence check before each install: commercial-use compatible (code + weights), as in ADR-010. If a component is non-commercial, skip it and note why.
- Timebox: if a component won't install or run after 2 attempts, mark it ❌ with the error and move on.

## Scope change (Admin, 2026-10-20)
After the synthetic checks, also run the **real sample, on this Mac only**: `samples/template_video.mp4` plus 2–3 names from `samples/source_list.xlsx`. The data never leaves this Mac, and all outputs stay git-ignored under `backend/spikes/m2_mac/work/`. The spike produces 2–3 real personalized videos (lip-synced, "Krishan" replaced). RESULTS.md also gives estimates for 100 and 1,000 videos and a recommendation: Mac is enough / rent a GPU / buy a GPU. (W-2 is resolved for local use only; W-2 for a GPU box is still open.)

## Checks (one per component)
| # | Component | Device | Pass = |
|---|-----------|--------|--------|
| S1 | faster-whisper (word timestamps) | CPU (CTranslate2 has no MPS) | finds the synthetic "कृष्ण / Krishan" word with start/end times |
| S2 | IndicXlit (Roman → Devanagari) | CPU | "Amit Dighal" → plausible Devanagari; note install pain (fairseq) |
| S3 | Chatterbox-Multilingual, Hindi, voice cloned from the Lekha clip | MPS | intelligible Hindi name clip; real-time factor recorded |
| S4 | Demucs (vocals / music split) | MPS | separated stems from a Lekha clip mixed with a synthetic tone bed |
| S5 | MuseTalk (lip sync) on its demo face + S3 audio | MPS | output video renders; s per second of video recorded |

## Output
`backend/spikes/m2_mac/RESULTS.md`: a ✅ / ❌ table, timings, peak memory, the licence line per component, and a recommendation (local dev possible? which parts still need a GPU?).

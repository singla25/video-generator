# ADR-012 Licences for the local real-AI stack (L0 / G1)

## Context
M2-local (plan `docs/plans/m2-local-real-ai.md`) runs real models on the Mac. Hard rule: no model whose licence forbids commercial use.

## Check (2026-10-28, from the project pages)
| Component | Licence | Status |
|---|---|---|
| faster-whisper / Whisper | MIT | OK |
| Qwen3-4B-Instruct-2507 | Apache-2.0 | OK |
| Chatterbox-Multilingual | MIT | OK |
| Demucs | MIT | OK |
| MuseTalk v1.5 code and unet | MIT, "any purpose, even commercially" | OK |
| face-alignment (code) | BSD-3-Clause | OK; S3FD/FAN weights not stated |
| S3FD weights (SFD repo, trained on WIDER FACE) | no licence stated | UNVERIFIED |
| face-parse-bisent weights (zllrunning, trained on CelebAMask-HQ) | code MIT, weights no terms; dataset is research-oriented | UNVERIFIED |

## Decision
Build the local adapters now. Treat the two UNVERIFIED weights as **development use on this Mac only**. Before any production or commercial use, replace them or get a written licence; the Admin decides. Setting `AI_MODE=local` logs this warning at startup.

## Consequences
Lip sync stays dev-only until the two weights are cleared or swapped. Everything else is clear for commercial use.

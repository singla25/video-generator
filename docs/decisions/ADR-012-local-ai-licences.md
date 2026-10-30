# ADR-012 Licences for the local real-AI stack (L0 / G1)

## Context
M2-local (plan `docs/plans/m2-local-real-ai.md`) runs real models on the Mac. Hard rule: no model whose licence forbids commercial use.

## Check (2026-10-28, from the project pages)
| Component | Licence | Status |
|---|---|---|
| faster-whisper / Whisper | MIT | OK |
| Qwen3-4B-Instruct-2507 | Apache-2.0 | OK |
| Chatterbox-Multilingual | MIT | OK |
| Demucs (code) / htdemucs weights | code MIT; the weights' licence is stated as unclear by the author | UNVERIFIED for commercial use (see Correction); the app does not use Demucs yet |
| MuseTalk v1.5 code and unet | MIT, "any purpose, even commercially" | OK |
| face-alignment (code) | BSD-3-Clause | OK; S3FD/FAN weights not stated |
| S3FD weights (SFD repo, trained on WIDER FACE) | no licence stated | UNVERIFIED |
| face-parse-bisent weights (zllrunning, trained on CelebAMask-HQ) | code MIT; weights have no terms; CelebAMask-HQ is "non-commercial research purposes only" | NON-COMMERCIAL until cleared (see Correction) |

## Decision
Build the local adapters now. Treat the two UNVERIFIED weights as **development use on this Mac only**. Before any production or commercial use, replace them or get a written licence; the Admin decides. Setting `AI_MODE=local` logs this warning at startup.

## Consequences
Lip sync stays dev-only until the two weights are cleared or swapped. Everything else is clear for commercial use.

## Correction (2026-10-30, from the G1 audit in ADR-010 on the branch feat/m2-mac-first)
- Demucs: the code is MIT, but the author states that the licence of the htdemucs weights is not clear (MUSDB contains research-only data and he cannot grant a licence); the 6-source variant likely carries CC-BY-NC. The first table row meant the code only.
- face-parse-bisent: the weights were trained on CelebAMask-HQ, whose terms say it is for non-commercial research and educational purposes only. Treat the weights as non-commercial.
- S3FD / FAN (face-alignment): no licence is stated for the weights (downloaded from adrianbulat.com); the original S3FD repository states none either.
- Confirmed permissive: faster-whisper (MIT), Qwen3-4B-Instruct-2507 (Apache-2.0), Chatterbox (MIT), MuseTalk code and weights (MIT, "any purpose, even commercially"), sd-vae-ft-mse (MIT), whisper-tiny (Apache-2.0).
- Decision unchanged: pilot use only on the Admin's Mac (DD-31). Production use needs the G8 gate: docs/plans/g8-licence-gate.md.
This is a technical reading of the project pages, not legal advice.

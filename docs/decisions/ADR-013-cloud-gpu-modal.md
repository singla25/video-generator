# ADR-013 Cloud GPU mode on Modal

**Status:** Proposed (2026-11-12). Accepted only after spike P2-S answers Q1 and Q2 and the Admin signs off.
**Plan:** `docs/plans/docker-and-cloud-setup.md`

## Context
Real AI today runs only natively on Apple silicon (`VIDGEN_AI_MODE=local`, ADR-010). Docker cannot use the Apple GPU,
and the measured local worker peak (20–21 GB on a 24 GB M4 Pro) rules out smaller Macs. The Admin decided (2026-11-12)
that Modal is the only cloud render worker; Kaggle is documentation only.

## Decision (proposed)
1. `settings.ai_mode` gains a third value, `"modal"`, wired in `api/container.py` next to `fake` and `local`.
2. One adapter per existing port (`SpeechToText`, `VoiceCloner`, `LipSyncer`) in `infrastructure/modal_ai/`. The ports,
   `render_row` and the retry policy (`max_retries = 1`, coded row failure) stay unchanged.
3. All adapters call **one Modal class** that loads the models once per container and stays warm across calls.
4. The template video and voice sample are uploaded **once per batch** to a Modal Volume, keyed by content hash;
   per row only text / speech audio goes up and the synced clip comes back (`LipSyncer.sync()` receives the whole
   template today, so re-sending it per row is not acceptable).
5. GPU: L4 (24 GB) first, T4 (16 GB) fallback — to be confirmed by P2-S measurements.
6. Privacy: in `modal` mode the dashboard requires an explicit confirmation that names, voices and faces go to Modal
   **before the first template upload**. Consent gate, encryption at rest and PII-free logs are unchanged.
7. Secrets: Modal token ID + secret are read from environment variables only (`MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`),
   written by the installer to `.env` (0600), and passed only to the worker container.
8. Dependency: optional extra `cloud` with a pinned `modal`, added with T4 (separate approval). Until then the spike
   uses `uv run --with modal`.

## Open point that blocks acceptance — licences (ADR-012)
ADR-012 limits two lip-sync weights (S3FD; face-parse-bisent, trained on non-commercial CelebAMask-HQ) to
**"development use on this Mac only"**. Running MuseTalk on Modal moves them off this Mac. Before P2-S runs lip sync
on Modal, the Admin must decide one of: (a) amend ADR-012 to allow dev-only use on the Admin's own Modal account with
demo data, (b) replace the two weights first, or (c) run P2-S for speech-to-text and voice cloning only.

## Consequences
- Machines without Apple silicon (or with < 32 GB) can render real AI.
- Personal data leaves the machine in `modal` mode; mitigated by the confirmation step and demo data while learning.
- Running cost depends on Modal credit; P2-S measures it.
- A third adapter set to maintain; it must behave like `local` on the same inputs (the spike compares outputs).

## Alternatives considered
- One remote call per row (whole `render_row` remotely): fewer round trips, but copies render logic into Modal and
  bypasses the ports. Rejected unless P2-S shows per-step calls are too slow.
- Other clouds / self-hosted CUDA worker: out of scope (Admin decision 2026-11-12; plan m2-real-ai G6).

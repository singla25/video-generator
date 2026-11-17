# ADR-013 Cloud GPU mode on Modal

**Status:** Proposed (2026-11-12). **Admin, 2026-11-17: accepted as "Proposed until the spike runs"**: building with
fakes may proceed and the `cloud` extra (pinned `modal`) is approved; Q1 (GPU type) and Q2 (call size) stay open until
P2-S runs on a workspace with an active payment method.
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
6a. **Data scope (Admin decision C5, 2026-11-16): `modal` mode is for demo and learning data only, never real voter
   data.** Requirement C5 says voter data stays on our servers; Modal is a third-party cloud, so real sheets,
   templates of real people and real voter IDs are never rendered there. The installer's Modal step shows this
   ("demo and learning data only", "never real voter data") and continues only after an explicit "yes"; the
   dashboard confirmation in T4 uses the same wording. Real data stays in `fake` or `local` mode on the Mac.
7. Secrets: Modal token ID + secret are read from environment variables only (`MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`),
   written by the installer to `.env` (0600), and passed only to the worker container.
8. Dependency: optional extra `cloud` with a pinned `modal`, added with T4 (separate approval). Until then the spike
   uses `uv run --with modal`.

## Open point that blocks acceptance — licences (ADR-012)
ADR-012 limits two lip-sync weights (S3FD; face-parse-bisent, trained on non-commercial CelebAMask-HQ) to
**"development use on this Mac only"**. Running MuseTalk on Modal moves them off this Mac. Before P2-S runs lip sync
on Modal, the Admin must decide one of: (a) amend ADR-012 to allow dev-only use on the Admin's own Modal account with
demo data, (b) replace the two weights first, or (c) run P2-S for speech-to-text and voice cloning only.

**Admin decision (2026-11-13): (c).** P2-S runs speech-to-text and voice cloning on Modal only. Lip sync stays on the
Mac until (a) or (b) is decided, so Q1 (GPU type) is answered for those two models only.

## Consequences
- Machines without Apple silicon (or with < 32 GB) can render real AI.
- Personal data leaves the machine in `modal` mode; mitigated by the confirmation step and demo data while learning.
- Running cost depends on Modal credit; P2-S measures it.
- A third adapter set to maintain; it must behave like `local` on the same inputs (the spike compares outputs).

## Alternatives considered
- One remote call per row (whole `render_row` remotely): fewer round trips, but copies render logic into Modal and
  bypasses the ports. Rejected unless P2-S shows per-step calls are too slow.
- Other clouds / self-hosted CUDA worker: out of scope (Admin decision 2026-11-12; plan m2-real-ai G6).
  *Superseded in part by amendment A1 (proposed): any provider can be registered; a self-hosted or rented CUDA
  machine joins as a `remote_worker` once G6 exists.*

## Amendment A1 — pluggable render providers (accepted as "Proposed until the spike runs", 2026-11-17)
**Plan:** `docs/plans/render-providers.md` (approved 2026-11-17). The Admin accepted ADR-013 and this amendment as
"Proposed until the spike runs": building may proceed with fakes; the GPU type (Q1) and call size (Q2) stay open
until P2-S runs. Q3 (rented machines and real data): **no**, enforced by the API and the worker.

**Context.** The Admin asked that rendering not be fixed to three modes (fake, local, modal). Batches should go to
whichever registered provider the Admin picks at preview approval, with honest estimates and a spend limit.

**Decision (proposed).**
1. A **provider registry** (TOML file, standard library, no secrets) replaces the single process-wide choice. Each
   provider declares: name, **kind** (`local` · `remote_function` · `remote_worker`), queue, `ai_mode`,
   **data rule** (`real_allowed` · `demo_only`), **spend cap**, cost rate and required environment variables.
   Without a registry file the app behaves as today (one provider from `ai_mode`).
2. **Setup state** and **estimates** are derived, never declared: ready = required variables present and a live
   heartbeat on the provider's queue; estimates come **only from measured runs** of that provider in this app
   ("not measured yet" otherwise).
3. **One queue per provider.** The worker is unchanged in shape: it serves the queue named by `VIDGEN_QUEUE_NAME`
   and loads the adapters of its `ai_mode`. The batch stores its provider; rows, retries and requeue are routed to
   that queue. Heartbeat and queue depth become per queue.
4. The **chooser** at preview approval lists ready providers that fit the batch's declared data class, side by
   side (time, cost, remaining credit); an option whose estimate exceeds its remaining credit is refused; the
   worker **pauses** the batch before a row would pass the spend cap.
5. **C5:** remote kinds (`remote_function`, `remote_worker`) are `demo_only`. The data class is declared per batch
   at upload, and both the API and the worker check it. Decision 6a stands unchanged.
6. **Modal** becomes one `remote_function` provider (ai_mode `modal`, T4). The Modal design in decisions 1–8
   above is unchanged.
7. **remote_worker** lets any machine (for example a rented GPU server) join by running the same worker with its
   own queue name. It needs the **CUDA worker image (G6)**, shared S3-compatible storage, a private network to
   Redis and PostgreSQL, and the encryption keys on that machine. Until those exist it stays "needs setup".

**Consequences.** One migration (0003: batch provider, batch data class, row cost). New providers need a registry
entry and a worker, not code. Per-queue heartbeats replace the single key. Lip sync on any remote provider stays
blocked until licence option (a) or (b) is decided (ADR-012). Estimates are empty until a provider has measured
runs, by design.

**Alternatives considered.** A fixed enum of modes (rejected: the Admin asked for pluggable). Provider records in
the database (rejected for now: needs an admin UI and secrets handling; the file is reviewable in git).
Estimates from the spike or from design figures (rejected: the Admin asked for measured runs only).

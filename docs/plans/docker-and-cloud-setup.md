# Plan — Docker app stack, cloud GPU mode (Modal) and terminal installer

**Status:** APPROVED with fixes P1–P9 (Admin, 2026-11-12) · Stage 1 = T1–T3; T4 held until spike P2-S · **Date:** 2026-11-12
**Decisions already made by the Admin (2026-11-12):** (1) app stack in Docker, real local AI stays native; (2) Modal is the only cloud worker; (3) installer uses the Python standard library only.

## Review fixes folded in (P1–P9, approved 2026-11-12)
| # | Fix |
|---|-----|
| P1 | Local-mode RAM uses the measured figures (M4 Pro, 24 GB): worker 20–21 GB peak, API 8.7 GB, about 17.8 GB swap; 32 GB recommended. |
| P2 | Media is a **bind mount** of a host folder (the same `storage_root` the native worker uses), so the API in Docker and a native `local` worker see the same files. Named volumes only for PostgreSQL and Redis. In `local` mode the `app` profile starts without the worker container. |
| P3 | `scripts/setup.py` stays stdlib-only and delegates password hashing to the existing `scripts/dev_setup.py` through `uv run` (subprocess). It **never runs migrations by itself**: it asks y/N, like `dev_up.sh`. Containers never migrate on start. |
| P4 | A Modal token is a **pair** (token ID + token secret). Both are read with hidden input, written to `.env` (0600) and checked by running the `modal` package as a subprocess (`uv run --with modal …` until the `cloud` extra exists). Only the worker container gets the `MODAL_*` variables. |
| P5 | The cloud confirmation comes **before the first template upload** in `modal` mode, because template speech-to-text (`services/templates.py`) already sends the template's audio. `settings.ai_mode` gains `"modal"`. |
| P6 | Remote calls: see Q2 answer. `LipSyncer.sync()` gets the whole template today, so the template must be cached remotely, not re-sent per row. |
| P7 | The Linux worker image installs `ffmpeg` and `libfribidi` (Pillow raqm layout); a test checks the Devanagari label renders correctly inside the container. |
| P8 | Root-file grants for this task: backend-dev may write `scripts/setup.py`, `Dockerfile.backend`, `docker-compose.yml`; frontend-dev may write `Dockerfile.frontend`. |
| P9 | The dashboard image is a production build served by a small static web server image that forwards `/api` to the API container (no Vite dev server in Docker). |

## Goal
A user can set the product up from one terminal command and pick where AI rendering runs:

| Mode | Where AI runs | Needs |
|------|---------------|-------|
| `fake` | nowhere (test models) | Docker |
| `local` | natively on the Mac (Apple GPU) | Apple silicon; measured worker peak 20–21 GB + API 8.7 GB on a 24 GB M4 Pro (swaps); 32 GB recommended |
| `modal` | on Modal GPUs | free Modal account + token |

Docker cannot use the Apple GPU, so `local` AI never runs inside a container.

## Acceptance criteria
1. **AC1 App stack in Docker:** `docker compose --profile app up -d` starts PostgreSQL, Redis, API, worker and dashboard from the repository; `/api/health` answers; data survives a restart (named volumes for PostgreSQL/Redis, bind-mounted host folder for media). In `local` mode the worker runs natively against the same media folder. No container runs migrations on start. Existing `scripts/dev_up.sh` still works unchanged.
2. **AC2 Installer:** `python3 scripts/setup.py` (standard library only) checks prerequisites (Docker running, uv, Node, FFmpeg), asks Fake / Local / Modal, writes `.env` with owner-only permissions (0600), creates the admin login by delegating the hashing to `scripts/dev_setup.py` via `uv run`, asks y/N before applying migrations (never applies them unasked), and prints the exact next commands. It never prints or logs secrets and never overwrites an existing `.env` without asking.
3. **AC3 Guided account setup:** for Modal the installer prints the account steps (sign up, create token), opens the links, reads the token ID and token secret with hidden input, and validates them with one harmless call through the `modal` package run as a subprocess. Wrong or missing token gives a clear message and changes nothing.
4. **AC4 Modal mode:** `VIDGEN_AI_MODE=modal` runs speech-to-text, voice cloning and lip sync as Modal functions behind the existing ports. A failed or timed-out remote call fails that row with a coded error and is retried once; the batch continues.
5. **AC5 Privacy:** before the first template upload in `modal` mode (template speech-to-text already sends audio) the dashboard/installer states that names, voices and faces are sent to Modal and requires explicit confirmation. The consent gate, encryption at rest and PII-free logs are unchanged. Secrets are read from environment variables only.
6. **AC6 Docs:** README gets a short "Choose your mode" section, the Docker command, the installer walkthrough and the Modal account steps. Kaggle is documented as a manual place to test models, not a render worker.
7. **AC7 Quality:** ruff, mypy `--strict` and pytest pass; coverage of new code ≥ 85 %; no real Modal call in automated tests (mocked).

## Requirement tree
```
Docker + cloud setup
├── Functional
│   ├── Dockerfiles: backend (API + worker), frontend; compose profile "app"
│   ├── Installer scripts/setup.py (stdlib only), re-runnable, interactive
│   └── Modal adapter set behind existing ports, selected by VIDGEN_AI_MODE
├── Non-functional: no secrets in images or logs · idempotent installer · images multi-arch (arm64 + amd64)
├── Constraints: Docker has no Apple GPU · Modal needs account + internet · free credit is limited
├── Out of scope: other cloud providers · Kaggle integration · CUDA self-hosted worker (plan m2-real-ai G6)
└── Open questions: answered as proposals; spike P2-S confirms them before T4
    ├── Q1 Modal GPU type → proposal: L4 (24 GB) first, T4 (16 GB) as cheaper fallback. The 20 GB measured on the Mac is unified memory and does not map to GPU memory, so P2-S measures it. Prices and free credit are read from Modal when the spike runs (not assumed here).
    └── Q2 Remote call size → proposal: one adapter per existing port (SpeechToText, VoiceCloner, LipSyncer), all served by ONE Modal class that keeps the models warm in one container. Template and voice sample are uploaded once per batch to a Modal Volume keyed by content hash; per row only text / speech audio goes up and the synced clip comes back. render_row and the retry policy (max_retries = 1) stay unchanged. P2-S measures the real bytes per call.
```

## Spike P2-S (approved 2026-11-12)
- Runs on the Admin's Modal account, **demo data only** (neutral `sun.mp4` demo template, made-up names).
- Throwaway code in `backend/spikes/p2_modal/`; `modal` via `uv run --with modal` — **no `cloud` extra in pyproject.toml yet**.
- Measures, for L4 and T4: peak GPU memory, cold start, time per row, bytes up/down per call, credit used.
- Credit cap: set by the Admin before the spike starts; the spike stops when it is reached.
- Scope (Admin, 2026-11-13, licence option (c)): speech-to-text and voice cloning only; no lip sync on Modal (R5).

## Test tree outline
See `docs/test-tree/docker-and-cloud-setup.md` (tester writes it first).
```
Installer
├── Positive: fake / local / modal path writes a valid .env (0600), no secret printed · hashing delegated to dev_setup.py
├── Negative: Docker not running · missing tool · bad token pair · existing .env declined · no terminal · migrations declined → not applied
└── Edge: re-run is idempotent · Ctrl-C leaves no half-written .env · unicode in paths · token with spaces · stdlib-only imports
Modal adapters
├── Positive: remote STT/TTS/lipsync mocked return expected results
├── Negative: auth error · timeout · remote crash → coded row failure, one retry, batch continues
└── Edge: large video streamed not loaded · concurrent rows · cloud confirmation missing → refuse
Docker stack
├── Positive: health endpoint, restart keeps data · Devanagari label correct in the Linux image
└── Edge: port in use · arm64 and amd64 build · local mode: API container + native worker share the media folder
```

## Tasks (phased)
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| T1 | Test tree + failing tests for installer and Modal adapter contracts | tester | Owns tests/test trees | Plan approved | sonnet | yes `feat/tester/cloud-setup` | AC2–AC5 covered pos/neg/edge |
| T2 | `scripts/setup.py` installer | backend-dev | Python scripts, `.env` handling | T1 | sonnet | yes `feat/backend/installer` | T1 installer tests green |
| T3 | Dockerfiles + compose profile `app` | backend-dev (+ frontend-dev for dashboard image) | Owns backend/ and frontend/ builds | Approval to add root files (rule §1) | sonnet | no | AC1 |
| T4 | Modal adapters + settings + cloud confirmation | backend-dev | Adapters behind ports | T1, spike P2-S | sonnet | yes | AC4, AC5 |
| T5 | README + docs | CEO | Owns docs/ | T2–T4 | haiku | no | AC6 |
| T6 | Verify, coverage report | tester | Verify step of TDD | T2–T4 | sonnet | no | AC7 |
| P2-S | Spike: run the three models on a Modal GPU, measure memory/time/credit use | Admin account + backend-dev | Needs the Admin's Modal account | — | sonnet | no | Q1, Q2 answered |

## Order (TDD)
tester (red) → developer (green + refactor) → tester (verify) → CEO review → Admin approves merge.

## Risks
| # | Risk | Mitigation |
|---|------|-----------|
| R1 | Free Modal credit runs out quickly on GPU | Show estimated cost in the installer; spike measures real use; fall back to `local` |
| R2 | Personal data leaves the machine in `modal` mode | AC5 confirmation; demo data recommended while learning; documented in README |
| R3 | Models used locally (MPS) may not fit or behave the same on CUDA | Spike P2-S before T4; reuse licence findings in ADR-012 |
| R5 | ADR-012 limits two lip-sync weights to "development use on this Mac only"; Modal is off this Mac | Admin decides before P2-S runs lip sync on Modal (see ADR-013 open point) |
| R4 | Root files (Dockerfile, compose changes) are outside any agent's folder | Admin grants it per task (as D17 did earlier) |

## Migrations / dependencies (need separate approval)
- **Migrations:** none expected.
- **Dependencies:** `modal` for the spike only, via `uv run --with modal`. The optional extra `cloud` is added later with T4, pinned to the version the spike tested (separate approval). The installer itself adds none.
- **ADR:** ADR-013 "Cloud GPU mode on Modal" drafted as Proposed; accepted after P2-S.

## Admin approval
- [x] Plan approved, with fixes P1–P9 (2026-11-12)
- [x] Task assignment approved, sonnet as in the plan (2026-11-12)
- [x] Dependency `modal`: spike only (2026-11-12); `cloud` extra not yet
- [x] Root-file grants (P8) approved (2026-11-12)
- [ ] Spike credit cap set
- [ ] ADR-013 accepted (after P2-S)
- [ ] Merge approved

# Plan — Docker app stack, cloud GPU mode (Modal) and terminal installer

**Status:** DRAFT, waiting for Admin approval · **Date:** 2026-11-12
**Decisions already made by the Admin (2026-11-12):** (1) app stack in Docker, real local AI stays native; (2) Modal is the only cloud worker; (3) installer uses the Python standard library only.

## Goal
A user can set the product up from one terminal command and pick where AI rendering runs:

| Mode | Where AI runs | Needs |
|------|---------------|-------|
| `fake` | nowhere (test models) | Docker |
| `local` | natively on the Mac (Apple GPU) | Apple silicon, 16–18 GB peak RAM |
| `modal` | on Modal GPUs | free Modal account + token |

Docker cannot use the Apple GPU, so `local` AI never runs inside a container.

## Acceptance criteria
1. **AC1 App stack in Docker:** `docker compose --profile app up -d` starts PostgreSQL, Redis, API, worker and dashboard from the repository; `/api/health` answers; data survives a restart (volumes). Existing `scripts/dev_up.sh` still works unchanged.
2. **AC2 Installer:** `python3 scripts/setup.py` (standard library only) checks prerequisites (Docker running, uv, Node, FFmpeg), asks Fake / Local / Modal, writes `.env` with owner-only permissions (0600), creates the admin login, and prints the exact next commands. It never prints or logs secrets and never overwrites an existing `.env` without asking.
3. **AC3 Guided account setup:** for Modal the installer prints the account steps (sign up, create token), opens the links, reads the token with hidden input, and validates it with one harmless call. Wrong or missing token gives a clear message and changes nothing.
4. **AC4 Modal mode:** `VIDGEN_AI_MODE=modal` runs speech-to-text, voice cloning and lip sync as Modal functions behind the existing ports. A failed or timed-out remote call fails that row with a coded error and is retried once; the batch continues.
5. **AC5 Privacy:** before the first cloud render the dashboard/installer states that names, voices and faces are sent to Modal and requires explicit confirmation. The consent gate, encryption at rest and PII-free logs are unchanged. Secrets are read from environment variables only.
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
└── Open questions: (must be empty before approval)
    ├── Q1 Which Modal GPU type for the free credit? (proposal: smallest GPU that fits the models; measured in the spike P2-S)
    └── Q2 Remote function granularity: one call per row (proposal) or per step?
```

## Test tree outline
See `docs/test-tree/docker-and-cloud-setup.md` (tester writes it first).
```
Installer
├── Positive: fake / local / modal path writes a valid .env (0600), no secret printed
├── Negative: Docker not running · missing tool · bad token · existing .env declined · no terminal
└── Edge: re-run is idempotent · Ctrl-C leaves no half-written .env · unicode in paths · token with spaces
Modal adapters
├── Positive: remote STT/TTS/lipsync mocked return expected results
├── Negative: auth error · timeout · remote crash → coded row failure, one retry, batch continues
└── Edge: large video streamed not loaded · concurrent rows · cloud confirmation missing → refuse
Docker stack
├── Positive: health endpoint, restart keeps data
└── Edge: port in use · arm64 and amd64 build
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
| R4 | Root files (Dockerfile, compose changes) are outside any agent's folder | Admin grants it per task (as D17 did earlier) |

## Migrations / dependencies (need separate approval)
- **Migrations:** none expected.
- **Dependencies:** optional extra `cloud` with the `modal` Python package (new dependency, needs approval and an ADR). The installer itself adds none.
- **New ADR needed:** ADR-013 "Cloud GPU mode on Modal" (architecture change).

## Admin approval
- [ ] Plan approved
- [ ] Task assignment approved
- [ ] Dependency `modal` approved
- [ ] Merge approved

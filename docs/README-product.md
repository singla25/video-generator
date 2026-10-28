# VidGen Studio — Dynamic Video Generator

Turn **one template video and one voter list into one personalized video per row.** The spoken name in the template ("Krishan") is replaced by each person's name, in the original speaker's cloned voice, with matching lip movement. Every output is labelled as AI-generated and saved as `<ID>.mp4`.

> **Status:** the batch pipeline and the operator dashboard are built and tested, running on **fake AI adapters**. The real models (speech-to-text, voice cloning, lip sync) have been proven on an Apple Silicon Mac in a feasibility spike and are not wired into the app yet (milestone M2).

## What it does
- **Upload** a template video and an Excel/CSV list, map the columns, validate every row, and preview before you start.
- **Render in batches** on background workers. A render never runs inside a web request; failed rows get a plain-words reason and can be retried one by one.
- **Operate from a dashboard:** live progress, KPIs and charts, a rows table with search and filters, templates with consent status, history, and a security log with a login-throttle alert.
- **Safe by design** (these rules are tested, not just documented):
  - **Consent gate:** a template can't be used until the speaker's consent is uploaded and confirmed.
  - **AI label:** every video carries a visible "AI-Generated / एआई-जनित" band over the top ≥10 % of the frame.
  - **Voter data encrypted at rest** (AES-256-GCM, with a keyed blind index for lookups).
  - **Hardened login:** signed session cookie, CSRF protection, and lockout and throttling stored in the database.

## How it is built
```
React dashboard ──► FastAPI (/api) ──► services ──► domain ◄── infrastructure
                         │                                  (Postgres, Redis, FFmpeg,
                         └── enqueue job ──► Dramatiq worker  storage, AI adapters)
```
- **Layers:** `api → services → domain ← infrastructure` (ports and adapters; a test enforces the layering).
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2 + Alembic on Postgres 16, Dramatiq on Redis 7, FFmpeg, Pillow (Devanagari text via libraqm).
- **Frontend:** React 19, TypeScript, Vite, Tailwind 4, TanStack Query, Recharts. Fonts are self-hosted, with no external requests.
- **AI behind ports:** fake adapters today. Planned real stack (licence-checked): faster-whisper, a small LLM for name spelling, Chatterbox (Hindi voice cloning), Demucs, MuseTalk.
- **Quality:** built test-first. About 1,760 Python tests and 289 dashboard tests, plus Playwright end-to-end and accessibility checks.

## Run it locally (Mac)
Prerequisites: Docker Desktop, `uv`, Node.js. First time only: `uv sync` and `cd frontend && npm ci`.

```bash
docker compose up -d                                  # Postgres + Redis (bound to 127.0.0.1)
scripts/dev_up.sh                                     # first run creates .env with random secrets
.venv/bin/python scripts/dev_setup.py create-admin    # once: set the admin password (only its hash is stored)
scripts/dev_up.sh                                     # starts API, worker and dashboard
```
Open **http://localhost:5173**. Stop with `scripts/dev_down.sh`. `dev_up.sh` never applies a database migration silently: it lists pending ones and asks `y/N`.

## Roadmap
| Milestone | What | State |
|---|---|---|
| M1 | Batch pipeline on fake AI: API, database, auth, workers, FFmpeg, AI label | ✅ done |
| M3 | Operator dashboard | ✅ done |
| M2 | Real AI models and an automatic quality gate | Feasibility proven on a Mac (about 160 s per video, 16–18 GB memory). Production volume needs a GPU |
| CI | Automatic checks on every pull request (GitHub Actions) | Planned (ADR-011) |

## Project documents
Everything lives in `docs/`: requirements, plans, architecture decisions (ADR-001…011), test trees and per-agent changelogs. Open `docs/html/index.html` after running `python scripts/build_docs.py`. The spike results are in `backend/spikes/m2_mac/RESULTS.md`.

## How the project is built
A small AI engineering team (CEO, backend, frontend and tester agents) works under the shared rules in `CLAUDE.md`: approval gates, a safety guard, and mandatory TDD. See `.claude/` and the "Changing the rules" notes in the current README for details.

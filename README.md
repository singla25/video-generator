# Dynamic Video Generator

Turn **one template video into thousands of personalised videos**. Upload a template and a sheet of names; the system replaces the spoken name in the audio, re-syncs the lips, labels every output as AI-generated, and delivers a folder of ready-to-send MP4s with a manifest.

## What it does

1. **Upload** a template video (MP4/MOV) and a sheet (`.xlsx` / `.csv`) with Name, ID and an optional spoken-name column.
2. **Validate** every row (empty or duplicate IDs, over-long names, unsupported characters). Bad rows are skipped with a clear reason and never rendered.
3. **Analyse the template**: find the name in the speech with word timestamps, or mark the slot by hand. The profile is reused by later batches.
4. **Consent gate**: a template can be used only after a consent file is uploaded and confirmed.
5. **Preview and approve** the first row before the batch starts.
6. **Render in the background**: each row is an independent, retry-safe job. Only the name slot changes; the rest of the audio and video is untouched.
7. **Deliver**: `<ID>.mp4` files plus `manifest.csv`, with a ZIP download, a failures CSV, live progress and analytics in the dashboard.

## Key features

- Hindi (Devanagari) and Latin names, with transliteration and per-row spoken-name overrides.
- Voice cloning, lip sync and music-preserving vocal replacement, behind swappable ports (fake models for dev and CI, real models for the local pilot).
- Visible "AI-Generated / एआई-जनित" label on every frame and creator metadata in each file.
- Privacy first: names and IDs encrypted at rest, PII-free logs, batch deletion, automatic retention cleanup and an audit log.
- Pause, resume, cancel and retry-failed controls; session login with CSRF protection and rate limiting.
- Streams large sheets (100k rows) and large downloads instead of loading them into memory.

## Architecture

```
React dashboard → FastAPI API → services → domain (pure rules)
                       │
                       └─ Postgres · Redis queue (Dramatiq workers) · file storage · FFmpeg · AI adapters
```

- Rendering never runs inside a web request: the API creates a job, workers render, the client polls.
- Stack: Python 3.11, FastAPI, SQLAlchemy + Alembic, Postgres 16, Redis 7, Dramatiq, FFmpeg; React + Vite frontend.
- Code lives in `backend/vidgen` (`api`, `services`, `domain`, `ports`, `infrastructure`, `worker`) and `frontend/`.
- Plans and decisions: `docs/plans/` and `docs/decisions/`.

## Run locally (Mac)

The API, the worker and the dashboard all start with one script. It uses the Docker postgres and redis from `docker-compose.yml`, which must already be running, and the fake AI backend (no models, no paid services).

```bash
scripts/dev_up.sh                                       # first run creates .env with random secrets
.venv/bin/python scripts/dev_setup.py create-admin      # once: type your admin password (hidden, only its hash is saved)
scripts/dev_up.sh                                       # starts API, worker and dashboard
```

Open **http://localhost:5173** and log in with the admin password. Stop everything with `scripts/dev_down.sh` (postgres and redis keep running).

- `.env` is git-ignored and holds only local secrets. Never commit it, and never share it.
- `dev_up.sh` never applies a migration silently: if new ones are pending it lists them and asks `y/N` first (no answer, or no terminal, means nothing is applied and nothing starts).
- Logs and PIDs live in `.dev/` (git-ignored). If something fails, read `.dev/logs/*.log`.
- First time on a new machine: `uv sync` and `cd frontend && npm ci`.
- Local AI mode (pilot, Apple silicon): set `VIDGEN_AI_MODE=local` in `.env` (or the shell) and run `dev_up.sh`. It installs the `local-ai` extra, adds `chatterbox-tts` without its stale pins, uses `backend/spikes/m2_mac/work/local_ai_weights` for weights (`VIDGEN_LOCAL_AI_WEIGHTS_DIR`) and runs the worker with one thread. Fake mode is unchanged. See `docs/plans/m2-local-real-ai.md`.

## Testing and quality

```bash
uv run pytest -q                              # all tests
uv run ruff check backend tests               # lint
uv run ruff format --check backend tests      # format
uv run mypy --strict backend/vidgen           # types
cd frontend && npm test                       # dashboard unit tests
```

CI runs the same checks on every pull request (`.github/workflows/ci.yml`).

## Development workflow (AI-assisted)

This project is built with a small team of Claude Code agents (CEO, backend, frontend, tester) working under strict rules: tests first, nothing merged without your approval, and a safety guard against destructive actions. The rules live in `CLAUDE.md` and `.claude/`; only you change them. Start with `claude --agent ceo`.

### How a feature flows

| Step | Who | You approve? |
|------|-----|:---:|
| Listen, restate, MCQ cross-questions, requirement tree | CEO | ✅ tree |
| 2–3 approaches with pros/cons → ADR | CEO | ✅ choice |
| Plan + tasks + **why each agent** + model per task | CEO | ✅ plan |
| Assign tasks (worktrees if parallel) | CEO | ✅ assignment |
| Failing tests: positive / negative / edge | tester | — |
| Code to pass tests, then refactor | backend-dev / frontend-dev | — |
| Verify + coverage report | tester | — |
| Review diff, run checks, report | CEO | ✅ merge |
| Merge `--no-ff` into main, rebuild docs | CEO | — |

See everything at **`docs/html/index.html`**.

### Safety — what the guard blocks

- `rm -rf`, `git reset --hard`, `git clean`, force push, `branch -D`, `find -delete`, `DROP TABLE`
- Reading or writing outside the project, `~`, `/Users`, `.ssh`, `.aws`, Documents/Downloads…
- `.env`, keys, credentials (`.env.example` is allowed)
- Uploading data out (`curl -d/-F/POST`, `scp`, `nc`, `curl | sh`)
- Editing `CLAUDE.md`, `.claude/`, `.git/`
- Running migrations (`alembic upgrade` etc.) — the CEO asks you, and **you run the migration yourself**
- Sub-agents writing outside their folder — enforced when your Claude Code version passes the agent name to hooks; otherwise enforced by the agent rules and the CEO's diff review

Merges, pushes, dependency installs and file deletions always show you a permission prompt.

> The guard is a strong safety net, not a guarantee. Keep `main` protected on GitHub (require PR + passing checks), and keep regular backups/pushes so code can always be recovered.

### Changing the rules
Only you edit `CLAUDE.md` and `.claude/` (agents can't). Ask the CEO to *propose* new skills or agents; you approve and add them.

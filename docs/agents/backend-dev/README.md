# Backend developer (`backend-dev`)

## Role
Implements the Python API, video pipeline, job workers, storage and database code to make the tester's failing tests pass.

## Writes only in
`backend/` (plus root files `pyproject.toml`, `uv.lock`, `.python-version`, `docker-compose.yml` per decision D17)

## Definition
`.claude/agents/backend-dev.md`

## Current status
T2 done: tooling and empty package skeleton (`backend/vidgen`). No business logic yet.

## Commands
Run everything through uv: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
Alembic config: `uv run alembic -c backend/alembic.ini <cmd>` (no revisions yet).

## Environment variables (names only; prefix `VIDGEN_`)
Required (no defaults): `VIDGEN_CREATOR_ENTITY` (plain text, non-empty; written into video metadata), plus secrets `VIDGEN_ENCRYPTION_KEY`, `VIDGEN_INDEX_KEY`, `VIDGEN_SESSION_SECRET`, `VIDGEN_ADMIN_PASSWORD_HASH`.

Optional (have defaults): `VIDGEN_DATABASE_URL`, `VIDGEN_REDIS_URL`, `VIDGEN_STORAGE_ROOT`, `VIDGEN_AI_BACKEND` (fake|real),
`VIDGEN_MAX_VIDEO_BYTES`, `VIDGEN_MAX_VIDEO_SECONDS`, `VIDGEN_MIN_VIDEO_SECONDS`, `VIDGEN_MAX_SHEET_BYTES`, `VIDGEN_MAX_SHEET_ROWS`,
`VIDGEN_MAX_CONSENT_BYTES`, `VIDGEN_MAX_NAME_GRAPHEMES`, `VIDGEN_CROSSFADE_MS` (20-50), `VIDGEN_MAX_STRETCH_RATIO`,
`VIDGEN_MAX_EXTENSION_SECONDS`, `VIDGEN_DURATION_TOLERANCE_MS`, `VIDGEN_LOUDNESS_TOLERANCE_LU`, `VIDGEN_STT_CONFIDENCE_THRESHOLD`,
`VIDGEN_ROW_TIMEOUT_SECONDS`, `VIDGEN_RETRY_DELAY_SECONDS`, `VIDGEN_MAX_RETRIES`, `VIDGEN_RETENTION_DAYS`,
`VIDGEN_LOGIN_MAX_FAILURES`, `VIDGEN_LOGIN_WINDOW_MINUTES`, `VIDGEN_LOGIN_LOCKOUT_MINUTES`.

docker-compose only: `VIDGEN_DB_USER`, `VIDGEN_DB_PASSWORD`, `VIDGEN_DB_NAME`, `VIDGEN_DB_PORT`, `VIDGEN_REDIS_PORT`.

## Running the system
- API (served under `/api`): `uv run uvicorn vidgen.api.server:create_server_app --factory --host 127.0.0.1 --port 8000`
- Worker: `uv run python -m vidgen.worker`
- Services (dev): `docker compose up -d` (Postgres and Redis on 127.0.0.1)
- Migrations are run by the Admin: `uv run alembic -c backend/alembic.ini upgrade head`

# ADR-001 — Pin Python 3.11 and manage the environment with uv

## Status
Accepted (Admin, 2026-10-18, with plan `m1-batch-pipeline`)

## Context
`CLAUDE.md` requires Python 3.11+, but `pyproject.toml` allows `>=3.10` and the current `.venv` runs Python 3.14. The AI libraries needed in M2 (PyTorch, speech-to-text, voice cloning, lip sync) usually lag behind the newest Python. We need one reproducible interpreter for every agent, CI and the GPU server.

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **uv** | Installs Python 3.11 itself; very fast; `uv.lock` makes installs reproducible | One new tool | Free | Yes (CI/Docker friendly) |
| Homebrew python@3.11 + venv + pip-tools | Only standard tools | Slower; Python versions managed by hand | Free | Yes |
| pyenv + venv + pip | Flexible version switching | More moving parts, no lockfile by default | Free | Yes |

## Decision
Pin **Python 3.11** (`requires-python = ">=3.11,<3.12"`, `.python-version` = `3.11`) and use **uv** with a committed `uv.lock`. Ruff `target-version = "py311"`, mypy `python_version = "3.11"`.

## Setup — done by the Admin
```bash
# 1. Tools
brew install uv ffmpeg
brew install --cask docker          # Docker Desktop (OrbStack also works)

# 2. Move the old Python 3.14 venv aside (agents never delete folders)
mv .venv .venv-py314-old            # delete it yourself later if you wish

# 3. Python 3.11
uv python install 3.11

# 4. After task T2 is merged to main
uv sync                              # creates .venv (3.11) from uv.lock
docker compose up -d                 # Postgres + Redis for dev/tests
uv run pytest -q && uv run ruff check . && uv run mypy backend
```
Every agent runs tools through `uv run …`.

## Consequences
- Same interpreter and package versions everywhere; GPU images in M2 use the same lockfile.
- Upgrading to 3.12 later is a new ADR plus a `uv lock` refresh.
- Adding a dependency becomes `uv add <pkg>`, and it still needs Admin approval.

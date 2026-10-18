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

### Devanagari text shaping (libraqm) — macOS dev machines (added 2026-10-19, D-12)
Pillow loads libraqm and fribidi **at runtime**, looking for the *unversioned* library names (`libraqm.dylib`, `libfribidi.dylib`). Homebrew on Apple Silicon installs them under `/opt/homebrew/lib`, which is not on the default search path.

Don't use `DYLD_FALLBACK_LIBRARY_PATH`: macOS System Integrity Protection strips `DYLD_*` variables whenever `/bin/sh` or `/bin/zsh` starts a program, so tools, scripts and workers silently lose it. `~/lib` was not searched on the Admin's macOS either. Working fix (verified by the Admin and CEO):
```bash
brew install libraqm                     # pulls in fribidi + harfbuzz
sudo mkdir -p /usr/local/lib
for f in /opt/homebrew/lib/libraqm*.dylib /opt/homebrew/lib/libfribidi*.dylib; do
  sudo ln -sf "$f" /usr/local/lib/
done
# verify in a clean environment (must print True):
env -u DYLD_FALLBACK_LIBRARY_PATH uv run python -c "from PIL import features; print('raqm:', features.check('raqm'))"
```
`tests/unit/infra/test_label_renderer.py::test_complex_text_shaping_is_active_for_devanagari` fails if shaping is not active, so a misconfigured machine is caught immediately.
**Linux worker images (M2):** install the distro package (e.g. `libraqm0` + `libfribidi0` on Debian/Ubuntu); no symlinks are needed there.

## Consequences
- Same interpreter and package versions everywhere; GPU images in M2 use the same lockfile.
- Upgrading to 3.12 later is a new ADR plus a `uv lock` refresh.
- Adding a dependency becomes `uv add <pkg>`, and it still needs Admin approval.

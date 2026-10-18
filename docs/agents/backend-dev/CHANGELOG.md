# Backend developer — Changelog

Newest first. One entry per task.

## 2026-10-18 — T6 (ingest adapters)
- Added `infrastructure/sheets/reader.py` (FileSheetReader), `ffmpeg/probe.py` (FfprobeVideoProbe), `storage/local.py` (LocalStorage), `crypto/aesgcm.py` (AesGcmCipher), `conformance.py` (mypy port checks).
- Ports: new `VideoProbe`; `probe` removed from `VideoEncoder`; `SheetReader` gained `numbered_rows` and `sheet_name`; data types `SheetRow`, `VideoInfo`, `VideoLimits` live in `ports/models.py` (adapters re-export them).
- Tests: 478 not-slow + 3 slow pass; infrastructure coverage 93 % (each module 93-98 %).
- Choices: xlsx uses the first *visible* sheet and pads rows to header width; mp4 vs mov told apart by the `major_brand` tag; storage publishes with hard-link (`os.link`) so a name clash can never overwrite; cipher blob = key-id length byte + key id + nonce + ciphertext, key id authenticated.
- Open: none.

## 2026-10-18 — T4 (domain)
- Implemented `vidgen.domain.{codes,headers,validation,naming,status,timing,retry,stats,slot_match}` (pure: stdlib + `regex`).
- 334 tests in tests/unit/domain pass; domain coverage 100 % line + branch. ruff, ruff format, mypy strict clean.
- Choices: ZWJ/ZWNJ allowed only between Devanagari characters; Devanagari digits and dandas are not name characters; only valid rows register their ID for duplicate detection; header/mapping errors other than a missing column use `UNSUPPORTED_SHEET` / `COLUMN_NOT_FOUND`; `SlotTooShortError` uses `SLOT_NOT_FOUND`.
- Open: none.

## 2026-10-18 — T2 (tooling + skeleton)
- Python 3.11 + uv, hatchling build, approved runtime/dev deps (incl. `regex`, `types-regex`), tool config (ruff, mypy strict, pytest, coverage).
- `backend/vidgen` skeleton per ADR-008, Protocols in `ports/interfaces.py`, `settings.py`, `logging.py` (closed non-PII context).
- Alembic initialised in `backend/migrations` (`backend/alembic.ini`), no revisions.
- `docker-compose.yml` (postgres:16, redis:7, localhost-only). Ruff excludes `scripts/`, `.claude/`, `main.py`.
- Files: `pyproject.toml`, `uv.lock`, `.python-version`, `docker-compose.yml`, `backend/**`, this doc folder.
- Tests added: none (skeleton). Open: `docker compose` plugin missing on this Mac; compose file only YAML-parsed.

## 2026-10-18 — SETUP
- Agent created.

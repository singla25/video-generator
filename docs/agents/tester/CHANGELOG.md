# Tester — Changelog

Newest first. One entry per task.

## 2026-10-18 — T3 (RED: domain unit tests)
- Added tests/unit/domain (13 files, 166 test functions) + tests/fixtures/names.py. Branch feat/m1-domain.
- Contract modules: headers, codes, validation, naming, status, timing, retry, stats, slot_match. All fail with ModuleNotFoundError (RED).
- Ruff check/format clean; mypy --strict only reports the missing vidgen.domain modules.
- Non-ASCII in tests is written as \\u escapes (readable diffs, ruff RUF001).

## 2026-10-18 — T1 follow-up (Addendum B)
- Applied Addendum B1–B13 to `docs/test-tree/m1-batch-pipeline.md`; open issues replaced by a resolution table. Added 24 cases (5 positive, 8 negative, 11 edge). Final: 105 positive / 98 negative / 171 edge = 374.
- New ambiguities: NA-1 (ETA remaining count), NA-2 (idempotency key reuse), NA-3 (STT tie-break/threshold).
- Files: docs/test-tree/m1-batch-pipeline.md. Tests added: none.

## 2026-10-18 — T1 (M1 test tree)
- Wrote `docs/test-tree/m1-batch-pipeline.md` covering AC1–AC19 + E2E, with Addendum A applied.
- Files: docs/test-tree/m1-batch-pipeline.md. Tests added: none (tree only).
- Open issues: OI-1..OI-13 listed at end of the tree.

## 2026-10-18 — SETUP
- Agent created.

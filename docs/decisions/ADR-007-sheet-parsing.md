# ADR-007 — Excel/CSV parsing: openpyxl (read-only) + csv

## Status
Accepted (Admin, 2026-10-18)

## Context
Sheets range from 10 to 100k+ rows. Validation must answer in < 3 s for MVP sizes without loading everything into memory.

## Options
| Option | Pros | Cons | Cost |
|--------|------|------|------|
| **openpyxl read-only + stdlib csv** | Streams rows; light | A bit more code | Low |
| pandas | One-liners | Heavy; whole sheet in memory | Low |
| python-calamine | Fastest | Newer; Rust binary wheel | Low |

## Decision
**openpyxl in `read_only` mode** for `.xlsx` and **stdlib `csv`** (UTF-8 with BOM handling) for `.csv`, both behind a single `SheetReader` port that yields normalised rows.

## Consequences
- `.xls` (old Excel) is not supported; users export to `.xlsx` or `.csv`.
- Formulas are read as cached values only.

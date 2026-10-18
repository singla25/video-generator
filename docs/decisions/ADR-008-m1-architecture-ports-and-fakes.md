# ADR-008 — M1 architecture: ports-and-adapters with fake AI adapters

## Status
Accepted (Admin, 2026-10-18, with plan `m1-batch-pipeline`)

## Context
The real AI models (speech-to-text, transliteration, voice cloning, lip sync) need a GPU and a licence review (M2). The whole product flow must still be built and fully tested now, on a Mac CPU (D2, D5).

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **Ports + deterministic fake adapters in M1, real adapters in M2** | Full flow testable on CPU today; M2 only swaps adapters | Fakes say nothing about real quality | Low | Yes |
| Wait for real models before building the product | Real quality from day one | Blocks everything on GPU and licence work | High | — |

## Decision
Layering `api → services → domain ← infrastructure` (`CLAUDE.md §4`):
```
backend/vidgen/
  domain/          pure rules: validation, naming, statuses, failure codes, timing math (no I/O)
  ports/           Protocols: SpeechToText, Transliterator, VoiceCloner, LipSyncer, TextDetector,
                   TextRenderer, VideoEncoder, QualityChecker, Storage, SheetReader, Cipher,
                   repositories, Clock
  services/        use cases: templates, batches, preview, render_row, analytics, retention, audit
  infrastructure/  ffmpeg/, storage/ (local; S3 in M2), db/, crypto/, queue/ (Dramatiq), fakes/
  api/             FastAPI routers, schemas, auth, error mapping
  settings.py      pydantic-settings
backend/migrations/  Alembic
tests/  unit/ · integration/ · e2e/ · fixtures/ (synthetic media generated with ffmpeg)
```
Fakes are deterministic. The fake STT returns configured words and timestamps, the fake voice produces a tone whose length scales with the name, and the fake lip sync passes frames through unchanged. Adapters are chosen by a setting (`ai_backend = fake | real`).

## Consequences
- M1 output videos are structurally correct (format, timing, label, metadata, manifest) but carry a placeholder voice.
- M2 = new adapters + quality checks Q1–Q6, with no changes to services or API.

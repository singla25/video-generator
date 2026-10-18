# ADR-002 — Job queue: Dramatiq + Redis

## Status
Accepted (Admin, 2026-10-18)

## Context
Rendering must never run inside a web request. Each row is an independent, idempotent job. A worker crash must lead to exactly one automatic retry (D11), and quality failures must not be retried automatically.

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **Dramatiq + Redis** | Acks after the job finishes, so a killed worker's job is redelivered; built-in retries, time limits, middleware | Smaller community than Celery | Low | Yes, add workers |
| Celery + Redis | Most mature, rich features | Heavy configuration; needs `acks_late` and related settings for crash safety | Medium–high | Yes |
| RQ + Redis | Simplest API | A killed worker's job is left stranded; needs custom recovery | Low | Yes |

## Decision
**Dramatiq with the Redis broker.** Retry middleware is limited to 1 retry, and only for retryable errors (crash, `RENDER_TIMEOUT`, `STORAGE_ERROR`). Tests use Dramatiq's `StubBroker`.

## Consequences
- Workers scale horizontally; queue depth is visible from Redis.
- Idempotency is still our job: a row job checks its stored state and writes output atomically (temp file → rename).
- Pause/cancel are enforced by workers reading the batch state before each row and between pipeline stages.

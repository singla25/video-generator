# ADR-014: Keep the API light and the layering strict (PROPOSED)

**Status:** PROPOSED by the optimizer (round 3). Not accepted. Needs the Admin's yes before any code changes (CLAUDE.md section 2, items 1 and 7).
**Date:** 2026-11-23
**Evidence:** `docs/reports/OPTIMIZATION-ROUND-3.md`

## Context

The default architecture in CLAUDE.md section 4 is `api -> services -> domain <- infrastructure`, rendering and heavy work in workers, a stateless API, storage and video engine behind interfaces, streamed large files. A static check of the code shows the rules mostly hold (the domain and service layers are clean) and five places where they do not:

1. Template analysis (speech-to-text on the whole video) runs inside the HTTP request, inside an open database transaction, and in `local` mode in the API process.
2. The worker reads the whole template video into memory for every row.
3. `infrastructure/db/login_state.py` imports types from `services/login_guard.py`.
4. The `api` package imports SQLAlchemy, Redis and Dramatiq only to catch their exceptions.
5. The composition root (`api/container.py`) sits in `api` and is imported by `worker/runner.py`.

## Decision (proposed)

1. **Heavy AI work only in workers.** `analyse` becomes a queued job (same pattern as previews): the endpoint returns 202 with a status, the dashboard polls. As a first, smaller step, transcription moves outside the database transaction.
2. **Stream large files.** Copy the template with `shutil.copyfileobj`; later cache one local copy per batch per worker.
3. **Dependency direction.** Login-guard state types move to `domain` (values) and `ports` (the store protocol); infrastructure imports only domain and ports.
4. **Errors at the boundary.** Adapters translate driver errors to one `DependencyUnavailableError` (domain); `api` maps it to the existing "dependency unavailable" response and no longer imports driver packages.
5. **One composition root.** `vidgen/bootstrap/` builds the container for both `api` and `worker`; `api/` keeps routes and schemas only.
6. **Guard rails.** Extend `tests/unit/meta/test_architecture.py` with: no `infrastructure -> services`, no `api` or `services` third-party driver imports, `worker` does not import `api`.

## Consequences

- Positive: a light API, lower worker memory, replaceable drivers, the layering enforced by a test.
- Negative: the dashboard analyse flow changes (poll instead of wait); several files move (folder structure change), so the change is staged: items 2 and 6 first (no behaviour change), then 3 and 4, then 5, then 1.
- Rollback: every step is its own PR; items 2 to 6 have no data or migration impact. Item 1 adds a job type and a status field on the template; if it needs a column it needs a migration, which needs separate approval.

## Alternatives considered

- Leave analysis synchronous and document it: simplest, but the API process keeps loading models and a slow analysis ties up a worker thread and a connection.
- Move only `transcribe` out of the transaction: removes the held connection but not the model in the API process.

## Open questions for the Admin

1. Is a polling analyse flow acceptable for the dashboard (the analysis result today appears after one request)?
2. May the folder `vidgen/bootstrap/` be created (structure change)?

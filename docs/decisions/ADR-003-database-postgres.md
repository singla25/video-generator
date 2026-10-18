# ADR-003 — Database: PostgreSQL everywhere, SQLAlchemy 2 + Alembic

## Status
Accepted (Admin, 2026-10-18)

## Context
Batches, rows, templates, audit log and retention data need a durable store that is safe under many concurrent workers. Dev, tests and prod should behave the same way.

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **Postgres in dev/tests/prod (Docker), SQLAlchemy 2 + Alembic** | Identical behaviour everywhere; row locking (`SELECT … FOR UPDATE SKIP LOCKED`) | Needs Docker on the Mac | Low–medium | Yes |
| SQLite dev/tests, Postgres prod | Nothing to install | Dialect and concurrency differences show up only in prod | Low | Prod only |

## Decision
**PostgreSQL 16** via `docker-compose.yml` for dev and tests, **SQLAlchemy 2.0** (typed ORM) with **psycopg 3**, and **Alembic** migrations in `backend/migrations/`. Tests use a separate throwaway database and build the schema from the models. Migration files are reviewed by the CEO and **run only by the Admin** (`CLAUDE.md §2.3`).

## Consequences
- Every table carries `campaign_id`, ready for multi-user (D6).
- Docker Desktop becomes a dev prerequisite.
- Schema changes always go through an Alembic migration plus Admin approval.

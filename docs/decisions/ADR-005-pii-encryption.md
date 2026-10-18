# ADR-005 — Voter data encryption: app-level encryption + keyed ID hash

## Status
Accepted (Admin, 2026-10-18)

## Context
Names and IDs are personal data (C5). They must be encrypted at rest, never logged, and duplicate IDs must still be detectable.

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **App-level (cryptography AES-GCM) + HMAC-SHA256 blind index for ID** | DB never sees plaintext; duplicate check via hash; key from configuration | No SQL search on names | Low–medium | Yes |
| Postgres pgcrypto | DB-side | Key passes through SQL and can leak into DB logs | Medium | Yes |
| Disk encryption only | No code | DB access = plaintext | None | n/a |

## Decision
Encrypt `name`, `spoken_name` and `voter_id` with **AES-256-GCM** (`cryptography`) inside a `Cipher` port. Store an **HMAC-SHA256 blind index** of the normalised ID for duplicate detection. Two separate keys (encryption, index) are supplied through runtime configuration, never committed, with a key ID stored per row so keys can be rotated. Logs reference rows only by row number or UUID.

## Consequences
- Searching rows by name in the dashboard happens after decryption in the service layer, scoped to one batch (≤ 100k rows, paged).
- Losing the key means losing the data. Key backup is the Admin's operational task.
- A tester check asserts that no fixture name or ID appears in captured logs.

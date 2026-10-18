# ADR-006 — Admin login: signed session cookie

## Status
Accepted (Admin, 2026-10-18)

## Context
MVP has a single admin login (D6), the API must stay stateless, and voter data is only visible to logged-in users (C5).

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **Signed httpOnly session cookie + argon2 password hash from configuration** | Stateless; not readable by JS; easy to extend to users table | Needs CSRF protection | Low | Yes |
| JWT bearer token | Common | Token in JS storage (XSS); hard logout | Medium | Yes |
| HTTP Basic | Trivial | Poor UX; password on every request | Very low | Poor |

## Decision
Login checks the password against an **argon2** hash supplied through configuration, then issues a **signed, time-limited, httpOnly, Secure, SameSite=strict** cookie (`itsdangerous`). State-changing requests also require a CSRF token (double-submit). Failed logins are rate-limited.

## Consequences
- Moving to multiple operators later means adding a `users` table. The cookie format stays the same.
- Logout is enforced by cookie expiry plus a server-side "session version" setting that can be bumped to invalidate all sessions.

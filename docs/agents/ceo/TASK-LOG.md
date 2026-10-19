# CEO — Task log

## Process rules (Admin, 2026-10-19)
- The Admin does not run `git add` or `git commit` in the project while agents are working. If something needs committing, the Admin asks the CEO.
- Every brief requires: stage explicit paths only; every commit carries the standard Co-Authored-By/Claude-Session trailer and a task-related Conventional Commit message (approved by the Admin).

## Incident notes
- 2026-10-19 01:01: commit `8f575e9` "chore: agent team setup" (deletion of the duplicate `video-generator-agents/CLAUDE.md`) was made by the Admin by accident: a queued setup command ran when a 6-hour-old `rm` finished. The tester was not involved. Kept as is (Admin decision).
- 2026-10-19 01:04: an accidental `git init && git add .` by the Admin staged 6 of backend-dev's in-progress T10-round-2 files (no commit made, file contents unchanged). The CEO handles the index when backend-dev reports; CEO commits use `git commit --only <paths>` meanwhile.

Plan: `docs/plans/m1-batch-pipeline.md` (approved 2026-10-18)

| ID | Task | Agent | Model | Status | Approved by Admin | Merged |
|----|------|-------|-------|--------|-------------------|--------|
| T0 | Install uv, ffmpeg, Docker; move old .venv | Admin | — | Waiting for Admin | — | — |
| T1 | M1 test tree | tester | sonnet | ✅ Done & CEO-reviewed — 374 cases (105 P / 98 N / 171 E), addenda A–C applied in plan; branch `feat/tester/m1-tree` (round 1 was blocked by guard on worktree) | Yes, 2026-10-18 | Waits for gate 1 |
| T0 | Install tools, move old venv | Admin | — | ✅ Done 2026-10-18 | — | — |
| T2 | Tooling + skeleton | backend-dev | sonnet | ✅ Done & CEO-reviewed after 1 fix round (video limit 300 s, creator_entity required, port semantics). Incident: `ruff format .` briefly touched `.claude/` + `scripts/`, reverted, verified identical; Admin informed | Yes, 2026-10-18 | Waits for gate 1 |
| — | Merge gate 1 (T1 + T2) | CEO | — | ✅ Merged `bb940be`, checks green on main | Yes, 2026-10-18 | ✅ |
| T3 | RED: domain unit tests | tester | sonnet | ✅ Done & CEO-reviewed after 1 fix round (accented names invalid per D9) — 166 tests / 13 files, fail only on missing modules. Note: commit a12967b also swept in the CEO's uncommitted Addendum D (content verified identical; cause: shared folder + non-explicit staging) | Yes, 2026-10-18 | — |
| T4 | GREEN+REFACTOR: domain/ | backend-dev | sonnet | ✅ Done & CEO-reviewed after 1 fix round (escape invisible joiners) — 334/334 pass, 100 % line+branch coverage, branch `feat/m1-domain` @ 1bf4b64 | Yes, 2026-10-18 | Waits for gate 2 |
| T5 | RED: ingestion, probe, storage, cipher | tester | sonnet | ✅ Done & CEO-reviewed (105 tests + 3 slow; fail only on missing modules; 1 guard block on URL text in a heredoc, benign) @ 935d0c0 | Yes, 2026-10-18 | — |
| T6 | GREEN: SheetReader, VideoProbe, LocalStorage, Cipher | backend-dev | sonnet | ✅ Done & CEO-reviewed — 478 pass + 3 slow pass, infra coverage 93 % @ cf7b81a (nit: conformance.py 0 % → tidy in T8) | Yes, 2026-10-18 | — |
| T7 | RED: FFmpeg engine | tester | sonnet | ✅ Done & CEO-reviewed after 1 fix round (behavioural checks instead of filter names) — 115 fast + 1 slow tests @ a91cf27 | Yes, 2026-10-18 | — |
| T8 | GREEN: FFmpeg engine + label renderer | backend-dev | sonnet | ✅ Done & CEO-reviewed after 1 fix round (invisible joiners → reuse domain constants) @ 3f8c08f. With raqm: 649/649 pass; label visually verified (correct Devanagari shaping, 130 px band on 1080×1300). Fonts committed by CEO at Admin request @ 08c247d | Yes, 2026-10-18 | Waits for gate 2 |
| T7b | Fix 4 test defects, cover ffmpeg helpers to 100 %, require Devanagari shaping | tester | sonnet | ✅ Done & CEO-reviewed @ 7d3cfb3 — 644 pass; only the shaping test fails until Admin installs libraqm (D-12) | Yes (within T7/T8 scope) | — |
| — | Merge gate 2 (slices A + B) | CEO | — | ✅ Merged `c3aa763`, 649 pass on main | Yes, 2026-10-19 | ✅ |
| T9 | RED: DB models/repos, auth, templates + consent + slot, audit | tester | sonnet | ✅ Done & CEO-reviewed after 2 rounds (target word per template D-13; lockout D-15 → per-client + global throttle + sessions unaffected + alert + trusted proxies) @ ab6bd94. Interrupted once by usage limit and resumed. Dev DB verified untouched | Yes, 2026-10-19 | — |
| T10 | GREEN: models, migration 0001 (created, not run), repos, auth, template API, audit | backend-dev | sonnet | ✅ Done & CEO-reviewed after 2 rounds @ 2c97b13: D-17 applied (login state in Postgres, live-duplicate partial unique index, finished_at index; 0001 amended, migration test 9/9 on `vidgen_migration_test`); 870 pass + 1 tester expectation (7th table) → T10b follow-up. Dev DB still empty | Yes, 2026-10-19 | — |
| T10b | RED: fix alert test; login-guard persistence; DB duplicate guard; migration up/down/up test (D-14); clock coverage | tester | sonnet | ✅ Done & CEO-reviewed @ a9a40af — 15 expected failures, 856 pass; migration test uses `vidgen_migration_test` with a `_test` name guard; dev DB verified empty | Yes (within T10 scope; migration test approved 2026-10-19) | — |
| — | Migration 0001 on dev DB `vidgen` | Admin | — | ✅ Run by Admin 2026-10-19 (after a rehearsal on `vidgen_rehearsal_test`, since dropped). CEO verified read-only: 7 tables + alembic_version @ 0001, all empty, batch_rows PII only `*_enc` bytea + `voter_id_index`, duplicate-guard and finished_at indexes present | Yes, 2026-10-19 | n/a |
| T11 | RED: batch API | tester | sonnet | ✅ Done & CEO-reviewed (+1 follow-up: on-disk folder collision) @ a83e3e9 — 195 new tests, 184 fail on missing routes, 882 pass | Yes, 2026-10-19 | — |
| T12 | GREEN: batch services + endpoints | backend-dev | sonnet | ✅ Done & CEO-reviewed @ c0ced81 (interrupted by usage limit, resumed) — 1064 pass; 7 failures = test clock/session defects → T11b; coverage 89–100 %; no migration 0002 (DD-8) | Yes, 2026-10-19 | — |
| T11b | Tests: re-login after clock jumps; access-log query redaction (DD-9) | tester | sonnet | ✅ Done & CEO-reviewed @ e418c64 — session TTL untouched; 4 access-log tests fail until T14 | Delegated (CEO) | — |
| T13 | RED: worker pipeline | tester | sonnet | ✅ Done & CEO-reviewed after 1 round (stage order DD-6) @ fdb25d2 — 123+ tests; bodies verified with throwaway stubs | Delegated (CEO), 2026-10-19 | — |
| T14 | GREEN: render pipeline, worker, Dramatiq queue, fake adapters, access-log redaction | backend-dev | sonnet | ✅ Done & CEO-verified after 2 rounds @ 244a0b2 — 1230 pass (incl. slow + e2e), 97 % total, domain/render_row/manifest 100 %, no infra imports in services | Delegated (CEO) | Waits for gate 3 |
| T15 | VERIFY: runner tests, tree walk, COVERAGE.md | tester | sonnet | ✅ Done & CEO-verified @ 4f432b2 — 1597 pass + 3 strict xfail (V1/V2/V3), 98.2 % coverage, AC 19/19 ✅, all 374 tree IDs tested or annotated | Delegated (CEO) | — |
| T16 | CEO review → gate 3 | CEO | — | ✅ Review clean; V1 split done (a11472d, 046b3fd); final run 1611 pass + 1 xfail (V2), 98 % | Delegated (CEO) | ✅ gate 3 (DD-12) |
| T13c | Tests: 8 defect fixes, injection contract + layering guard, domain/fakes coverage | tester | sonnet | ✅ Done & CEO-reviewed @ 15b6ef0; T14 round 2 (layering) in progress | Delegated (CEO) | — |
| T15a | RED: E2E tests (synthetic 10-row batch, retry, deletion) | tester | sonnet | ✅ Done & CEO-reviewed @ 5a1b106 — 3 e2e tests (real app/DB/storage/ffmpeg/label; fake AI; in-process StubBroker worker); probes label + creator metadata | Delegated (CEO) | — |
| T15–T16 | Verify + coverage report; CEO review → gate 3 | tester / CEO | sonnet | Planned | — | — |
| — | **Merge gate 3** (M1 complete) | CEO | — | ✅ Merged `49f0767` (DD-12); main: 1611 pass + 1 xfail, mypy/ruff clean | Delegated (CEO) | ✅ |
| F0 | Node.js | Admin | — | ✅ Already installed (v26.12.0, DD-2); placeholder brand DD-1 | — | — |
| F1a | Frontend tooling scaffold (no app code) | frontend-dev | sonnet | ✅ Done & CEO-verified after 3 rounds @ b42f597 (types DD-14, Tailwind 4 DD-15); npm audit 0, build ok | Delegated (CEO) | — |
| F1 | RED: dashboard test tree + failing UI tests | tester (fresh agent) | sonnet | Round 1 @ ae65ef6 (156 case IDs). Round 2 in progress: drop symlink, DD-17 contract + backend RED tests | Delegated (CEO) | — |
| F1b | Vitest config resolves tests/frontend (scoped fs.allow) | frontend-dev | sonnet | In progress (DD-16) | Delegated (CEO) | — |
| B-M3 | Backend: inspect-sheet + failure_code filter (GREEN after F1 r2) | backend-dev | sonnet | Planned | Delegated (CEO) | — |
| F1–F7 | M3 dashboard (plan `docs/plans/m3-dashboard.md`, ADR-009) | tester / frontend-dev / CEO | sonnet | Planned; F1 after F1a | Plan: yes (Admin); assignment: delegated | — |

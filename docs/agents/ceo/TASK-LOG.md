# CEO — Task log

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
| T10 | GREEN: models, migration 0001 (created, not run), repos, auth, template API, audit | backend-dev | sonnet | In progress on `feat/m1-api` | Yes, 2026-10-19 | — |
| T11 | RED: batch API | tester | sonnet | Waiting for T10 | Yes, 2026-10-19 | — |
| T12 | GREEN: batch services + endpoints | backend-dev | sonnet | Waiting for T11 | Yes, 2026-10-19 | — |
| T13–T16 | See plan | tester / backend-dev / CEO | sonnet | Planned | — | — |
| F1–F6 | M3 frontend | tester / frontend-dev | sonnet | Blocked (screenshots, ADR-009) | — | — |

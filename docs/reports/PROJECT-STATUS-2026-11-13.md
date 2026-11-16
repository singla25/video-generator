# Project status report, 2026-11-13

Written by the CEO on branch `docs/ceo/status-report-2026-11-13` from `origin/main`. Documentation only: no code, tests, dependencies or migrations were changed or run for this report. Numbers in section 7 are the last check reported by the Admin and were not re-run for this report.

> **Update 2026-11-16 (CEO refresh at the Admin's request).** Since this report was written, PRs #18, #20 and #21 have been merged. #22 (rescue of the M2 docs) and #23 (C5: Modal is for demo data only) are open. Corrected below, each marked "2026-11-16": the summary, the PR table, the branch rows for the Docker work and `feat/m2-mac-first`, B3 (kept, now decided), B4, B17, B18, and section 11. The TASK-LOG on main was cleaned by #21 (15 finished rows marked done; F7 and G8 still open). Everything else is unchanged from 2026-11-13.

## Summary

- End to end, the local pipeline works: sheet upload, validation, consent-gated template, preview with confirmed spelling, local AI render (voice, lip sync, AI bubble), output folder and manifest, and the dashboard that drives it.
- Merged to `main`: M1 batch pipeline (gate 3), M3 dashboard (gate), the M2 local pilot (PR #5), and PRs #6 to #17 (label, CI, draft and list fixes, spoken suffix, multi name slots).
- Last merged PR is #17 (`2496183`, DD-40); `main` is at that commit. Migration 0002 is in the repo; the real database `vidgen` is at 0002.
- Open: PR #18 (guard change, needs Admin merge). Another session holds unmerged work for the Docker app, terminal installer and Modal cloud mode (branch `claude/exciting-cannon-t53afd`), waiting for four Admin approvals.
  - **2026-11-16:** #18 merged. The four approvals were given, and Stage 1 (Docker app stack, installer, README modes) was merged as PR #20. Modal adapters (T4) wait for spike P2-S (credit cap and the Admin's go still pending). C5 is in open PR #23.
- Open: the G8 licence gate plan is a draft and not approved. Three weights (Demucs, face-parse-bisent, S3FD/FAN) are pilot-only on the Admin's Mac (DD-31, ADR-012).
- Not done: per-row spoken names, music bed under the name slot, automatic detection of every name occurrence, per-template suffix and pause (each needs a migration or a design choice).
- Top risk 1: the licence status of the pilot weights. Outputs must stay on the Admin's Mac until B1 is closed.
- Top risk 2: privacy. A cloud render mode (Modal) would send names, voices and faces off the Mac, against rule C5. This needs an Admin decision (B3).
- Top risk 3: lip sync and voice are tuned on one template and one speaker; quality on other faces is untested (B10).
- Not verified for this report: the test, lint, type and e2e numbers in section 7 are the Admin's last reported check; the CI result of each PR is taken from the PR list, not re-run here.
- Not verified: the Hindi spelling automation is right only about 45 to 55 % of the time for rows other than the confirmed preview row (B2).
- Not verified: `mypy --strict` passes only without the optional local-ai packages; with them installed, 8 errors remain (B12).

## 1. Pull requests

All 18 PRs in the repository (`gh pr list --state all`). PR #4 was closed without merging; its change is contained in PR #5. PRs #15 and #16 were made by another session (README and docs).

| # | Title | State | Merged (date) | Branch |
|---|-------|-------|---------------|--------|
| 23 | feat(installer): Modal mode is for demo and learning data only (C5) | OPEN (2026-11-16) | - | feat/backend/c5-demo-only |
| 22 | docs(ceo): rescue M2 Mac-first plan, ADR-010 G1 licence audit, DD-30/DD-31 | OPEN (2026-11-16) | - | docs/ceo/m2-docs-rescue |
| 21 | docs(ceo): mark finished TASK-LOG items done (F7, G8 stay open) | MERGED | 2026-11-16 | docs/ceo/task-log-cleanup |
| 20 | Docker app stack, guided installer and README modes (Stage 1 of docker-and-cloud-setup) | MERGED | 2026-11-16 | feat/tester/cloud-setup |
| 19 | docs(ceo): project status report and next-phase backlog (this report) | OPEN | - | docs/ceo/status-report-2026-11-13 |
| 18 | chore(guard): worktree paths and write grants for the Docker and installer files | MERGED (2026-11-16) | 2026-11-16 | chore/guard-grants-and-worktrees |
| 17 | feat: several name slots per template (DD-40) | MERGED | 2026-11-12 | feat/multi-slot |
| 16 | Claude/exciting cannon t53afd (other session: README and docs) | MERGED | 2026-11-12 | claude/exciting-cannon-t53afd |
| 15 | Claude/exciting cannon t53afd (other session: README and docs) | MERGED | 2026-11-06 | claude/exciting-cannon-t53afd |
| 14 | feat: spoken suffix after the name; name in the middle of the video (DD-39) | MERGED | 2026-10-31 | feat/spoken-suffix-marketing-demo |
| 13 | fix: resume a draft from the row counts the API sends (DD-38 follow-up) | MERGED | 2026-10-31 | fix/resume-from-counts |
| 12 | fix: confirmed spelling survives a new preview; drafts visible and resumable (DD-38) | MERGED | 2026-10-31 | fix/draft-visibility-and-spelling |
| 11 | ci: GitHub Actions workflow (ADR-011, scope B) | MERGED | 2026-10-31 | chore/ci-workflow |
| 10 | feat: real batch lists, how many videos, delete template, better template form (DD-37) | MERGED | 2026-10-31 | feat/batch-lists-limit-template-delete |
| 9 | feat: preview progress, batch controls, queue-depth fix, local autostart | MERGED | 2026-10-31 | feat/preview-progress |
| 8 | docs: wrap-up of M2 local, ADR-012 correction, G8 plan | MERGED | 2026-10-30 | docs/ceo/wrapup-2026-10-30 |
| 7 | feat: smaller see-through AI bubble (DD-36) | MERGED | 2026-10-30 | feat/label-bubble-style |
| 6 | test: remove the redundant red adapter test set | MERGED | 2026-10-30 | fix/remove-red-g3-tests |
| 5 | feat: local real AI on the Mac (pilot), label bubble, name gap | MERGED | 2026-10-30 | feat/m2-local-real-ai |
| 4 | fix: tell the user when the background worker is not running | CLOSED (not merged; change is in #5) | - | fix/worker-health |
| 3 | docs: ADR-011 and plan for GitHub Actions CI (scope B) | MERGED | 2026-10-28 | chore/ci-github-actions |
| 2 | Spike/m2 mac feasibility | MERGED | 2026-10-28 | spike/m2-mac-feasibility |
| 1 | Fix/upload feedback | MERGED | 2026-10-27 | fix/upload-feedback |

Count: 18 PRs listed; 16 merged, 1 open, 1 closed. **2026-11-16:** 23 PRs; 19 merged, 3 open (#19, #22, #23), 1 closed.

## 2. Decisions

Source: `docs/agents/ceo/DELEGATED-DECISIONS.md`. Forty decisions, DD-1 to DD-40. Summaries are shortened from the file; the choice is kept.

| # | Date | Summary (choice) |
|---|------|------------------|
| DD-1 | 2026-10-19 | Placeholder product name "VidGen Studio" and original logo |
| DD-2 | 2026-10-19 | Use the existing Node v26.12.0 for the dashboard, no install |
| DD-3 | 2026-10-19 | M2 model stack (provisional): faster-whisper, IndicXlit, Chatterbox, MuseTalk, Demucs |
| DD-4 | 2026-10-19 | Accept the T11 contracts and add an on-disk folder collision check |
| DD-5 | 2026-10-19 | Run tester and backend-dev in parallel in strictly separate folders |
| DD-6 | 2026-10-19 | Render order: TTS, lip sync, encode, check, publish |
| DD-7 | 2026-10-19 | Pause after the name: config setting in M1, per-template in M2 |
| DD-8 | 2026-10-19 | Preview mapping kept in a JSON column in M1 (no migration 0002) |
| DD-9 | 2026-10-19 | Redact query strings in access logs (search stays GET) |
| DD-10 | 2026-10-19 | Fix the infrastructure import in render_row now (injected factories, guard test) |
| DD-11 | 2026-10-19 | Split two oversized files before gate 3; byte-range to M3; cookie replay to M3 hardening |
| DD-12 | 2026-10-19 | Merge gate 3 (M1 complete) with `--no-ff` |
| DD-13 | 2026-10-19 | M3 start: frontend-dev scaffolds test tooling (F1a) before the tester writes tests (F1) |
| DD-14 | 2026-10-19 | Approve @types/react, @types/react-dom, @types/node as pinned devDependencies |
| DD-15 | 2026-10-19 | Move to Tailwind 4 to remove seven dev-only advisories |
| DD-16 | 2026-10-19 | Scoped `fs.allow` in the Vitest config; remove the node_modules symlink |
| DD-17 | 2026-10-19 | M3 API gaps: `POST /batches/inspect-sheet` and a failure_code filter; thumbnail as placeholder |
| DD-18 | 2026-10-19 | Add a per-row retry endpoint |
| DD-19 | 2026-10-19 | Add template video endpoint with HTTP Range; test glue moves to tests/ |
| DD-20 | 2026-10-19 | Per-session throwaway test databases |
| DD-21 | 2026-10-19 | Serve the API under the `/api` prefix |
| DD-22 | 2026-10-19 | Fix the M3 defects before the gate (confirm slot, chip contrast, bar hatch) |
| DD-23 | 2026-10-20 | Confirm slot on the Templates card; also offered in wizard step 3 |
| DD-24 | 2026-10-20 | Polish before the M3 gate; progress semantics logged, not blocking |
| DD-25 | 2026-10-20 | Merge the M3 gate with `--no-ff` |
| DD-26 | 2026-10-28 | Merge the dev migration prompt (dev_up.sh asks y/N) |
| DD-27 | 2026-10-28 | Push to a private GitHub repository (main and three branches) |
| DD-28 | 2026-10-28 | CI scope B (full); CD deferred |
| DD-29 | 2026-10-28 | Worker heartbeat in Redis, status route and dashboard banner |
| DD-30 | 2026-10-28 | Local Metal GPU for real AI on the Mac (optional extra, AI_MODE switch) |
| DD-31 | 2026-10-28 | Pilot-only weights (Demucs, face-parse-bisent, S3FD/FAN) on the Mac only |
| DD-32 | 2026-10-28 | AI label: small bottom-right bubble by default (band kept as option) |
| DD-33 | 2026-10-30 | Keep the bubble; render timing variants; Admin picks by ear |
| DD-34 | 2026-10-30 | Real extra gap after the name: `name_gap_s` = 0.25 s |
| DD-35 | 2026-10-30 | Delete the 11 redundant red adapter test files (approved by Admin) |
| DD-36 | 2026-10-30 | Smaller see-through AI bubble (design B: 48 px, 12 px margin) |
| DD-37 | 2026-10-31 | Dashboard: real lists, "how many videos", delete template, new template form |
| DD-38 | 2026-10-31 | Drafts visible and resumable; confirmed spelling survives a new preview |
| DD-39 | 2026-10-31 | Spoken suffix after the name (global, default जी); mid-video lip sync slot |
| DD-40 | 2026-10-31 | Several name slots per template (up to 5 slots, migration 0002) |

## 3. Branches

Classification of all 35 non-main branch names (local, with origin copies where they exist). "Merged (ancestor)" means `git branch --merged origin/main` lists it. "Squash-merged" means the branch name matches a merged PR in section 1 but the branch is not an ancestor of main (a squash merge does not show as merged). Worktree = checked out in a git worktree.

| Branch | Where | Status | PR |
|--------|-------|--------|----|
| chore/ci-github-actions | local + origin | Squash-merged | #3 |
| chore/ci-workflow | local + origin | Squash-merged | #11 |
| chore/guard-grants-and-worktrees | local + origin | NOT merged (open). **2026-11-16: squash-merged** | #18 |
| claude/exciting-cannon-t53afd | local (worktree `.worktrees/readme`) + origin | PRs #15 and #16 squash-merged; later commits NOT merged (7 local commits, 6 with no match in main; 3 on origin, 2 unmatched). **2026-11-16: its later commits are all inside #20 (merged)** | #15, #16, #20 |
| docs/ceo/m1-plan | local | Merged (ancestor) | - |
| docs/ceo/m3-wrapup | local | Merged (ancestor) | - |
| docs/ceo/status-report-2026-11-13 | local (this session) | NOT merged (new, this report) | none |
| docs/ceo/wrapup-2026-10-30 | local + origin | Squash-merged | #8 |
| docs/ci-workflow-draft | local | NOT merged (2 commits, 1 unmatched). **2026-11-16: its `docs/patches/ci.yml` is identical to main's `.github/workflows/ci.yml`; safe to delete** | no PR |
| feat/backend/installer | local (worktree) | NOT merged (21 commits, 18 unmatched). **2026-11-16: contained in #20 (merged) except 2 HTML-only commits that are not needed** | #20 |
| feat/backend/m1-skeleton | local | Merged (ancestor) | - |
| feat/batch-lists-limit-template-delete | local + origin | Squash-merged | #10 |
| feat/dev-migration-prompt | local | Merged (ancestor; DD-26) | - |
| feat/frontend/dashboard-image | local (worktree) | NOT merged (16 commits, 14 unmatched). **2026-11-16: contained in #20 (merged)** | #20 |
| feat/label-bubble-style | local + origin | Squash-merged | #7 |
| feat/m1-api | local | Merged (ancestor; gate 3, DD-12) | - |
| feat/m1-domain | local | Merged (ancestor) | - |
| feat/m1-ingest | local | Merged (ancestor) | - |
| feat/m2-local-real-ai | local + origin | Squash-merged | #5 |
| feat/m2-mac-first | local | NOT merged (4 commits, 4 unmatched); the licence audit it produced is captured in the ADR-012 correction, so nothing else needs rescuing. **2026-11-16 correction: a line-by-line check found 85 doc lines only on this branch (the approved Mac-first M2 plan, the ADR-010 G1 audit section, DD-30/DD-31). They are rescued in PR #22; the branch is safe to delete once #22 is merged** | #22 |
| feat/m3-dashboard | local | Merged (ancestor; DD-25) | - |
| feat/multi-slot | local + origin | Squash-merged | #17 |
| feat/preview-progress | local + origin | Squash-merged | #9 |
| feat/spoken-suffix-marketing-demo | local + origin | Squash-merged | #14 |
| feat/tester/cloud-setup | local (worktree) | NOT merged (20 commits, 17 unmatched). **2026-11-16: squash-merged as #20** | #20 |
| feat/tester/m1-tree | local | Merged (ancestor) | - |
| fix/draft-visibility-and-spelling | local + origin | Squash-merged | #12 |
| fix/queue-depth | local | NOT merged by ancestry; 4 commits with no matching patch in main; the queue-depth fix is inside PR #9 (squash-merged), so this branch is safe to delete | no PR (title of #9 mentions a queue-depth fix) |
| fix/remove-red-g3-tests | local + origin | Squash-merged | #6 |
| fix/resume-from-counts | local + origin | Squash-merged | #13 |
| fix/upload-feedback | local + origin | Merged (ancestor) | #1 |
| fix/w4-dashboard-progress-consistency | local | Merged (ancestor) | - |
| fix/worker-health | local + origin | PR closed, not merged; change contained in #5 (Admin's note) | #4 (closed) |
| spike/m2-mac-feasibility | local + origin | Squash-merged | #2 |
| worktree-agent-abe939d72a80997ab | local | Merged (ancestor; 0 commits outside main) | - |

Count: 35 branch names classified. 26 are merged (ancestor or squash). 9 have unmerged commits or an open PR: chore/guard-grants-and-worktrees, claude/exciting-cannon-t53afd, docs/ci-workflow-draft, feat/backend/installer, feat/frontend/dashboard-image, feat/m2-mac-first, feat/tester/cloud-setup, fix/queue-depth, and this session's new branch. Deleting any of them needs the Admin's yes (backlog B17).

**2026-11-16:** of those 9, #18 and #20 are merged, `docs/ci-workflow-draft` and `fix/queue-depth` are safe to delete (content in main), `feat/m2-mac-first` waits for #22, and this report's branch is #19. New branches since then: `feat/backend/mode-gate` (contained in #20), `docs/ceo/task-log-cleanup` (#21, merged), `docs/ceo/m2-docs-rescue` (#22), `feat/tester/c5-demo-only` and `feat/backend/c5-demo-only` (#23), and `docs/ceo/status-report-refresh` (the refresh of this report, pushed to #19's branch).

## 4. Plans and ADRs

Plans in `docs/plans/` (`PLAN-TEMPLATE.md` is a template, not a plan):

| Plan | Status line |
|------|-------------|
| ci-github-actions.md | Approved by the Admin (scope B), 2026-10-28 |
| dashboard-lists-limit-template-delete.md | Approved by the Admin, 2026-10-31 (DD-37) |
| docker-and-cloud-setup.md | DRAFT, waiting for Admin approval (2026-11-12) |
| draft-visibility-and-spelling.md | Approved by the Admin, 2026-10-31 (DD-38) |
| g8-licence-gate.md | Draft, waiting for Admin approval; nothing built |
| m1-batch-pipeline.md | Approved (Admin, 2026-10-18) |
| m2-local-real-ai.md | No Status line; the text says the Admin approved local Metal GPU on 2026-10-28 |
| m2-mac-spike.md | Running under delegated authority (2026-10-20); throwaway code, not product code |
| m2-real-ai.md | Draft (2026-10-19); implementation blocked on a GPU that needs the Admin |
| m3-dashboard.md | Approved (Admin, 2026-10-19) |
| multi-name-slots.md | Approved by the Admin, 2026-10-31 (DD-40) |
| spoken-suffix-and-mid-slot.md | Approved by the Admin, 2026-10-31 (DD-39) |

ADRs in `docs/decisions/` (`ADR-000-template.md` is the template):

| ADR | Status line |
|-----|-------------|
| ADR-001 python-311-and-uv | Accepted (Admin, 2026-10-18) |
| ADR-002 job-queue-dramatiq | Accepted (Admin, 2026-10-18) |
| ADR-003 database-postgres | Accepted (Admin, 2026-10-18) |
| ADR-004 video-engine-ffmpeg | Accepted (Admin, 2026-10-18) |
| ADR-005 pii-encryption | Accepted (Admin, 2026-10-18) |
| ADR-006 admin-auth | Accepted (Admin, 2026-10-18) |
| ADR-007 sheet-parsing | Accepted (Admin, 2026-10-18) |
| ADR-008 m1-architecture-ports-and-fakes | Accepted (Admin, 2026-10-18) |
| ADR-009 frontend-stack | Accepted (Admin, 2026-10-19) |
| ADR-010 m2-ai-model-stack | Proposed (provisional); final acceptance needs the licence audit (G1) and a GPU quality spike |
| ADR-011 github-actions-ci | Accepted (Admin chose scope B, 2026-10-28) |
| ADR-012 local-ai-licences | No Status line; has a Decision (pilot use on the Admin's Mac only) and a Correction (2026-10-30) |

ADR-013 does not exist yet; backlog B3 needs it.

## 5. Architecture snapshot

- Layers under `backend/vidgen/`: `api/` (FastAPI routes, schemas, auth, ranges, uploads, `container.py` wiring), `services/` (batch flow, rendering, templates, manifest, audit), `domain/` (pure rules: status, codes, validation, naming, timing, retry, slot matching; no I/O), `infrastructure/` (adapters). Layering rule: services import no infrastructure.
- Ports: `backend/vidgen/ports/interfaces.py` Protocols: SpeechToText, Transliterator, VoiceCloner, LipSyncer, TextDetector, TextRenderer, LabelRenderer, VideoProbe, VideoEncoder, QualityChecker, Storage, SheetReader, Cipher, TemplateRepository, AuditRepository, UnitOfWork, Clock, WorkerHeartbeat.
- Local AI adapters in `backend/vidgen/infrastructure/local_ai/`: stt, transliterate, tts, lipsync, musetalk_support, name_slot, compositing, fidelity, guard, offline, loaders, factory, errors, `_common`. Used only when `VIDGEN_AI_MODE=local`; the fake adapters are the default.
- Worker: Dramatiq actors and runner in `backend/vidgen/worker/` (`actors.py`, `runner.py`, `periodic.py`, `warm_up.py`), queue adapter in `infrastructure/queue/`, render pipeline in `services/render_row.py` (ADR-002). Renders never run inside a web request.
- Postgres: SQLAlchemy models and repositories in `infrastructure/db/`; Alembic config `backend/alembic.ini`; migrations `backend/migrations/versions/0001_initial.py`, `0002_template_extra_slots.py`. Real database `vidgen` at 0002 (section 7).
- Redis: job queue, worker heartbeat (TTL), and saved state written to disk; configured in `backend/vidgen/settings.py`, used in `api/container.py`, `api/routes_system.py`, `worker/runner.py`.
- Dashboard: `frontend/` (React, TypeScript, Vite, Tailwind 4, Vitest, Playwright; ADR-009). Pages: Login, Overview, Wizard, Batch detail, Templates, History, Security, plus a placeholder page.
- CI: `.github/workflows/ci.yml` with three jobs: `python` (line 20), `frontend` (line 103), `e2e` (line 140). Triggered on push and pull request.

## 6. What was built (by milestone)

- M1 batch pipeline (gate 3, DD-12): sheet ingest, validation, encrypted PII, template slot and consent, FFmpeg splice with crossfades, AI label, manifest, Dramatiq worker with retries, API, audit log.
- M3 dashboard: Overview, wizard (upload, map columns, slot and preview, output and start), batch detail, templates, history, security, per-row retry, template video with HTTP Range, API under /api.
- M2 local real AI on the Admin's Mac (pilot): faster-whisper, Qwen3-4B spelling pre-fill, Chatterbox voice, MuseTalk lip sync with only a mouth oval replaced (face and beard kept), confirm-spelling step, AI mode badge, stuck-queue sweep, Redis saves to disk, optional local-ai install group with uv.lock, autostart script and login-item file (docs/autostart), worker health heartbeat and banner.
- Label and timing: small see-through AI bubble (DD-32, DD-36), 0.25 s gap after the name (DD-34), spoken suffix after the name `जी` (DD-39).
- Name slots: lip sync starting at the slot for a name in the middle of the video (DD-39), several name slots per template with up to 5 slots, per-slot lip sync and encode passes, migration 0002 (DD-40).
- Dashboard additions (DD-37, DD-38): real Running, Completed and Failed lists, drafts under Running with Continue setup, resume a draft, choose how many videos to generate (all, 5, 10, 15, custom; rows beyond the limit become SKIPPED with code NOT_SELECTED), delete a template (refused while a batch uses it), a new template form with a drop zone, confirmed spelling survives a new preview.
- Process and quality: GitHub Actions CI (python, frontend, e2e), licence audit (ADR-012 with correction), G8 plan, docs and logs, decision log DD-1 to DD-40.

## 7. Quality numbers at the last check (2026-11-13)

- Backend unit and integration (test_worker.py run alone, with the dev worker stopped): 2647 passed, 1 skipped, 0 failed.
- Dashboard Vitest: 600 of 600.
- End to end on a throwaway real stack: 22 passed, 3 skipped.
- CI on the last merged PRs: python, frontend and e2e green.
- ruff and ruff format clean.
- mypy --strict: 8 errors, all in backend/vidgen/infrastructure/local_ai/loaders.py, only when the optional local-ai packages are installed (CI installs without them).
- Real runs on the Admin's Mac: single-slot mid-video render (13.07 s from a 12.82 s template, name plus the honorific in the middle, mouth changes inside the slot, one AI bubble); two-slot render (18.57 s from 18.07 s, the name twice, later words shifted by the gaps, one AI bubble, peak 8.4 GB).
- Beard texture kept in the first-name template clip 0.79 against a target of 0.85 (accepted by the Admin after viewing).
- Database: real database `vidgen` is at migration 0002; a backup of the data before the Admin's reset is in .dev/backups/ and the old media in .dev/media-* (both git-ignored).

## 8. NOT DONE (backlog for the next phase, in priority order)

**P1 (before any production use)**

| ID | Item | Why it is not done | Needs | Owner | Size |
|----|------|--------------------|-------|-------|------|
| B1 | G8 licence gate: replace or clear the Demucs, face-parse-bisent and S3FD/FAN weights (plan docs/plans/g8-licence-gate.md, ADR-012 correction) | waiting for the Admin's approval of the plan; candidates (MediaPipe, a clearly licensed separation model or none) are unverified | Admin approves the plan | backend-dev + CEO | large |
| B2 | Per-row spoken names: the confirmed spelling covers the preview row only and the automatic spelling is right about 45-55 % of the time | design limit of the pilot | Admin adds a Devanagari `Spoken name` column to the sheets, or a better transliterator | Admin / backend-dev | medium |
| B3 | Privacy decision for cloud rendering: Modal would send names, voices and faces off the Mac, against rule C5 (voter data stays on our servers) | needs an Admin decision recorded in ADR-013. **2026-11-16: decided (C5): Modal mode is for demo and learning data only, never real voter data. Recorded in ADR-013 (6a), the README mode table, and the installer's Modal step, which needs an explicit "yes"; PR #23 (open). T4's dashboard confirmation must reuse the same wording** | Admin | CEO | small |

**P2 (product completeness)**

| ID | Item | Why it is not done | Needs | Owner | Size |
|----|------|--------------------|-------|-------|------|
| B4 | Docker app stack, terminal installer (scripts/setup.py) and Modal cloud mode (plan docs/plans/docker-and-cloud-setup.md, tasks T1-T6 and spike P2-S) | **2026-11-16:** Stage 1 (Docker app stack, installer, README modes) is merged as #20; Gap-1 (installer offers only modes the backend accepts) is in #20; C5 is in #23. Still open: T4 Modal adapters (they must implement `LipSyncer.sync(video, audio, out, start_s, key_from)`), held for spike P2-S (speech-to-text and voice cloning only, demo data, licence option (c)); and Gap 2 (local AI with the Docker app plus a native worker, not tested end to end). | Admin: spike credit cap and "go"; Modal account | CEO + backend-dev + tester | large |
| B5 | Music bed under the name slot and the gap: the voice-only clip replaces the template audio, so the slot and the 0.25 s gap are silent | the app has no separation step (Demucs weights are unclear, see B1) | decision on a licensed separation model or filling the gap with room tone | backend-dev | medium |
| B6 | Automatic detection of every occurrence of the word to replace (today the first slot is detected and extra slots are added by hand) | out of scope of DD-40 | none | backend-dev + frontend-dev | medium |
| B7 | Per-template spoken suffix (today one global setting VIDGEN_SPOKEN_SUFFIX) | would need a migration | Admin approval of a migration | backend-dev | small |
| B8 | Per-template measured pause after the name (DD-7) | would need a migration | Admin approval of a migration | backend-dev | small |
| B9 | Session cookie replay after logout until expiry (V3, found in M1 verification) | needs a revocation table (migration) | Admin approval of a migration | backend-dev | medium |
| B10 | Mouth tuning for new templates: the mouth oval and colour blend were tuned on one template; the lip colour looks slightly lighter in the output | not tested on other faces | a second real template to test with | backend-dev | medium |

**P3 (hygiene)**

| ID | Item | Why it is not done | Needs | Owner | Size |
|----|------|--------------------|-------|-------|------|
| B11 | Add VIDGEN_SPOKEN_SUFFIX to .env.example | .env.example is outside every agent's folder | Admin (or a folder grant) | CEO | tiny |
| B12 | A mypy override for the optional local-ai libraries (8 errors in loaders.py when they are installed) | follow-up | none | backend-dev | small |
| B13 | tests/integration/worker/test_worker.py hangs while the dev worker runs (it shares the Redis queue) | tests assume a stopped dev worker | a marker or a separate queue name in the test | tester | small |
| B14 | prettier --check does not cover tests/frontend (the e2e spec differs at HEAD) | config only covers frontend/ | none | frontend-dev | small |
| B15 | The slot editor does not refuse a negative start for an extra slot locally (the server does) | no message was specified | none | frontend-dev | tiny |
| B16 | Check the log line `error fetching models/sd-vae` during labelling in the local smoke run | run finished, probably an offline fallback | none | backend-dev | small |
| B17 | Delete old branches (see the branch table in section 3): merged ones are safe; DELETING NEEDS THE ADMIN'S YES; also consider deleting the REMOTE branch feat/m2-local-real-ai because its history contains one sample-sheet row id that never reached main (main was squash-merged). **2026-11-16: see the updated note under the branch table; `feat/m2-mac-first` only after #22** | Admin approval | Admin | CEO | small |
| B18 | Leftover test databases from killed pytest runs (names ending _test, for example vidgen_55e3f615_test, vidgen_63e1f22e_test, vidgen_76ce4e2b_test) and the stash and untracked files in the Admin's checkout (docs/pr-worker-health.md, docs/patches/local-ai-deps-fix.patch, docs/html/pr-worker-health.html, .worktrees/). **2026-11-16: full list of the 16 leftovers (no open connections, about 8 MB each): vidgen_12ba5b90_test, vidgen_13443f2b_test, vidgen_55e3f615_test, vidgen_63e1f22e_test, vidgen_818aab8e_test, vidgen_9052763e_test, vidgen_92fc2a4a_test, vidgen_95246324_test, vidgen_c462cd53_test, vidgen_d940db43_test, vidgen_fda9fdb5_test, vidgen_mig_3ac40085_test, vidgen_mig_cf5cff62_test, vidgen_mig_f5658f31_test, vidgen_selftest, vidgen_selftest2. Keep vidgen, vidgen_demo, and vidgen_test and vidgen_migration_test (protected by tests/integration/conftest.py). The Admin drops them.** | deletions need the Admin | Admin | Admin | tiny |
| B19 | GitHub: turn on branch protection for main (require python, frontend, e2e); merge PR #18 (guard change by the Admin) | Admin's GitHub setting | Admin | Admin | tiny |
| B20 | Paste docs/agents/ceo/CLAUDE-md-proposal.md into CLAUDE.md if wanted (agents cannot edit CLAUDE.md) | rule §3.8 | Admin | Admin | tiny |

## 9. Known issues, risks and limits

- Quality: voice is cloned from the template speaker or the built-in Hindi voice; speech-to-text garbles Hindi words so slot times rest on silence detection; the lip sync may shift face colour slightly; two encode passes for two slots cost a little quality (CRF 18); first local render after a restart is slow (model compile); measured memory: 5-8 GB resident in the smoke runs and up to 20 GB for the worker in the dashboard (another session's measurement), so keep the Mac free; the 25 fps lip sync is resampled to 60 fps.
- Licences: three weights are pilot-only (DD-31); do not use the outputs outside the Admin's Mac.
- Privacy: sample data and real ids must never be committed; main contains two example id formats in the requirements docs from the start (both values withheld from this report); the app logs no names or ids; the confirmed spoken name is stored encrypted.
- Process: a PR's head on GitHub can lag behind the branch tip (PR #12 was merged without its last commits; always compare `gh pr view N --json headRefOid` with `git rev-parse origin/<branch>` before merging); Haiku agents once ran `rm -rf` on an empty pattern (nothing was deleted) so every brief now forbids rm; the usage limit was hit once (weekly), so large parallel work can stall; the project guard blocks agents outside their folders (installer and Docker files are now granted in PR #18); worktrees live under .worktrees/ and the guard normalises their paths.

## 10. How to resume (commands, settings, files)

```bash
git checkout main && git pull
scripts/dev_up.sh                 # starts API :8000, worker, dashboard :5173; asks y/N before migrations; reads .env
scripts/dev_down.sh
.venv/bin/pytest tests/unit tests/integration -q --ignore=tests/integration/worker/test_worker.py
.venv/bin/ruff check backend tests
.venv/bin/mypy --strict backend/vidgen
cd frontend && npx vitest run && npm run typecheck && npm run lint && npm run build
PYTHONPATH=. uv run python tests/frontend/e2e/run_stack.py --project=desktop   # stop the dev app first: it needs ports 8000 and 5173
```

Settings:

| Name | Meaning | Default |
|------|---------|---------|
| VIDGEN_AI_MODE | fake or local (local needs the weights) | fake |
| VIDGEN_LOCAL_AI_WEIGHTS_DIR | where the local weights are read from | backend/spikes/m2_mac/work/local_ai_weights |
| VIDGEN_SPOKEN_SUFFIX | spoken suffix after the name (empty switches it off) | जी |
| VIDGEN_NAME_GAP_S | extra gap after the name, seconds | 0.25 |
| VIDGEN_LABEL_STYLE | AI label style: bubble or band | bubble |
| VIDGEN_PAUSE_SECONDS | pause after the name, seconds | 0.5 |
| VIDGEN_CROSSFADE_MS | crossfade length, milliseconds (allowed 20-50) | 30 |

Files:

- Plans: `docs/plans/`; decisions: `docs/decisions/` and `docs/agents/ceo/DELEGATED-DECISIONS.md`; task log: `docs/agents/ceo/TASK-LOG.md`; test trees: `docs/test-tree/`.
- Generated site: `docs/html/index.html` (regenerate with `python scripts/build_docs.py`).
- Demo templates and sheets: `backend/spikes/m2_mac/work/marketing_demo/` (git-ignored; script `backend/spikes/m2_mac/make_marketing_template.py`, flag `--two-names`).
- Smoke renders: `backend/scripts/local_ai_smoke.py --template PATH --slot START END [--slot START END] --sheet CSV --rows N --out-name NAME`.
- Screenshots: `media/review/ui/`.

Working method: tests first (tester red, developer green, verify); Haiku agents with exact briefs; the CEO verifies every result (re-run tests, read the diff); branch per task; PR; wait for CI green AND check the PR head equals the branch tip; squash-merge by the Admin or on the Admin's yes; never merge or delete or migrate without the Admin's yes.

## 11. Decisions waiting for the Admin

1. Approve or change the G8 plan.
2. Approve the four items of the Docker and Modal plan (plan, task assignment with the folder grants, the optional `modal` extra, ADR-013 including the privacy choice).
3. Merge PR #18.
4. Say yes to branch deletions (list in section 3).
5. Decide how to handle the music bed (B5).
6. Provide a second real template for tuning (B10).
7. Turn on branch protection on GitHub.
8. Decide whether real voter data may ever go to a cloud worker.

**2026-11-16 status:** item 2 approved (plus licence option (c) for the spike); item 3 done (#18 merged); item 8 decided (C5: never; demo and learning data only, PR #23). New: the spike credit cap and "go"; merge #22, #23 and this PR; delete the branches that are safe (section 3 note); drop the 16 test databases (B18).

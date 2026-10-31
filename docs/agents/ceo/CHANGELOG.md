# CEO agent — Changelog

Newest first. One entry per task.

## 2026-10-31 — PR #9 merged; DD-37 started
- PR #9 (e4b0cee): preview progress, batch controls, queue-depth fix, local autostart files. Database emptied at the Admin's request (backup in .dev/backups, old media moved to .dev/media-*).
- DD-37: four dashboard changes planned and started (see docs/plans/dashboard-lists-limit-template-delete.md).

## 2026-10-30 — M2 local real AI merged (PRs #5, #6, #7)
- PR #5 (bf14a93): local real AI on the Admin's Mac (pilot): faster-whisper, Qwen3-4B spelling pre-fill, Chatterbox voice, MuseTalk lip sync with only a mouth oval replaced, confirm-spelling step and mode badge, stuck-queue sweep, Redis saves to disk, optional local-ai install group with uv.lock, worker-health fix (PR #4 closed as contained).
- DD-32/36: AI label is a small see-through bubble at the bottom-right (48 px at 1080, white ring), band kept as an option. DD-34: 0.25 s real gap after the name (video 0.25 s longer than the template). DD-33: pause setting has no effect when the name fits the slot.
- PR #6 (bde91b3): removed the redundant red adapter test set (DD-35). PR #7 (c3b3055): the see-through bubble.
- Tests on main: 2174 → 2192 passed, 2 skipped (unit + integration, test_worker.py run alone with the dev worker stopped).
- Open: Admin tries local mode from the dashboard; G8 production licence gate (plan docs/plans/g8-licence-gate.md, waiting for approval); CI workflow (ADR-011, approved scope B).

## 2026-10-27 — M2 Mac feasibility spike (branch spike/m2-mac-feasibility)
- Merged feat/dev-migration-prompt (dev_up.sh asks y/N before migrations); suite 1750 pass.
- Spike S1–S6: whisper ✅, IndicXlit ❌ (fairseq vs Py3.11), Chatterbox ✅, Demucs ✅, MuseTalk ✅ (patched landmarks), real sample ✅ (3 local videos, 158–189 s each, 16–18 GB peak). Results: backend/spikes/m2_mac/RESULTS.md.
- Open: Admin quality review of the 3 videos; AI-label band looks ~9 % of height (spec ≥10 %, spike only); G1 licence check for face-alignment + face-parse weights.

## 2026-10-19/20 — M1 complete (gate 3) and M3 dashboard merged, under delegated authority
- Gate 3 (`49f0767`): API, DB, auth, batches, worker, pipeline; 1611 → 1745 Python tests.
- M3 (`4979db0`): React/TS/Vite/Tailwind 4 dashboard; Vitest 207/207, Playwright 48/48, axe 0 serious; API now under `/api` (server wrapper); new endpoints: inspect-sheet, failure_code filter, per-row retry, template video + HTTP Range.
- Decisions DD-1…DD-25 in `DELEGATED-DECISIONS.md`; waiting for the Admin: W-1 GPU budget, W-2 real samples on GPU, W-3 drop 2 leftover test DBs, W-4 UI visual sign-off.
- Process: per-session throwaway test DBs (DD-20); `git commit --only` rule for agents sharing one index.

## 2026-10-19 — Slices A + B reviewed (T3–T8, T7b); gate 2 prepared
- Reviewed T3/T4 (domain) and T5–T8 (sheets, probe, storage, cipher, FFmpeg engine, label). Fix rounds: accented names (D9), invisible joiners twice, filter-name-coupled tests, 4 tester defects (T7b).
- Decisions recorded: D-1…D-12 (label style, M1 extension, libraqm). ADR-001 now documents the macOS libraqm setup (symlinks into /usr/local/lib; DYLD vars are stripped by SIP).
- Committed the Admin's fonts (08c247d) at the Admin's request. Visually verified the Devanagari label.
- Process lessons: commit CEO docs before handing the shared folder to an agent; explicit `git add` paths in every brief; scan for invisible/bidi characters on every review.

## 2026-10-18 — M1 discovery, plan, T1 + T2 review
- Phase 1–2 for REQ-001: requirement tree (`docs/requirements/REQ-001-requirement-tree.md`, D1–D17), ADR-001…008.
- Phase 3: plan `docs/plans/m1-batch-pipeline.md` approved, with addenda A (T1 gaps), B (test-tree open issues), C (CEO clarifications). Added the `regex` dependency (Admin approved).
- Reviewed T1 (test tree, 374 cases) and T2 (tooling + skeleton; one fix round). Recorded a guard-scope incident (formatter touched `.claude/`, reverted, verified identical).
- Known process limits: the guard blocks agent worktrees under `.claude/worktrees/`, so tasks run sequentially.

## 2026-10-18 — SETUP
- Agent created.

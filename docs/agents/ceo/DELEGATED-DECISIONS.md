# Delegated decisions (Admin offline)

**Authority granted:** 2026-10-19 by the Admin, valid until the Admin says "authority ended".
**Scope:** technical choices (prefer "Recommended"), task assignment and models (opus only after sonnet fails twice), fix rounds, worktrees, accepting tasks after CEO review (tests + ruff + mypy green), placeholder product name + logo, merging at a gate when the full suite is green, lint/types are clean, the diff is reviewed and there are no domain violations (`--no-ff`, never force-push), starting F0–F7 after gate 3 if Node.js is available.
**Still forbidden:** running migrations on `vidgen` · paid services · sending voter data or samples externally · non-commercial licences · deleting files/folders beyond normal refactoring · weakening the consent gate, AI label or encryption · editing `CLAUDE.md` / `.claude/`.

## Decisions

| # | When | What | Options | Choice | Why |
|---|------|------|---------|--------|-----|
| DD-1 | 2026-10-19 | Placeholder product name + logo (M3 F2 needs them) | "VidGen Studio" · "Samvad Studio" · "VoiceFrame" | **VidGen Studio** + `docs/design/brand/logo.svg` (emerald square, play triangle, lime sound wave, Plus Jakarta Sans wordmark) | Neutral, matches the package name `vidgen`, no political or third-party connotation; colours come from DESIGN-NOTES; original artwork (not derived from TrustVest). Admin may replace it; only 2 files change. |
| DD-3 | 2026-10-19 | M2 model stack (draft, provisional) | see ADR-010 table | faster-whisper · IndicXlit · Chatterbox-Multilingual (hi) · MuseTalk · Demucs | All MIT per official repos/cards; Hindi supported; F5-TTS-derived Hindi, XTTS-v2 and Wav2Lip excluded (non-commercial). Provisional: full sub-model audit (G1) + GPU spike (G2) before acceptance. |
| DD-4 | 2026-10-19 | Accept T11 contracts (plan D-19) + require on-disk folder collision check | accept as-is · accept + add check | **Accept + add the storage-existence check** | R6.2 says "if the folder exists → suffix, never overwrite"; checking only DB names could mix outputs with stray folders. |
| DD-5 | 2026-10-19 | Run T13 (tester, tests/ only) in parallel with T12 (backend-dev, backend/ only) in the shared folder | sequential · parallel without worktrees (guard blocks worktrees) | **Parallel, strictly disjoint folders + explicit staging** | Saves a full cycle; the domains don't overlap; the CEO's own commits use `git commit --only`. The risk is only noisy full-suite runs, so the tester verifies its tests in isolation. |
| DD-2 | 2026-10-19 | F0 (Node.js) for M3 | Install · use existing | **Use the existing Node v26.12.0** at /opt/homebrew/bin/node; no install needed | Already present; F0 counts as satisfied. If any approved npm package doesn't support Node 26, frontend-dev pins an LTS via `engines` and reports it. |

## Waiting for Admin

| # | Since | Item | Why blocked | Prepared |
|---|-------|------|-------------|----------|
| W-1 | 2026-10-19 | M2 GPU provider + budget | Paid service (forbidden under delegation) | `docs/plans/m2-real-ai.md` draft, ADR-010 provisional model stack |
| W-2 | 2026-10-19 | Using the real `samples/` on a GPU box for the M2 spike | Voter data handling decision | Plan says: our own server only, never a third party |

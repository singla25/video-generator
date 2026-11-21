# Morning report: overnight run, 2026-11-22

Plain language. Branch `integration/overnight`, one PR to `main`. **Nothing was merged into `main`.** No migration was run,
`vidgen` and `vidgen_demo` were not touched, no Modal command, token or network call was made, `.env` and `~/.modal.toml`
were not read, no file was deleted, nothing was force-pushed, `CLAUDE.md` and `.claude/` are unchanged, and no dependency
changed (the approved `modal==1.6.4` extra was already there).

## 1. Numbers on `integration/overnight` (checked by me after the last merge)
| Check | Result |
|-------|--------|
| pytest (all except e2e and the dashboard tests; worker tests included, dev stack was stopped) | **3772 passed, 2 skipped, 0 failed** (before the run: 3102 passed, 2 skipped) |
| Vitest (dashboard) | **682 / 682** in 34 files (before: 646) |
| Dashboard typecheck, lint, prettier, build | clean |
| ruff check, ruff format | clean (487 files) |
| mypy --strict backend/vidgen | clean (149 files) |
| `uv lock --check` | up to date |
| Playwright end-to-end (ports 5173 and 8000 were free) | **49 passed, 26 skipped, 0 failed** |
| Diff vs main | 105+ files, no deleted file, no change to `pyproject.toml`, `uv.lock`, migrations, `docker-compose.yml`, `.claude/` or `CLAUDE.md` |

## 2. What was built, per track (branch, tests)
| Track | Result | Branch |
|-------|--------|--------|
| **A. Better name detection (BL-6)** | Typing `Rahul` now matches the Devanagari word `राहुल` **by sound** (plain rules, no library). When nothing is close enough the dashboard shows the **3 closest words** ("Use this word"); the slot is never auto-confirmed. Whisper gets the typed name as a hint. Setting `VIDGEN_NAME_MATCH_THRESHOLD` (default 0.8). No migration: candidates are only in the response. Quality: 36 of 36 labelled name pairs match; **0 of 252** different names matched (false-positive rate 0); 100 % branch coverage of the matcher; the offline Whisper size script. | `feat/overnight/a-name-detection` |
| **B. Modal mode, no live calls** | `ai_mode="modal"` accepted; the installer offers it (demo-data confirmation and token pair still required). The Modal app `backend/modal_app/app.py` (4 remote functions, one warm GPU class, pinned image) and the shared function names, so app and client cannot drift. Hint reaches the remote call. Provider registry and chooser work in modal mode (demo-only, spend cap). Lip sync on Modal fails with a clear message (not silent). 97 new tests, all with a fake client or a stub `modal` module, sockets blocked. | `feat/overnight/b-modal-mode` |
| **C. Startup schema check (BL-8)** | Read-only check of the database revision against the newest migration, cached 5 s. When behind or empty: most API routes answer 503 `DB_NEEDS_MIGRATION`, the status route has a `schema` field, the dashboard shows a banner with the message, the worker logs an error. It never applies a migration. 82 new tests plus a static test that no runtime code runs migrations. Login protection stays on whenever tables exist (5 failures then 429 is tested). | `feat/overnight/c-schema-check` |
| **D. Docs (BL-5)** | Chooser note about the spend-cap overshoot (11 tests). `CURRENT-PLAN.md`, TASK-LOG, DD-41 to DD-51 and the docs HTML updated. **README text is in `docs/README-additions.md`** (see section 5). | `feat/overnight/d-docs` |
| **E. Local AI with the Docker app (BL-4)** | `python3 scripts/setup.py native-worker` (with `--print`, secrets hidden, refusals when not a Mac with Apple silicon or not in local mode). 39 static and configuration tests. **Models were not started.** | `feat/overnight/e-docker-local` |
| Whisper size test | Small and medium both found "Rahul" on the made-up demo template (1.4 GB vs 2.3 GB, 8.9 s vs 10.8 s on CPU). One clip only: **no default changed**. `docs/reports/WHISPER-SIZE-TEST-2026-11-22.md` | integration |

Skipped as you said: lip sync on Modal (licence), the CUDA image (G6), G8.

## 3. Decisions I took (full text in `DELEGATED-DECISIONS.md`, DD-41 to DD-51)
- DD-43 Candidates: closeness at least 0.4, at most 3. Targets with fewer than 3 sound units need an exact sound match (guard against false positives).
- DD-44 Schema gate: the reader is optional in test app builders (so about 590 older tests stayed unchanged); production always wires it. Login tolerance only when the database is empty.
- DD-45 Native worker is a subcommand of `scripts/setup.py` (stdlib only, inside the agent write grants). Its compose test uses PyYAML, which is already in the lock.
- DD-48 New failure code `LIPSYNC_UNAVAILABLE`; placeholder cost settings (cap 5.0 USD, rate 0.0006 per second) until your spike measures real cost.
- DD-49 My review found a bug the offline tests could not see: the Modal app imports the `vidgen` package but the cloud image did not contain it. Fixed test first (`add_local_python_source("vidgen")`).
- DD-47 README is outside the agent grants (guard), so the text is in docs.

## 4. What failed or is unfinished
- **README.md not updated** (guard). Text is ready in `docs/README-additions.md`.
- **Modal app never run.** It is checked against a stub only. `huggingface_hub==2.3.0` in its image comes from our lock and is **not verified on Modal**. Expect small fixes on the first deploy.
- **Native worker never started** (needs about 20 GB of RAM): only static and configuration tests.
- **Name matcher margin:** the closest different names are `Krishan` vs `Kiran` and `Karan` at **0.75**, against the 0.8 threshold. Raising the threshold is safe for spelling variants (Kishan is 0.88) but check on your own names.
- **Whisper default** is unchanged (one clip is not enough).
- Candidates are not stored: after a reload press analyse again (your decision 1).
- In modal mode the spelling pre-fill stays the fake transliterator.
- The tester agents signed some commits as Haiku, not Sonnet (cosmetic).
- Two leftover scratch items, both git-ignored: `.dev/` files in worktrees. No file was deleted by me.
- PR #26 (plan) is still open; I merged its branch into the overnight branch so the plan could be updated, so its content is in both PRs (identical).

## 5. What needs you
1. Review and merge the overnight PR (CI will run on it).
2. Paste `docs/README-additions.md` into `README.md` (agents cannot edit it).
3. Decide: Whisper default size (after more demo clips); the matcher threshold if you want it stricter than 0.8.
4. First real run of local AI with the Docker app on your Mac (about 20 GB of RAM), when you are ready.
5. G8 licence plan approval and the lip-sync-on-Modal licence decision (BL-7).
6. Move `vidgen-backup-before-0003.sql` out of the project (it is not git-ignored and holds data).
7. Migration 0003 on `vidgen_demo` is optional (only for new screenshots).

## 6. Morning checklist for the Modal spike
1. In the Modal dashboard add a **payment method** or credits to the workspace you will use (the spike failed on 2026-11-17 with "Please add a payment method to use L4 GPU functions").
2. Set that workspace's **spending limit to $5**. The app's own cap is a soft limit: the workspace limit is the hard stop.
3. **Switch the Modal profile** to that workspace. Check with `uv run --with modal modal profile current`; list and switch with `modal profile list` and `modal profile activate <name>` (check `modal profile --help` if a name differs).
4. Tell me **"resume"**. I will then (a) run the budget-guarded spike wrapper from branch `spike/p2-modal` (`run_spike.py L4 stt`, then `L4 all`, then `T4 all`), (b) deploy the new app `backend/modal_app/app.py` once the spike shows numbers, and (c) record real timings and cost, replacing the placeholder rate. Real voter data never goes to Modal (C5): demo template and made-up names only.

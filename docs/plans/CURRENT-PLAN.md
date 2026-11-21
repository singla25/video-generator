# Current plan (2026-11-22)

Plain-language status. No code changed to write this.

## 1. What we are building and why
**VidGen Studio** makes personalised campaign videos. You give it one template video and a sheet of names.
It makes one video per row, where the spoken name (for example "Krishan") is replaced by the row's name, in the
cloned voice, with the lips matching. Every video carries a small "AI" label, and the voter list is encrypted.

Two ways to run it:
- **Mac local (the main product).** All the AI runs on your Mac's GPU. Nothing leaves the Mac. Slower: a 24 GB Mac
  works but swaps heavily.
- **Cloud GPU (Modal, later).** Faster, but the data goes to a cloud service.

**The C5 privacy rule:** in cloud mode only demo data (a neutral demo template and made-up names) is allowed.
Real voter data never goes to the cloud. The installer and the app enforce this.

## 2. Done and merged
#1 upload feedback · #2 Mac feasibility spike · #3 CI docs · #5 local real AI on the Mac · #6 test cleanup ·
#7 smaller AI bubble · #8 wrap-up docs · #9 preview progress, batch controls, autostart · #10 real batch lists,
delete template · #11 GitHub Actions CI · #12 and #13 drafts and spelling · #14 spoken suffix, name mid-video ·
#15, #16 and #17 several name slots · #18 guard update · #19 status report · #20 Docker app and installer ·
#21 task-log cleanup · #22 M2 docs rescue · #23 cloud mode is demo-only (C5) · #24 render providers, chooser and
spend cap (phase a). **Open: #25** (Modal adapters, phase b).

## 3. What is left
| # | Item | Why | Needs from you | Effort | Blocked? |
|---|------|-----|----------------|--------|----------|
| 1 | Merge PR #25 | Modal adapters, tested against a fake client | Your merge | minutes | No |
| 2 | Migration 0003 | Adds provider, data class and cost columns; the app needs it | **Done on the real database `vidgen`.** Optional on `vidgen_demo`, only if you need it for new screenshots (section 5) | done | No |
| 3 | Better name detection (BL-6) | Today "Krishan" in Roman letters misses the Devanagari word in the audio, and low-confidence words count as not found | Yes/no on the plan | Medium, 1-2 days of agent work | No |
| 4 | Startup schema check (BL-8) | A clear "database needs migration" message instead of broken screens | Nothing | Small | No |
| 5 | Docs and README for the chooser and cloud mode (BL-5) | Includes the spend-cap overshoot note | Nothing | Small | No |
| 6 | Local AI with the Docker app and a native worker (BL-4) | Mac-local without hand-starting the worker | Plan approval | Medium | No |
| 7 | Licence gate for production weights (G8) | Three lip-sync weights are cleared for the pilot only, not commercial use | Approve the plan and pick a replacement | Medium to large | Needs your decision |
| 8 | Modal spike with real numbers (BL-1) | Speed and cost of the cloud path | A Modal card with a $5 workspace limit | Small | **Blocked: your card** |
| 9 | Lip sync on Modal (BL-7) | Cloud lip sync | Your licence decision: (a) allow dev-only use of the two unverified weights on your Modal account with demo data, (b) replace the weights first, or (c) cloud for speech and voice only | Medium | **Blocked: your licence decision** |

## 4. Recommended order (Mac-local complete first, Modal waits for the card)
1. Merge PR #25 (you).
2. ~~Migration 0003~~ **Done** on the real database `vidgen`. The demo database `vidgen_demo` is still at 0002 (optional).
3. **Better name detection (BL-6):** fuzzy Roman and Devanagari matching, the closest 3 candidates when nothing
   passes, the expected name as a Whisper hint, and a Whisper model-size test on demo templates.
4. Startup schema check (BL-8).
5. Docs and README (BL-5).
6. Local AI with the Docker app (BL-4).
7. Licence gate (G8), once you approve the plan; needed before any production run.
8. Waiting on you: Modal spike (card), then lip sync on Modal (licence decision), then switch cloud mode on.

## 5. What you do yourself
1. **Merge PR #25** on GitHub (checks are green).
2. ~~Migration 0003 on the real database~~ **Done:** `vidgen` is at `0003`.
3. **Optional: migration 0003 on the demo database** `vidgen_demo` (now at `0002`), only if you need it for new
   screenshots. It only adds columns, nothing is deleted.
   - Look first, changes nothing: `uv run python scripts/dev_setup.py pending`
   - Back up: `docker compose exec -T postgres pg_dump -U vidgen vidgen_demo > vidgen_demo-before-0003.sql`
   - Apply: `alembic -c backend/alembic.ini upgrade head` with `VIDGEN_DATABASE_URL` set to the demo database.
   - Check: `select version_num from alembic_version;` should say `0003`.
   - Undo, if needed: `alembic -c backend/alembic.ini downgrade 0002` (drops exactly the three new columns), or
     restore the backup.

Where things stand: `vidgen` (real) is at `0003`, `vidgen_demo` is at `0002`. A backup file
`vidgen-backup-before-0003.sql` is in the project root. It is not git-ignored and holds data: never commit it;
move it out of the project.

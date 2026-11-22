# Current plan (2026-11-22, updated after the overnight run)

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
spend cap (phase a). #25 Modal adapters (phase b). **Built overnight, waiting in one PR for your merge:** better name detection (BL-6), startup schema check (BL-8), chooser note about the spend-cap overshoot (BL-5, code part), local AI with the Docker app (BL-4, static checks), Modal mode with no live calls (BL-3). See `docs/reports/MORNING-REPORT.md`. **In [PR #49](https://github.com/singla25/video-generator/pull/49), waiting for your merge (merge commit):** BL-14 real output checks (AC8, AC9) and stale temp cleanup wired into the worker.

## 3. What is left
| # | Item | Why | Needs from you | Effort | Blocked? |
|---|------|-----|----------------|--------|----------|
| 1 | ~~Merge PR #25~~ | Modal adapters, tested against a fake client | Done (merged) | done | No |
| 2 | Migration 0003 | Adds provider, data class and cost columns; the app needs it | **Done on the real database `vidgen`.** Optional on `vidgen_demo`, only if you need it for new screenshots (section 5) | done | No |
| 3 | ~~Better name detection (BL-6)~~ | Roman name now matches the Devanagari word by sound; closest 3 words when nothing matches | **Done, in the overnight PR.** You decide the default Whisper size after more demo clips | done | No |
| 4 | ~~Startup schema check (BL-8)~~ | A clear "database needs migration" message instead of broken screens | **Done, in the overnight PR** | done | No |
| 5 | Docs and README (BL-5) | Chooser note is built; the README text is ready in `docs/README-additions.md` | **Paste it into README.md** (agents may not edit it) | 10 min | No |
| 6 | Local AI with the Docker app and a native worker (BL-4) | **Does not work yet:** template analysis runs in the API process, and the Docker image has no `local-ai` extra or weights, so the Docker API cannot analyse a template in local mode. For the first real run use `VIDGEN_AI_MODE=local scripts/dev_up.sh` (checklist updated) | Approve option A, B or C (checklist, end) only if you want the API in Docker | A: medium, C: larger | Needs your decision |
| 7 | Licence gate for production weights (G8) | Three lip-sync weights are cleared for the pilot only, not commercial use | Approve the plan and pick a replacement | Medium to large | Needs your decision |
| 8 | Modal spike with real numbers (BL-1) | **Parked (budget, Admin decision 2026-11-22).** The Modal code stays in the project behind its flag; no Modal commands, payments or cloud accounts | Nothing for now | n/a | **Parked** |
| 9 | Lip sync on Modal (BL-7) | **Parked with Modal** | Licence decision only if Modal is resumed | n/a | **Parked** |

## 4. Recommended order (Mac-local complete first, Modal waits for the card)
1. Merge PR #25 (you).
2. ~~Migration 0003~~ **Done** on the real database `vidgen`. The demo database `vidgen_demo` is still at 0002 (optional).
3. ~~Better name detection (BL-6)~~, ~~startup schema check (BL-8)~~, the chooser note, the native-worker command and the Modal
   mode code are **built and waiting in the overnight PR** (merge it, then paste `docs/README-additions.md` into the README).
4. First real run of local AI with the Docker app on the Mac (BL-4).
5. Licence gate (G8), once you approve the plan; needed before any production run.
6. **Modal is parked (budget).** Instead: a manual measurement on Kaggle's free GPU (`docs/kaggle/KAGGLE-T4-TRIAL.md`, made-up data only). When the results come back they are recorded here and we decide which cloud option, if any, still makes sense.

## Kaggle GPU trial (2026-11-22, free, no cloud cost)
On one T4 (Python 3.13, torch 2.11.0+cu130): Chatterbox load 17.9 s, warm generation 4.24 s for 3.84 s of audio, peak 3.2 GB,
float32. Whisper small: load 0.6 s, run 0.69 s, 743 MiB. Whisper medium: load 11.1 s, run 0.71 s, 1963 MiB, higher word confidence
(about 0.91 vs 0.65 on the first word). Whether both found the name is **not yet confirmed** by the Admin. MuseTalk was **not tested**.
Details and caveats: `docs/kaggle/KAGGLE-T4-TRIAL.md`.

- **Recommendation:** Whisper **medium on a GPU**, **small on the Mac**.
- **Which cloud option still makes sense:** GPU speed is not the blocker (voice about 1.1 times real time warm, speech-to-text under
  one second on a T4-class card). So if a cloud worker is ever resumed, a single T4 or L4 class GPU, pay per use, is enough for
  speech and voice. The open question is lip sync (MuseTalk), which was not measured and has the licence decision (BL-7, G8).
  Modal stays parked. The next cloud-related step costs nothing: run MuseTalk on Kaggle by hand the same way, made-up data only.
  Kaggle stays a manual measuring tool, never a render worker.

## 5. What you do yourself
1. ~~Merge PR #25~~ **Done.** Next: review and merge the overnight PR (`integration/overnight`), then PR #26 if it is still open.
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

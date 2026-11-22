# First dashboard run on the demo setup (2026-11-22)

Throwaway demo database `vidgen_demo` (migration 0003 applied by the Admin), local AI mode, started with `scripts/dev_up.sh`.
Demo template (10.5 s, 1080x1300) and 4 made-up names. Driven in a headless browser. `vidgen` was not touched. No migration was run by me.

## Numbers
| Step | Result |
|------|--------|
| Template upload and analysis | 4 s; slot found automatically at 4.52-4.90 s, source AUTO, confidence 0.80; no closest-3 buttons needed |
| First preview (cold) | **109 s** (speaking the name 21 s, lip sync 72 s, finishing 13 s) |
| Warm preview (after confirming the spelling) | **45 s** |
| Rows | 14.7 s, 16.8 s, 16.1 s, then **85.4 s** (see memory) |
| Batch of 4 | about 2 min 13 s from the first row start to the last row end |
| Worker peak memory | 7.5 GB (resident); API about 1.0 GB |
| Swap | 2.1 GB before, **15.3 GB peak**, 13.6 GB still used after; the Mac did not freeze |
| Logs | 0 errors in the API, worker and dashboard logs |
| Outputs | ZIP 10.7 MB: 4 videos + manifest.csv; each 1080x1300 H.264 + AAC, 10.77 / 10.78 / 10.77 / 11.25 s (template 10.52 s); AI label bottom-right |

The slow fourth row ran with free memory near 80 MB and swap near 15 GB: memory pressure, not a code defect.

## Finding 1: where the "जी" suffix comes from
- **Source:** a global setting, `spoken_suffix` (environment variable `VIDGEN_SPOKEN_SUFFIX`), default `जी`
  (`backend/vidgen/settings.py`, DD-39). The worker reads it (`worker/runner.py`) and every preview and row speaks
  `spoken_text(name, suffix)` (`services/render_row.py`, `services/spoken_text.py`). It is not stored per template or per row.
- **Why it exists:** the design assumed templates that read "<name> जी", where the slot replaces both words. The demo template does not say "जी".
- **Turn it off:** set `VIDGEN_SPOKEN_SUFFIX=` (empty) in the settings file used by `dev_up.sh` and restart. This is global, for every template.
- **Per template:** not possible today. It would need a new template column, which is a migration (the plan listed it as out of scope).
- **Dashboard:** it neither shows nor edits the suffix. The "Spoken name" box shows only the name, so the suffix is invisible until you hear it.
- **A name that already ends with the suffix** is not doubled ("Asha जी" stays "Asha जी").
- **Proposal (BL-12):** show "will be spoken as: <name> जी" under the spoken-name box, and decide whether a per-template switch is worth a migration.

## Finding 2: why Kabir was heard as "आबिर"
- **How the spelling is produced:** the Qwen spelling model only suggests a spoken name for the **preview row** (`services/batch_support.py`),
  and you confirm it. **Other rows get no suggestion.** A row speaks its spoken name if the sheet has a "Spoken name column"
  (`effective_spoken_name` in `domain/validation.py`); if not, the **Roman text is handed to the Hindi voice as it is**. In this run only
  the preview row (Aarav) had a spoken name; the other three rows had none (checked in the database: spoken name empty), so "Kabir Test"
  went to the voice in Roman letters. (The smoke script, by contrast, runs the spelling model for every row, which is why the earlier smoke videos sounded better.)
- **Does the override fix it?** Yes, it helps. Direct test on the demo voice, heard back by Whisper small:
  Roman `Kabir Test जी` -> "काभेर तेस्ची"; Devanagari `कबीर टेस्ट जी` -> "तबीर तेस्तजी". The Devanagari spelling is closer ("बीर" is kept);
  Whisper small is also an imperfect listener, so judge by ear.
- **How to use the override today:** add a column with the Devanagari spelling to the sheet and choose it as "Spoken name column (optional)" in step 2 of the wizard.
  There is no per-row editor in the dashboard.
- **Proposal (BL-11):** at batch start, run the spelling suggestion for every row that has no spoken name (like the smoke script does) and store it
  encrypted as the row's spoken name; optionally add a per-row editor. Test first, no migration expected (the spoken name column already exists).

## Other observations
- The dashboard offers only the batch ZIP, no per-row download (BL-9).
- The Overview cards showed "Total 2 / Completed 2 / 4" for about a second after login, then 4 / 4 (BL-10).
- The "where to render" chooser opened and showed one provider with no radio buttons (only Cancel and Approve).
- Not exercised: the closest-3 candidate buttons (the slot was found), the schema banner (the database was at 0003).

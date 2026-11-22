# Plan: spoken spelling for every row (BL-11)

**Status:** Requested by the Admin on 2026-11-22 ("suggest the spoken spelling for every row that has no spoken name, store it encrypted in the existing column, no migration, test first"). The review/edit UI is only **proposed** (section 6), not built.

## Problem
Only the preview row gets the Qwen spelling suggestion (computed in the API for the preview row). Every other row without a "Spoken name column" in the sheet sends its **Roman text** to the Hindi voice, so names are mispronounced (first dashboard run: "Kabir Test" was heard as "आबिर टेस जी").

## Design (no migration, no new dependency)
- **Where:** in the **worker**, as a separate background job, never in a web request (Qwen takes about 20 s to load).
- **When:** after a preview becomes READY, in local AI mode (a transliterator exists). Fake mode: nothing changes.
- **What:** the job pages through the batch's rows that have **no spoken name** and are still QUEUED, asks the transliterator for the Devanagari spelling (`transliterate(name, spoken_script)`), and stores it **encrypted** in the existing `batch_rows.spoken_name_enc` column through the row store. Existing spoken names (from the sheet or an earlier run) are never overwritten. The Qwen model is released at the end (and on error).
- **Rows:** a row job speaks its stored spoken name (`effective_spoken_name` already prefers it). A row that has none (job not finished, or the transliterator failed) behaves exactly as today (Roman text). Starting the batch never waits for the job.
- **Safety:** idempotent and retry-safe, pages of a fixed size, one failing row does not stop the others, names are never logged (only counts and error types), no change to consent, label or encryption rules.

## Acceptance criteria
1. In local mode, when a preview becomes READY, one spelling job is queued for the batch; in fake mode none is.
2. The job stores an encrypted spelling for every QUEUED row without a spoken name; rows that already have one are skipped and never changed; rows not QUEUED are not touched.
3. A row render after the job uses the stored spelling (and is unchanged without it).
4. The job pages, releases the model, survives a failing row, can run twice without changing results, and never logs a name.
5. No migration, no new dependency; the preview row's confirmed spelling flow is unchanged.

## Test tree (the tester expands it)
Positive: rows filled, stored encrypted, row render uses it. Negative: existing spoken names kept, non-QUEUED rows untouched, blank result skipped, fake mode no job, transliterator error for one row. Edge: empty batch, 1 row, more rows than one page, unicode and very long names, run twice, batch deleted meanwhile, concurrency with a row claim.

## Proposal only: review and edit the spellings before the batch starts (not built)
A small panel on step 3 or 4: a table "Name | Spoken spelling" (paged, searchable) that reads the stored spellings, shows rows still waiting for a spelling, and lets the Admin edit one row (saved encrypted in the same column, with the same Devanagari validation as the sheet's spoken-name column). A "Hear this name" button is out of scope. Needs: an API route to list and update row spellings (authenticated, CSRF, audit entry, names never logged) and the dashboard panel. No migration expected. Decision for the Admin: build it as BL-13?

## Risks
- Qwen load time (about 20 s) and memory next to the voice model: the job runs alone (one worker thread) and releases the model.
- Large sheets: pages and a rate-friendly loop; the job is skippable and the render never waits for it.

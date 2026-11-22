# Test tree: spoken spelling for every row (BL-11)

Plan: docs/plans/bl11-spellings-for-all-rows.md. Branch feat/spellings-all-rows. TDD red state.

## Contract (names the developer follows)

| Piece | Name |
|-------|------|
| Queue port | `JobQueue.enqueue_spellings(batch_id: UUID) -> None` (Dramatiq adapter, default queue; message kwargs `{"batch_id": "<uuid>"}` only) |
| Actor name | `SPELLING_ACTOR_NAME = "spell_rows"` in `vidgen.infrastructure.queue.dramatiq_queue` |
| Worker | `register_actors(broker, renderer, config, spelling_filler=None)`; `WorkerActors.spell_rows` is the actor, or `None` when no filler is given. Actor body: `spelling_filler.fill_missing(UUID(batch_id))` |
| Service | `vidgen.services.spelling_filler`: `PAGE_SIZE = 50`, `SpellingReport(filled, skipped, failed)` (frozen dataclass of ints), `SpellingFiller(store, transliterator, spoken_script="devanagari", page_size=PAGE_SIZE)`, `.fill_missing(batch_id) -> SpellingReport` |
| Store port | in `vidgen.ports.rows`: `MissingSpelling(row_id, row_number, name)` (frozen dataclass, name decrypted); `SpellingStore.rows_missing_spoken_name(batch_id, after: int, limit: int) -> list[MissingSpelling]` (QUEUED, no spoken name, row_number > after, ascending, batch must exist) and `SpellingStore.set_spoken_name(row_id, spoken) -> bool` (encrypts into `spoken_name_enc`; compare-and-set: only if the row is still QUEUED and has no spoken name; True when stored). Both implemented on `SqlRowStore` |
| Trigger | `BatchFlow.preview_rendered` (via `BatchService`) calls `ctx.queue.enqueue_spellings(batch_id)` after the commit when `ctx.transliterator is not None`; a queue error is caught and logged by error type, the preview stays READY. Not on `preview_failed`, not for a deleted batch |

Filler rules: pages by cursor `after = last row_number of the page` (blank results stay missing, so the cursor must move on); blank/None result = `skipped`; a lost compare-and-set = `skipped`; an exception from transliterate or set for one row = `failed` plus a log record with the error type only; `release()` is called in a `finally` (the transliterator may lack it: call only if present); no name or spelling in any log record; a store error that is not per-row propagates after release.

## Tree and test ids

Feature: Spelling job
- Scenario: fill a batch (tests/unit/services/test_spelling_filler.py, SP-*)
  - Positive: P1 all rows filled; P2 call arguments; P3 page size 50; P4 release once; P5 second run no-op
  - Negative: N1 sheet name kept; N2 non-QUEUED untouched (5 statuses); N3 blank/None skipped (4); N4 one failing row; N5 release after all fail; N6 release when store breaks; N7 store error per row; N8 concurrent spoken name kept; N9 concurrent claim; N10 deleted/unknown batch; N11 other batch
  - Edge: E1 empty; E2 one row; E3 pages 3/4/5/7 rows at page size 3; E4 no endless loop on blanks; E5 unicode/RTL/emoji/200 chars; E6 long spelling; E7 rerun after partial failure; E8 no name in logs; E9 error type logged
- Scenario: store on Postgres (tests/integration/db/test_row_store_spellings.py, SP-DB-*)
  - Positive: P1 decrypted names in order; P2 encrypted at rest (raw column has no plaintext); P3 leaves list after set; P4 cursor and limit
  - Negative: N1 no overwrite; N2 sheet names not listed; N3 non-QUEUED not listed nor written; N4 claim between read and write; N5 deleted batch; N6 other batch
  - Edge: E1 unicode/long round trip; E2 set twice
- Scenario: render uses the spelling (tests/integration/worker/test_spellings_end_to_end.py, SP-W-*)
  - Positive: P1 filled rows synthesized in Devanagari; P2 failed row speaks Roman; P3 no job, unchanged; P4 encrypted column
  - Negative: N1 sheet name wins; N2 PROCESSING/COMPLETED untouched
  - Edge: E1 pages and second run; E2 batch deleted during the run
- Scenario: trigger (tests/integration/worker/test_spelling_job_queued.py, SP-J-*)
  - Positive: P1 one job per READY preview in local mode
  - Negative: N1 fake mode none; N2 failed preview none; N3 request_preview alone none; N4 queue down, preview stays READY
  - Edge: E1 deleted batch; E2 regenerate queues again
- Scenario: queue adapter and actor (tests/unit/infra/test_dramatiq_spellings.py, SP-Q*)
  - Q1 message actor and kwargs; Q2 coexists with other messages; Q3 actor runs filler; Q4 no actor without filler; Q5 actor registered by name

Doubles: tests/fixtures/spelling_fakes.py (FakeTransliterator, InMemorySpellingStore); `FakeJobQueue.spellings` and `.fail_spellings` in tests/fixtures/doubles.py.

AC map: AC1 SP-J-*; AC2 SP-*, SP-DB-*, SP-W-N*; AC3 SP-W-P1..P3; AC4 SP-P3..P5, SP-N4..N6, SP-E8; AC5 no migration (no schema test needed; SP-DB-P2 uses the existing column).

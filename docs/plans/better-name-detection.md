# Plan — Better name detection in the template (BL-6)

**Status:** APPROVED by the Admin on 2026-11-22 (overnight run, DD-41). Decisions: 1 candidates only in the response
(no migration); 2 plain sound rules (no new library); 3 closeness 0.8 as an adjustable setting; 4 download Whisper
small and medium weights into the git-ignored weights folder, not large-v3.
**Starts after:** PR #25 is merged (done) and migration 0003 is done (it is, on `vidgen`). Reason: this plan adds an
optional hint argument to the speech-to-text port, and the Modal adapters in #25 implement that port too.

## Goal
When you upload a template and type the name that is spoken in it (for example "Krishan"), the app finds that word
in the audio far more often. Today it must match exactly, and it often misses. When it still cannot find it, it
shows the closest 3 words so you can pick one instead of marking the time by hand.

## Why it fails today (from the code)
- `TemplateService.analyse` (`services/templates.py`) calls `select_target_word` (`domain/slot_match.py`).
- That function compares the typed name and each heard word as exact text (after case and punctuation clean-up).
- The speech-to-text adapter is told the language is Hindi, so the audio comes back in Devanagari ("कृष्ण"), but
  you type the name in Roman letters ("Krishan"). Those never match. Different Roman spellings ("Krishan",
  "Krishn", "Kishan") do not match each other either.
- A word under the confidence limit (`stt_confidence_threshold`, default 0.6) counts as "not found", with no clue
  why. The result is `SLOT_NOT_FOUND` and you have to mark the time by hand.

## What we will build (plain language)
1. **Sound-alike matching across scripts.** Both the typed name and every heard word are turned into a simple
   "sound skeleton" (consonants and long vowels, with the usual Hindi/English spelling differences smoothed out:
   v/w, sh/s, ph/f, double letters, matras, anusvara, nukta). Words are compared by how close the skeletons are,
   from 0 to 1. No new library: plain Python rules we can test.
2. **Closest 3 candidates.** If no word is close enough, the analysis result lists the 3 closest heard words with
   their time, their closeness and the speech-to-text confidence, including words below the confidence limit. The
   dashboard shows them as buttons: "Use this word". Picking one only sets the slot; you still confirm it, as today.
3. **Whisper hint.** The expected name is passed to Whisper as a hint (its `hotwords` / initial prompt option, in
   Devanagari and as typed), so it is more likely to write the name down.
4. **Model size test.** A script compares Whisper model sizes on the demo templates (found or not, time, memory)
   and prints a table. You pick the default. No change of default without your decision.

## Rules that do not change
- A found slot is never confirmed automatically (`slot_confirmed` stays false). You always confirm. The content
  lock and consent gate are untouched.
- Local AI mode stays offline at run time. Real voter data is not used in tests: only made-up words.

## Acceptance criteria
1. AC1 The typed name "Krishan" matches a heard "कृष्ण", "किशन" and "krishan" (and a labelled list of at least 20
   made-up name pairs, in both scripts, matches at 90 % or better). Unrelated words do not match.
2. AC2 A match needs closeness at or above a setting (`name_match_threshold`, default 0.8, range 0 to 1) and
   confidence at or above `stt_confidence_threshold`. Both are settings, no magic numbers.
3. AC3 When nothing passes, the result lists up to 3 closest words, best first, each with time, closeness and
   confidence. Words below the confidence limit may appear there but are never chosen automatically.
4. AC4 An empty transcript, one word, or silence gives a clear "not found" with an empty list. No crash.
5. AC5 The dashboard shows the candidates; picking one sets the slot, and the slot still needs your confirmation.
6. AC6 The expected name is passed to the speech-to-text adapter as an optional hint; with no hint, behaviour is the
   same as today. Fake and Modal adapters accept the new argument.
7. AC7 The model-size script runs offline on the demo templates and prints one table. It changes no setting.
8. AC8 Existing behaviour is kept: an exact match still works, and a typed name with a single character or only
   punctuation is refused clearly, not matched loosely.

## Requirement tree
```
Better name detection
├── Functional
│   ├── F1 Sound-skeleton for Roman and Devanagari text
│   ├── F2 Closeness score and accept rule (closeness + confidence)
│   ├── F3 Closest 3 candidates in the analysis result and the API
│   ├── F4 Whisper hint (optional argument on the speech-to-text port)
│   ├── F5 Dashboard: candidate buttons in the slot editor
│   └── F6 Model-size comparison script
├── Non-functional
│   ├── Speed: matching 2000 heard words takes well under 100 ms
│   ├── No new Python dependency, no network at run time
│   └── Deterministic: same input, same answer (no AI model in the matcher)
├── Constraints
│   ├── Slot is always confirmed by a person
│   ├── Port change must keep fake, local and Modal adapters working
│   └── Typed and heard text may be unicode (Devanagari, nukta, chandrabindu, zero-width joiners)
├── Out of scope
│   ├── Several different names in one template (multi-name slots already exist)
│   ├── Learning from your corrections
│   └── Detecting the name without you typing it
└── Open questions: none (4 decisions with defaults below, please confirm or change)
```

## Decisions for you (recommended answer first)
1. **Keep candidates only in the response, not in the database (Recommended).** No migration. After a page reload
   you press "Analyse again" (a few seconds on CPU). The alternative stores them in a new `slot_candidates`
   column, which is migration 0004 and needs your separate approval.
2. **Plain rules for the sound skeleton (Recommended).** Alternatives: a transliteration library (new dependency)
   or the local Qwen model (heavy, not in CI).
3. **Closeness default 0.8**, tuned on the made-up list in AC1. Lower finds more but guesses more.
4. **Model-size test downloads Whisper weights** for the sizes we do not have yet (MIT licence, a few GB). The
   script uses only a folder you name and never downloads by itself. Say yes to each size, or run it with the
   sizes already on the Mac.

## Test case tree (outline; the tester expands it in `docs/test-tree/better-name-detection.md`)
- **Skeleton and closeness:** positive (Krishan / कृष्ण / किशन / Krishn), negative (Krishan vs Ramesh),
  edge (empty, one letter, only punctuation, mixed script, zero-width joiner, uppercase, long name, repeated
  letters, numbers).
- **Accept rule:** positive (close and confident), negative (close but low confidence is a candidate, not a match;
  confident but far is nothing), edge (exactly at both thresholds, ties on closeness, same word twice).
- **Candidates:** positive (top 3 best first), negative (fewer than 3 words, none), edge (identical scores,
  duplicate words, a hundred words).
- **Service and API:** analysis returns match, candidates or not found; slot stays unconfirmed; picking a candidate
  sets the slot; unauthenticated and wrong template are refused.
- **Whisper hint:** passed when given, absent when not; fake, local and Modal adapters accept it.
- **Dashboard:** candidate buttons show, picking sets the slot, empty list shows the old message, errors show.
- **Script:** prints a table, runs without network, refuses a missing folder.

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| N1 | Expand test tree; write failing tests for matcher, service, API, hint, script | tester | Owns tests and the tree | PR #25 merged | haiku | feat/tester/name-detection | Tests fail for the right reasons |
| N2 | Frontend failing tests for candidate buttons | tester | Owns frontend tests | N1 | haiku | same | Fail for the right reasons |
| N3 | Matcher: sound skeleton, closeness, accept rule, candidates (pure domain code) | backend-dev | Owns `backend/`, pure Python | N1 | sonnet (the sound rules are the hard part) | feat/backend/name-detection | N1 matcher tests green |
| N4 | Wire into `analyse`, API field, setting, hint on the port and all adapters | backend-dev | Same domain | N3 | haiku | same | Service, API, hint tests green |
| N5 | Model-size comparison script (offline) | backend-dev | Same domain | N3 | haiku | same | Script test green |
| N6 | Candidate buttons in the slot editor | frontend-dev | Owns `frontend/` | N2, N4 | haiku | feat/frontend/name-detection | N2 tests green |
| N7 | Verify, coverage, run the size test with you | tester | Independent check | N3-N6 | haiku | n/a | Full suite green |
| N8 | Review, docs, PR | CEO | Review and records | N7 | n/a | n/a | You approve merge |

Order (TDD): N1 and N2 (red) → N3 → N4 and N5 → N6 → N7 → CEO review → you approve the merge.

## Risks
| Risk | Mitigation |
|------|-----------|
| Loose matching picks the wrong word | Slot is always confirmed by a person; candidates show closeness; threshold is a setting |
| Short names match too much | Extra-strict rule for names under 3 sounds (AC8) |
| Port change breaks the Modal adapters | Plan starts after #25 merges; tests cover all three adapters |
| Made-up test names do not reflect real speech | Size test runs on your demo templates; you check the table |
| Whisper hint changes results for other words | Hint is optional and tested with and without it |

## Migrations / dependencies (need separate approval)
- Migration: **none** with decision 1 as recommended. Option "store candidates" would be 0004.
- New Python dependency: **none**.
- Model weights: only if you say yes to a new Whisper size for the size test.

## Admin approval
- [x] Plan approved, decisions 1 to 4 confirmed (Admin, 2026-11-22)
- [x] Task assignment approved (overnight delegated authority, DD-41)
- [ ] Merge approved (the Admin merges the overnight PR; nothing goes to main alone)

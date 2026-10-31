# Plan — Spoken suffix after the name and mid-video name slot

**Status:** Approved by the Admin on 2026-10-31 (DD-39)
**Decision record:** docs/agents/ceo/DELEGATED-DECISIONS.md (DD-39)
**Branch:** feat/spoken-suffix-marketing-demo

## Goal

Two requests from the Admin after trying local mode:

- **(A) Spoken suffix.** The template text reads "<name> जी" and the name slot replaces both words, but the voice says only the name. Add a spoken suffix after the name. It is set by `VIDGEN_SPOKEN_SUFFIX` (default `जी`; an empty value switches it off). A pure function `spoken_text(name, suffix)` builds the text to speak and never duplicates the suffix. It applies to batch rows and to the preview. The timing already adapts to the longer speech.
- **(B) Name in the middle of the video.** The audio splice already works for any slot. The lip sync, however, always starts at 0:00 of the video because the `LipSyncer` port has no slot argument, so a name in the middle gets mouth movement at the wrong time. Pass the slot start to the lip sync, and lip-sync only the segment that starts there.

Before (B) is built, a synthetic marketing template (two-wheeler dealer, name in the middle of the sentence) is produced so the Admin can test it.

## Requirement tree

```
Spoken suffix and mid-video slot
├── Functional
│   ├── R1  spoken_text(name, suffix) returns the name followed by the suffix, once
│   ├── R2  VIDGEN_SPOKEN_SUFFIX sets the suffix; default "जी"; empty = off
│   ├── R3  Batch rows and the preview speak spoken_text(name, suffix)
│   ├── R4  LipSyncer.sync(video, audio, out, start_s=0.0) — additive optional argument
│   ├── R5  The lip sync touches only the segment from start_s and splices it back
│   ├── R6  Face boxes cached per (template, start_s)
│   └── R7  Synthetic two-wheeler dealer template, name in the middle, built by a script
├── Non-functional
│   ├── Output keeps fps, width, height, duration and audio sync of the input video
│   ├── Coverage >= 85 % on new code; 100 % on core video-pipeline logic
│   └── No secrets read; outputs go to the git-ignored work folder
├── Constraints
│   ├── No migration
│   ├── No new dependency
│   ├── Tests first (TDD: tester red, backend-dev green, tester verify)
│   ├── Haiku agents with exact briefs, verified by the CEO
│   └── LipSyncer change is additive only (new optional argument)
├── Out of scope
│   ├── Per-template suffix (would need a migration)
│   ├── Changing the suffix text per language or per row
│   └── Lip sync quality changes (MuseTalk model, weights)
└── Open questions (must be empty)  — none
```

## Acceptance criteria

1. `spoken_text("Ravi", "जी")` returns `Ravi जी`. With `VIDGEN_SPOKEN_SUFFIX` unset the default suffix is `जी`. With `VIDGEN_SPOKEN_SUFFIX=` (empty) `spoken_text("Ravi", "")` returns `Ravi` unchanged.
2. `spoken_text` never duplicates the suffix: `spoken_text("Ravi जी", "जी")` returns `Ravi जी`. Surrounding spaces are trimmed. A blank name raises the existing invalid-name error; a name that is only the suffix is treated as blank, so no suffix is ever spoken alone.
3. A suffix that is longer than 20 characters or contains a control character is rejected at start-up with a clear configuration error. Nothing is rendered with it.
4. Every batch row speaks `spoken_text(name, suffix)`, and the row's audio length follows the longer speech (the slot and the timing adapt). The preview speaks the same text as the batch rows for the same name and suffix.
5. `LipSyncer.sync(video, audio, out)` without `start_s` behaves exactly as today (regression test). `start_s` below 0 or beyond the video length is rejected with a typed error and no output file is written.
6. With `start_s` > 0 the lip sync changes only the frames from `start_s` onward and the output has the same fps, width, height, duration and audio stream as the input video; the audio stays in sync with the mouth movement at the slot.
7. Face boxes are cached per (template, start_s): a second render of the same template and start reuses the cached boxes and does not detect faces again.
8. The synthetic two-wheeler dealer template (name in the middle) renders end to end on the Admin's Mac with the spoken suffix, and the Admin confirms by ear and by eye that the mouth moves with the name. ruff, mypy and pytest pass; coverage meets the targets above; no migration and no new dependency are added.

## Test tree outline

See docs/test-tree/spoken-suffix-and-mid-slot.md (tester writes it in SUF-RED and MID-RED). Each scenario has positive, negative and edge cases:

- Suffix: default, empty (off), already present, extra spaces, blank name, suffix only, over-long suffix, control characters, Devanagari and mixed-script names.
- Batch and preview: same text for the same row, timing adapts to longer speech, preview and batch agree.
- Mid-slot: start_s default 0.0 (regression), start_s in the middle, start_s = 0, start_s at the end, negative start_s, start_s beyond duration, corrupt input video, fps and size preserved, audio sync preserved, face-box cache hit and miss.

## Tasks

| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| SUF-RED | Write failing tests for the spoken suffix (R1–R3, AC1–AC4) | tester | Owns tests/ and the test tree; writes red tests first | DD-39 approval | haiku | No (sequential on the feature branch) | Tests exist and fail only on missing code |
| SUF-GREEN | Implement `VIDGEN_SPOKEN_SUFFIX`, `spoken_text`, batch and preview wiring | backend-dev | Owns backend/ (settings, services, TTS input) | SUF-RED | haiku | No | SUF-RED tests pass; ruff and mypy clean; no test edited |
| DEMO-TEMPLATE | Script `backend/spikes/m2_mac/make_marketing_template.py` that builds a two-wheeler dealer template with the name in the middle; outputs in the git-ignored work folder | backend-dev | Owns backend/spikes and the local render tooling | SUF-GREEN | haiku | No | Script runs; the template and a sample row are in the work folder; Admin can open them |
| MID-RED | Write failing tests for `start_s` (R4–R6, AC5–AC7) | tester | Owns tests/ and the test tree | DEMO-TEMPLATE | haiku | No | Tests exist and fail only on missing code |
| MID-GREEN | Add `start_s` to the `LipSyncer` port and the adapter; segment splice; face-box cache per (template, start_s) | backend-dev | Owns the infrastructure adapter and the port | MID-RED | haiku | No | MID-RED tests pass; regression with start_s = 0.0 identical; ruff and mypy clean |
| VERIFY | Run full suites on the branch; real mid-slot render of the demo template on the Admin's Mac; the Admin listens and watches | CEO | Only the CEO verifies and reports to the Admin | MID-GREEN | haiku (CEO checks) | No | Suites green; Admin accepts the render (AC8) |
| PR | Open the PR to main, CI green, CEO diff review | CEO | Merging needs CEO review and Admin approval | VERIFY | haiku | No | PR ready; Admin decides merge |

## Order (TDD)

tester (SUF-RED) → backend-dev (SUF-GREEN) → backend-dev (DEMO-TEMPLATE) → tester (MID-RED) → backend-dev (MID-GREEN) → CEO (VERIFY, Admin listens) → PR → Admin approves merge

## Risks

1. **The MuseTalk segment splice must keep fps, size and audio sync.** Splicing a lip-synced segment back into the full-length video can change frame count, frame rate or audio offset. Mitigation: the tests check fps, width, height, duration and audio stream against the input (AC6); the CEO checks a real render before the PR.
2. **A Lekha-voiced demo template sounds synthetic.** The test voice is not a natural voice for a dealer advert. Mitigation: this is accepted for a test template only; it is not used for any delivered video.
3. **The suffix default changes every new render.** After this change, each new render speaks the name followed by `जी`, which the Admin did not hear before. Undo: set `VIDGEN_SPOKEN_SUFFIX=` (empty) in the local environment, which restores today's speech.

## Migrations / dependencies (need separate approval)

- Migrations: none. A per-template suffix would need one and is out of scope (DD-39).
- Dependencies: none added.
- Port change: `LipSyncer.sync` gains an optional `start_s` argument (additive; existing callers and fakes keep working).

## Admin approval
- [x] Plan approved (2026-10-31, DD-39)
- [x] Task assignment approved (2026-10-31, DD-39; all tasks haiku)
- [ ] Merge approved

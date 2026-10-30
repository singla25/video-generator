# Plan — G8 licence gate for production weights

**Status:** Draft, waiting for Admin approval. Nothing is built until the Admin approves. No migration.

## Goal
No model weights with unclear or non-commercial licences are needed for a production run.

## Background
- ADR-012 (Correction, 2026-10-30) lists three weights that are not cleared for commercial use:
  - Demucs htdemucs weights: the author states the licence is unclear.
  - face-parse-bisent weights: trained on CelebAMask-HQ, which is for non-commercial research and educational purposes only.
  - S3FD / FAN (face-alignment) weights: no licence stated.
- The app does not use Demucs yet.
- face-parse-bisent and S3FD/FAN are used inside the MuseTalk lip sync path.
- DD-31: these weights are accepted for pilot use on the Admin's Mac only.

## Acceptance criteria
1. Every weight the production path loads has a licence line in ADR-012 with its source URL and the date checked.
2. A test fails if a weight outside the allow-list is loaded in production mode.
3. Quality check on the sample row is not worse than the pilot: beard texture retention >= 0.85 on the lip-synced clip, and no visible seam.
4. Pilot mode (`AI_MODE=local` on the Admin's Mac) still works.
5. ADR-012 is updated to match the result.

## Requirement tree
```
G8 licence gate
├── Functional
│   ├── F1 Production path loads only allow-listed weights
│   └── F2 Pilot path keeps current behaviour
├── Non-functional
│   ├── Quality of lip sync not worse than pilot (beard texture >= 0.85, no seam)
│   └── Licence evidence recorded with URL and date
├── Constraints
│   ├── Nothing is built until the Admin approves
│   └── No migration
├── Out of scope
│   ├── Legal advice (this is a technical reading of project pages)
│   └── Changes to the fake AI default
└── Open questions (must be empty before build)
    └── Which replacement option the Admin chooses (see Options)
```

## Options to evaluate
All options are UNVERIFIED. Each must be checked against the official licence pages before any code is written.

- **Landmarks and face mask:** MediaPipe-based landmarks and mask. Code is believed to be Apache-2.0; the models must be checked separately.
- **Separation (Demucs):** either skip separation, or use a separation model with a clear licence. Skipping is possible because the music bed is not preserved under the name slot today anyway.
- **Written licences:** obtain written licences from the rights holders for the current weights.

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| G8-1 | Licence research for the options above (no code) | CEO + Haiku | Documentation research only | Admin approval | haiku | No | Licence line with URL and date per candidate in ADR-012 |
| G8-2 | Red tests for the allow-list (production mode fails on a non-listed weight) | tester | Owns `tests/`; writes tests first | G8-1 | haiku | No | Tests exist and fail on current code |
| G8-3 | Swap the adapters to allow-listed weights | backend-dev | Owns `backend/` adapters | G8-2 | haiku | No | G8-2 tests green; pilot tests still green |
| G8-4 | Verify on the Mac with the sample row | tester | Verification and quality check | G8-3 | haiku | No | Quality criteria 3 and 4 met, recorded in ADR-012 |

## Order (TDD)
tester (red, G8-2) → backend-dev (green, G8-3) → tester (verify, G8-4) → CEO review → Admin approves merge

## Risks
1. **Quality drop:** the replacement may be worse on beard texture or seams. Mitigation: quality check on the sample row (criterion 3) before any merge.
2. **Licence research is incomplete:** a candidate may also have unclear terms. Mitigation: every candidate is UNVERIFIED until its official page is read and recorded with URL and date.
3. **Pilot breaks:** changing the adapters may affect the Mac pilot. Mitigation: criterion 4 and the existing pilot tests.

## Migrations / dependencies (need separate approval)
- No database migration.
- Any new dependency (for example MediaPipe) needs separate Admin approval before it is added.

## Admin approval
- [ ] Plan approved
- [ ] Task assignment approved
- [ ] Merge approved

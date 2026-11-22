# Plan — BL-14 Output checks (OUTPUT_CHECK_FAILED made real)

## Goal
Today `backend/vidgen/worker/runner.py` builds `FakeQualityChecker`, so `OUTPUT_CHECK_FAILED` can never happen. Plan AC8 (duration, resolution, fps, video codec family and audio format match the template; duration = template + name delta within `duration_tolerance_ms` = 50) and AC9 (loudness of the spliced slot within `loudness_tolerance_lu` = 1.0 LU) are therefore not enforced. This plan adds a real checker and wires it into the worker. It also wires the existing `remove_stale_temp` helper into a periodic worker task.

## Acceptance criteria
1. In `local` and `modal` AI modes the worker uses the real checker; only `fake` mode uses the fake.
2. An output whose duration differs from template duration + name delta by more than `duration_tolerance_ms` fails with `OUTPUT_CHECK_FAILED`.
3. An output with a different resolution, fps, video codec family or audio format than the template fails.
4. For each slot, the loudness of the output region differs from the template region by more than `loudness_tolerance_lu` fails; silent audio fails.
5. Zero-length, unreadable or corrupt output returns issues. The checker never raises.
6. Issue codes come from a domain enum. Messages never contain names or paths.
7. `render_row` raises `DomainError(OUTPUT_CHECK_FAILED)` with a fixed message that contains no names.
8. Stale temp files are cleaned by a periodic worker task (`temp_cleanup_interval_seconds` default 3600, `temp_max_age_seconds` default 3600). Errors are logged, never fatal.
9. Existing tests still pass. `ruff` and `mypy --strict` are clean.

## Requirement tree
```
BL-14
├── Functional
│   ├── R1 Real QualityChecker (ffprobe + ebur128) for AC8 and AC9
│   ├── R2 Expectation built from slots and plans (pure domain function)
│   ├── R3 Worker wiring by ai_mode
│   ├── R4 render_row passes the expectation and raises OUTPUT_CHECK_FAILED
│   └── R5 Periodic temp cleanup in the worker
├── Non-functional
│   ├── No names or paths in messages or logs
│   └── Checker never raises; cost: one extra ffmpeg pass
├── Constraints
│   ├── Port change is additive and backward compatible
│   └── Reuse loudness.parse_integrated_lufs and domain timing.duration_within_tolerance
├── Out of scope
│   └── No migration, no new dependency, helpers and settings are not deleted
└── Open questions (none)
```

## Design
1. **Port change (NEEDS CEO/ADMIN REVIEW, gate 7; additive only).** `QualityChecker.check(template, output, expected: OutputExpectation | None = None) -> list[str]`. Existing callers and the fake keep working because `expected` defaults to `None`.
   - `OutputExpectation` is a frozen dataclass in `ports/models.py`. It holds `delta_s` (sum of `plan.duration_delta_s`) and per-slot `SlotRegion(template=(start, end), output=(start, end))`.
   - A pure domain function builds it from slots and plans. The output region of slot i starts at `start_i` plus the sum of deltas of earlier slots. Its length is slot length + `pause_absorbed` + extension + gap.
2. **New `infrastructure/ffmpeg/quality.py`: `OutputQualityChecker`.** Uses ffprobe and ebur128 and returns codes from a domain enum. Unreadable or zero-length output returns issues. It never raises and never prints names or paths.
3. **Worker wiring.** `build_quality_checker(settings)` in `worker/runner.py`: real checker for `ai_mode` local and modal, fake only for fake mode. It reads the two tolerance settings.
4. **render_row** passes the expectation. A failure raises `DomainError(OUTPUT_CHECK_FAILED)` with a fixed, name-free message.
5. **Temp cleanup.** `remove_stale_temp` runs in a `PeriodicTask` in the worker. New settings: `temp_cleanup_interval_seconds` (3600) and `temp_max_age_seconds` (3600).

## Test tree outline
See docs/test-tree/bl14-output-checks.md (tester writes it).
```
Output checks
├── Single slot
│   ├── Positive: matching output passes (duration, fps, codec, audio, loudness within 1 LU)
│   ├── Negative: wrong duration; wrong fps; wrong codec; silent audio; loudness 2 LU off
│   └── Edge: duration exactly at tolerance; zero-length output; corrupt file; missing file
├── Multi-slot
│   ├── Positive: regions shifted by earlier deltas pass
│   └── Negative/Edge: only the second slot is off; negative delta
├── Wiring
│   ├── Positive: local/modal get the real checker, fake gets the fake
│   └── Negative: failure raises OUTPUT_CHECK_FAILED, message has no names
└── Temp cleanup
    ├── Positive: old files removed, new kept
    └── Edge: cleanup error is logged, worker keeps running
```

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| BL14-T1 | Test tree and red tests | tester | Owns tests/ | Plan approved | sonnet | Yes (this one) | Tests fail for the right reasons |
| BL14-T2 | Port, domain function, checker, wiring, cleanup task | backend-dev | Owns backend/ | BL14-T1 | sonnet | Yes (this one) | Tests green, ruff and mypy clean |
| BL14-T3 | Verify, coverage, edge cases | tester | Independent check | BL14-T2 | sonnet | Yes (this one) | Full suite green, coverage >= 85 % (100 % on pipeline logic) |

## Order (TDD)
tester (red) → backend-dev (green + refactor) → tester (verify) → CEO review → Admin approves merge

## Risks
- False failures on real templates because of codec padding. Mitigation: tolerances are settings; test with real demo templates before merge.
- Extra ffmpeg pass costs time per row. Mitigation: ebur128 only on slot regions; measure once.
- Port change touches a shared interface. Mitigation: additive default, flagged for review.

## Migrations / dependencies (need separate approval)
None. No migration, no new dependency.

## Admin approval
- [ ] Plan approved
- [ ] Port change reviewed (gate 7)
- [ ] Task assignment approved
- [ ] Merge approved

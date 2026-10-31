# Test tree: preview progress, slow warning and fake-AI note

Feature: Wizard preview progress (T-PROG-FE)
Tests: tests/frontend/unit/preview-progress.test.tsx
Case IDs: TT-PP-<P|N|E><n>.

## Contract (frontend developer implements this)

| Item | Rule |
|------|------|
| API | `batch.preview.stage`: `"preparing" \| "voice" \| "lipsync" \| "finishing" \| null` (optional). `/system/status` gives `ai_mode`: `"fake" \| "local"`; absent on older servers. |
| Progress list | While `preview.status` is PENDING: `<ol role="list" aria-label="Preview progress">`, four items with exact texts "Preparing", "Speaking the name", "Matching the lips", "Finishing". Earlier steps `data-state="done"`; current has `aria-current="step"` and `data-state="current"`; later `data-state="todo"`. Null or missing stage = "Preparing" current. Hidden for READY, FAILED, NONE, STALE, no preview. |
| Local note | `ai_mode` local and PENDING: `role="note"` "First run after a restart is slow, a few minutes. The AI models are loading." |
| Slow warning | PENDING for 30 s (fake, unchanged) or 180 s (local): "Preview is taking longer than expected." and a Retry button. |
| Fake note | `ai_mode` fake: `role="note"` "Fake AI is on: the video will have a beep instead of the name." inside the Preview panel, any preview state. Not in local mode, not while the status call loads or fails. |

Unknown stage values are not in the contract. The tests only require no crash, the four steps, and at most one current step.

```
Feature: Wizard preview progress, slow warning and fake-AI note
├── Scenario: Preview is pending, progress list (P2, P3)
│   ├── ✅ P1 ordered list "Preview progress" with the four exact texts
│   ├── ✅ P2 stage preparing/voice/lipsync/finishing -> done, current, todo states
│   ├── ✅ P3 polling moves the current step; READY removes the list
│   ├── ❌ N1 no list for READY (even with a stage), FAILED, STALE, NONE, no preview
│   └── ⚠️ E1 null or missing stage -> Preparing current; E2 unknown or empty stage -> no crash;
│          E3 same list in fake, local and older-server modes
├── Scenario: Local mode first-run note (P4, N2-N4, E4, E9)
│   ├── ✅ P4 local + PENDING shows the note as role="note"
│   ├── ❌ N2 fake + PENDING no note; N3 local + READY/FAILED/NONE/no preview no note; N4 no ai_mode no note
│   └── ⚠️ E4 READY hides it; E9 local -> fake switch removes it
├── Scenario: Slow warning (P5-P7, N5-N7, E5-E7)
│   ├── ✅ P5 fake at 31 s shows warning + Retry (unchanged); P6 local at 180 s shows it; P7 Retry re-posts
│   ├── ❌ N5 fake at 29 s nothing; N6 local at 31 s nothing; N7 local at 179 s nothing
│   └── ⚠️ E5 READY after 181 s hides it; E6 READY at 100 s never shows it; E7 unmount clears the timer (fake 30 s, local 180 s)
├── Scenario: Fake-AI note (P8, N8-N12, E8)
│   ├── ✅ P8 fake shows the note inside the Preview panel for no-preview, NONE, PENDING, READY, FAILED, STALE
│   ├── ❌ N8 local no fake note; N9 local + PENDING no fake note; N10 no note while status loads (then shows);
│   │      N11 HTTP or network error on status -> no mode text; N12 no ai_mode -> no note
│   └── ⚠️ E8 fake -> local mid-session swaps the notes
└── Scenario: READY and status failures (E10-E12)
    ├── ✅ E10 local READY hides list, note and warning; E11 fake READY hides list, keeps fake note
    └── ⚠️ E12 failing status keeps the list (stage is mode-independent) and adds no mode-specific text
```

## Red expectations

Failing for the right reason before the feature exists: the list tests, the local note, the fake note, and the local warning at 31 s or 179 s (current code uses 30 s for every mode). Guards that pass before the feature (they pin unchanged behaviour): fake warning at 31 s and nothing at 29 s, the 180 s local warning, the absent-note checks, and the status-failure checks.

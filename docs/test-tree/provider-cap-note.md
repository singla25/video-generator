# Feature: spend-cap overshoot note in the render chooser (BL-5)

Note (role="note") with the exact Admin text, shown only if a listed (not data-class-refused) provider has a spend cap (`spend_cap_usd` not null).

- Scenario: open the chooser
  - Positive: local + capped cloud -> note (BL5-P1); cloud only -> note (P2); note not aria-hidden, inside dialog (P3)
  - Negative: local only (N1); cloud refused by data class, with or without local (N2, N3); loading (N4); load error (N5) -> no note
  - Edge: cap null -> no note (E1); cap 0 is still a cap -> note (E2); list refetch -> exactly one note (E3)

Tests: tests/frontend/unit/provider-cap-note.test.tsx

# Test tree — Render providers (phase a, backend)

Plan: `docs/plans/render-providers.md` (approved 2026-11-17: Q1 = 3 measured runs, Q2 = yes, Q3 = no
enforced by API and worker). ADR-013 amendment A1. Everything runs with FAKE providers: no Modal, no
network, no paid call. Migration 0003 is tested only on a throwaway `vidgen_mig_*_test` database.

## API contract (frontend tests rely on this; pinned by the backend tests)

Money values are JSON numbers (USD, float). Errors use the existing body `{code, message}`.

**Batch creation** `POST /batches` (multipart) gains `data_class` (`"real"` default | `"demo"`) and
`confirm_demo` (`"true"`). `demo` without `confirm_demo=true` is 422 `VALIDATION_ERROR`; any other
`data_class` value is 422.

**Batch JSON** (all batch responses) gains: `provider_id` (string | null), `data_class`
(`"real"` | `"demo"`), `spent_usd` (number, this batch's measured cost, 0 when none), `pause_reason`
(null, `"spend cap reached"` or `"provider not allowed for this data class"`; only set while PAUSED).

**List providers** `GET /batches/{id}/providers` →
```
{ "data_class": "real"|"demo", "selected_provider_id": str|null,
  "any_selectable": bool, "message": str|null,            # message set when nothing is selectable
  "providers": [ { "id", "name", "kind", "data_rule",
      "setup": {"state": "ready"|"needs_setup", "reason": str|null},
      "estimate": null | {"seconds_per_video","batch_seconds","batch_cost_usd"},
      "estimate_label": "not measured yet" | null,        # label exactly this text when estimate is null
      "spend_cap_usd": number|null, "spent_usd": number, "remaining_usd": number|null,
      "selectable": bool,
      "refusal": null | {"code": "not_ready"|"data_class"|"over_credit", "reason": str} } ] }
```
Every registered provider is listed (the UI hides `data_class` refusals and greys `not_ready`).

**Choose** `POST /batches/{id}/preview/approve` accepts an optional JSON body `{"provider_id": "<id>"}`.
Without a body the call behaves as today (batch keeps provider null = default provider). With an id the
provider is checked and stored on the batch. Refusals leave the batch unchanged:
`422 UNKNOWN_PROVIDER`, `409 PROVIDER_NOT_READY`, `409 PROVIDER_NOT_ALLOWED` (C5), `409 PROVIDER_OVER_CREDIT`.
`POST /batches/{id}/start` re-checks a stored provider (ready, data class): `409 PROVIDER_NOT_READY` /
`PROVIDER_NOT_ALLOWED`; the batch stays DRAFT and no job is queued.

**Change provider** `PUT /batches/{id}/provider` `{"provider_id"}`: only DRAFT or PAUSED
(else `409 INVALID_STATE`), same refusals as above; QUEUED rows are enqueued again on the new queue.

**Worker C5 behaviour (pinned):** a demo-only provider with a real batch (API bypassed): the row is NOT
rendered (still QUEUED, attempts 0, no TTS call), the batch goes PAUSED, outcome `DEFERRED`;
`pause_reason` = `"provider not allowed for this data class"`.
**Spend cap (pinned):** worst case of one row = `row_timeout_seconds × rate_per_second`; the worker pauses
(PAUSED, row stays QUEUED, outcome `DEFERRED`, reason `"spend cap reached"`) when `spent + worst > cap`
(equal is allowed). A completed row stores `cost_usd = render_seconds × rate_per_second`.

**Code shape pinned by tests:** `vidgen.domain.providers` (pure), `vidgen.infrastructure.provider_registry`
(TOML), `vidgen.infrastructure.queue.redis_heartbeat.RedisQueueHeartbeats`,
`vidgen.services.provider_guard.ProviderGuard` (`RowRenderer(provider_guard=...)`),
`Settings.providers_file`, `AppDeps.queue_heartbeats`, `JobQueue.enqueue_*(..., queue_name=None)` and
`depth(queue_name=None)` (queue_name passed only when the batch has a provider), `StuckRow.provider_id`
with `requeue_stuck_rows(..., provider_queues=)`. Registry TOML: `[[provider]]` tables with keys `id name kind
queue ai_mode data_rule spend_cap_usd rate_per_second|rate_per_hour requires_env`; unknown keys are refused
(so no `token`/`secret` keys).

## Tree

```
Feature: Render providers
├── Scenario: Provider record (RP-REC)            unit/domain/test_provider_records.py
│   ├── ✅ local provider valid; remote_function demo_only with cap valid; queue defaults to vidgen.<id>
│   ├── ❌ unknown kind · remote kind real_allowed · remote kind without cap · negative rate/cap · blank id
│   └── ⚠️ duplicate id · duplicate queue · empty registry · unknown provider id lookup · null id = default
├── Scenario: Registry file (RP-REG)              unit/infra/test_provider_registry_file.py
│   ├── ✅ valid TOML → providers; missing file → one provider from ai_mode + queue_name
│   ├── ❌ bad TOML · invalid entry names the entry · secret-looking or unknown key refused
│   └── ⚠️ empty file · unicode name · requires_env names only · rate_per_hour converted
├── Scenario: Estimates (RP-EST)                  unit/domain/test_provider_rules.py
│   ├── ✅ 3 runs → median seconds, cost = seconds × rate, batch totals
│   ├── ❌ < 3 runs → None ("not measured yet")
│   └── ⚠️ failed/cancelled excluded · rate 0 · even count median · exactly N
├── Scenario: Setup state (RP-SET, RP-HB)         unit/domain/test_provider_rules.py, unit/infra/test_queue_heartbeats.py
│   ├── ✅ env + live heartbeat on own queue → ready
│   ├── ❌ missing env → reason names variable · no heartbeat → "worker not running"
│   └── ⚠️ env present but empty · heartbeat expires · two workers one queue · per-queue keys · redis down
├── Scenario: Selectable / chooser rules (RP-SEL) unit/domain/test_provider_rules.py
│   ├── ✅ ready + fits data class + within credit
│   ├── ❌ not ready · demo_only for real · estimate > remaining credit (each with a code)
│   └── ⚠️ estimate == remaining · unmeasured + capped selectable (Q2) · uncapped never over credit
├── Scenario: Chooser API (RP-API)                integration/api/test_providers_chooser.py, test_batch_data_class.py
│   ├── ✅ list shape · choose at approval stores provider · batch JSON fields · legacy approve without body
│   ├── ❌ unknown · not ready · demo_only for real · over credit → 4xx, batch unchanged
│   └── ⚠️ nothing ready → message · provider not ready at start → 409, no jobs · demo needs confirmation
├── Scenario: Routing (RP-RTE)                    unit/infra/test_dramatiq_routing.py, unit/services/test_requeue_routing.py, integration/api/test_providers_routing.py
│   ├── ✅ start, retry-failed, per-row retry, requeue → chosen queue only; depth per queue
│   ├── ❌ other queue receives nothing; unrouted batch passes no queue name (legacy shape)
│   └── ⚠️ change provider while paused moves rows · running refused · old batch → default
├── Scenario: Worker C5 and spend cap (RP-WRK)    integration/worker/test_provider_guard.py
│   ├── ✅ cost_usd stored · spent accumulates · pause before the row that passes the cap
│   ├── ❌ demo_only + real batch bypassing API → not rendered, PAUSED, reason shown
│   └── ⚠️ cap exactly reached allowed · cap raised → renders again · no guard = legacy behaviour
│       (concurrent rows near the cap: needs real workers, deferred to P5 verify)
└── Scenario: Migration 0003 (RP-MIG)             integration/db/test_migration_0003_providers.py
    ├── ✅ upgrade adds provider_id (nullable), data_class (default real), cost_usd (nullable); downgrade removes
    ├── ❌ at 0002 the columns do not exist
    └── ⚠️ old batch survives with data_class real · round trip no drift · throwaway DB only
```

Acceptance mapping: AC1 REG/REC · AC2 SET/HB · AC3 EST · AC4 API list · AC5 SEL/API over credit ·
AC6 RTE · AC7 WRK cap · AC8 API + WRK C5 · AC9 e2e with two workers (P5) · AC10 whole suite.

## UI section (phase P3, Vitest + MSW, fake API)

Files: `tests/frontend/unit/data-class-step.test.tsx`, `provider-chooser.test.tsx`, `spend-cap-pause.test.tsx`;
fixtures `tests/frontend/mocks/providers.ts` (plus a default MSW handler for the providers list).
Each file's header comment pins the UI contract (roles, names, test ids).

```
Feature: Render providers (UI)
├── Scenario: Data class at upload (RP-UI-DC)
│   ├── ✅ "Real data" default · demo + confirmation sends data_class=demo, confirm_demo=true
│   ├── ❌ demo without the confirmation box → Next disabled, reason announced
│   └── ⚠️ back to Real data forgets the confirmation · arrow keys move between radios
├── Scenario: Chooser at "Approve preview" (RP-UI-CH)
│   ├── ✅ side by side: name, kind, time, cost, remaining credit · "not measured yet" still pickable · confirm sends {provider_id}
│   ├── ❌ needs-setup and over-credit greyed with reason, cannot be picked · data_class refusals hidden ·
│   │      409 PROVIDER_NOT_READY / NOT_ALLOWED / OVER_CREDIT and 422 UNKNOWN_PROVIDER → message, dialog stays open
│   └── ⚠️ single selectable provider is preselected (E1) · unicode name · nothing selectable → API message,
│          approval blocked · focus in dialog, Escape/Cancel send nothing · full keyboard path
└── Scenario: Spend-cap pause on the batch page (RP-UI-CAP)
    ├── ✅ "spend cap reached" + "$4.95 of $5.00" · data-class pause reason
    ├── ❌ paused by hand (no reason) or running → no reason box
    └── ⚠️ reason announced with role=status
```
Existing wizard test TT-UI-AC5-P8 now goes through the chooser (updated; red until the dialog exists).

## A11y: keyboard-accessible scroll regions (axe scrollable-region-focusable, PR 24)
- TT-A11Y-SCROLL-P1 ScrollRegion renders role=region, tabindex=0, aria-label, overflow-x-auto
- TT-A11Y-SCROLL-P2 DraftsSection, BatchListTable, RowsTable, HistoryPage, StepMap use ScrollRegion with labels "Drafts table", "Batches table", "Rows table", "History table", "Sheet preview table"
- TT-A11Y-SCROLL-E1 extra className kept; no raw overflow-x-auto left outside ScrollRegion.tsx
- Test: tests/frontend/unit/scroll-region.test.tsx. Dev creates frontend/src/components/ScrollRegion.tsx (label, children, className?).

## Chooser preselection (Admin decision, PR 24 e2e TT-UI-E2E-P2c)
The chooser always opens; exactly one selectable listed provider is preselected, otherwise nothing.
- RP-UI-CH-PS1 two selectable: none checked, approve disabled
- RP-UI-CH-PS2 one selectable + not-ready others: the selectable is checked, approve enabled
- RP-UI-CH-PS3 zero selectable: none checked, disabled
- RP-UI-CH-PS4/PS5 data_class-hidden providers do not count
- RP-UI-CH-PS6 Cancel after preselection sends nothing; PS8 preselected id is what is approved
- RP-UI-CH-PS7 a reload never overrides the user's own choice
- RP-UI-CH-E1 (changed) single selectable preselected; RP-UI-CH-N1 now uses two selectable + one not-ready
- e2e TT-UI-E2E-P2c: Approve preview, dialog, default radio checked, Approve with this provider, Next enabled. No other e2e spec approves a preview.

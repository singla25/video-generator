# Plan — Pluggable render providers and the render plan chooser

**Status:** DRAFT for Admin approval · **Date:** 2026-11-17 · **Backlog item:** 2 (after the spike review, item 1)
**Decision record:** ADR-013 amendment A1 (proposed, same branch). **Starts only after** the spike review and the
Admin's approval of this plan, the ADR amendment, the task assignment and migration 0003.

## Goal
Rendering is no longer fixed to three modes. Any number of **render providers** can be registered. Each one says
what it is, where its estimates come from, what data it may receive, whether it is ready, and how much it may
spend. When the Admin approves the preview, a **chooser** shows the ready providers side by side (time, cost,
remaining credit) and the batch is rendered by the one the Admin picks, through that provider's own queue.

## What exists today (verified 2026-11-17)
- The worker already listens on one configurable queue: `settings.queue_name` (default `vidgen`), used by
  `worker/actors.py` and `DramatiqJobQueue(queue_name=...)`. A second worker started with another
  `VIDGEN_QUEUE_NAME` already serves a separate queue.
- The worker heartbeat is **one shared Redis key** (`vidgen:worker:heartbeat`, `redis_heartbeat.py`). It takes a
  `key` argument but is not per queue yet.
- `settings.ai_mode` is `Literal["fake", "local"]`; it picks the AI adapters for the whole process.
- Template speech-to-text runs **inside the API** (`routes_templates.analyse` → `services/templates.py`), not on a
  queue. Templates never pass through a provider, so C5 is safe for templates without extra work.
- Batches already have `PAUSED` and the pause/resume transitions (`domain/status.py`).
- The batch table has no provider or data-class column. Migrations 0001 and 0002 exist.

## Provider registry
Each provider is one entry in a registry file (TOML, read with the standard library `tomllib`; path from the
setting `VIDGEN_PROVIDERS_FILE`). No secrets in the file: credentials stay in environment variables, and the entry
only names which variables it needs. If the file is missing, the app behaves exactly as today: one provider built
from `ai_mode` and `queue_name`.

| Field | Meaning | Values |
|-------|---------|--------|
| `id` / `name` | stable id (also the queue suffix) and the label shown in the chooser | `local-mac`, "This Mac" |
| `kind` | how jobs reach the hardware | `local` · `remote_function` · `remote_worker` |
| `queue` | the provider's own queue name | default `vidgen.<id>` |
| `ai_mode` | adapters the provider's worker loads | `fake` · `local` · `modal` (after T4) |
| `data_rule` | C5 | `real_allowed` · `demo_only` |
| `spend_cap_usd` | most it may spend; `none` for no cap (only allowed for `local`) | e.g. `5.00` |
| `rate` | how cost is counted (for the estimate and the cap) | per GPU-second (remote function) or per hour (remote worker); `0` for local |
| `requires_env` | environment variables that must be set for "ready" | e.g. `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` |

Derived at run time, never written by hand:
- **Setup state**: `ready` when every `requires_env` is present **and** a worker heartbeat exists on the provider's
  queue (per-queue heartbeat key); otherwise `needs setup` with the reason ("worker not running",
  "MODAL_TOKEN_ID missing").
- **Estimate** (time and cost per video, and for the batch): **from measured runs only**, i.e. completed rows that
  this provider rendered in this app. Median render seconds over at least `N` measured rows (proposal `N = 3`);
  cost = seconds × rate. With fewer rows the chooser shows **"not measured yet"**. Spike numbers and design figures
  are never used as estimates.
- **Spent / remaining credit**: the sum of the measured cost of rows this provider rendered (stored per row), and
  `spend_cap − spent`.

### The three kinds
1. **local**: a worker on this machine (native or in the Docker app) with its own queue. Real data allowed. Cost 0.
2. **remote_function**: a worker on this machine whose AI adapters call remote functions (Modal, ADR-013 and T4).
   Media for the model calls leaves the machine, so it is `demo_only` (C5). Cost = measured GPU seconds × rate.
3. **remote_worker**: any machine (for example a rented GPU server) that runs the **same worker**
   (`python -m vidgen.worker`) with `VIDGEN_QUEUE_NAME` set to the provider's queue. It needs:
   - the **CUDA worker image** (plan item **G6**, m2-real-ai). Today's local adapters are tuned for Apple MPS, and
     the Docker backend image has no AI extras;
   - network access to Redis and PostgreSQL, and shared media storage. Local disk is not shared, so this needs the
     S3-compatible storage adapter (architecture rule "storage behind an interface"), plus a private network
     (VPN or tunnel), never an open port;
   - the encryption keys, because the worker decrypts names. **The keys leave our machine**, so a rented machine
     counts as `demo_only` under C5 unless the Admin decides it is "our server" (open question Q3).

## Chooser and routing
- **Where:** at preview approval (wizard step 3). The preview is rendered as today; when the Admin clicks
  "Approve preview", the chooser opens before the batch can start.
- **What it shows:** only **ready** providers whose `data_rule` fits the batch, side by side: name, kind,
  estimated time for the batch, estimated cost, remaining credit, or "not measured yet". Providers that are not
  ready are listed underneath, greyed, with their reason, and cannot be picked.
- **Data class of a batch:** the Admin declares it at upload (step 1): "real data" (default) or "demo / learning
  data", with a confirmation. `demo_only` providers are offered only for demo batches (C5).
- **Refusal:** an option whose batch estimate is **greater than its remaining credit** cannot be picked, and the
  chooser says why. "Not measured yet" with a cap: the Admin may pick it, and the cap still stops it (next point).
- **Pause at the cap:** before each row the worker checks `spent + this row's worst case` against the cap. If it
  would pass the cap, the batch moves to **PAUSED** with the reason "spend cap reached" (no row fails), and the
  dashboard shows it. Raising the cap or choosing another provider resumes it.
- **Routing:** the chosen provider id is stored on the batch. `enqueue_rows`, retry, requeue of stuck rows and
  per-row retry all use that provider's queue. One queue per provider; queue depth and heartbeat per queue.
- **Change of provider:** allowed only while the batch is paused or not started; queued rows move to the new
  queue.

## Acceptance criteria
1. **AC1 Registry:** providers load from the registry file. A missing file gives exactly today's behaviour. An
   invalid entry (unknown kind, `real_allowed` on a remote kind without an Admin override, no cap on a paid kind,
   duplicate id or queue) is refused at start with a clear error naming the entry.
2. **AC2 Setup state:** `ready` only with all `requires_env` present and a live heartbeat on the provider's queue;
   otherwise `needs setup` with a reason. Heartbeats are per queue.
3. **AC3 Estimates:** time and cost come only from this provider's measured rows (≥ N). Otherwise the API and the
   dashboard say "not measured yet". No other source is used.
4. **AC4 Chooser:** at preview approval, ready providers that fit the batch's data class are shown side by side
   with time, cost and remaining credit; not-ready ones are greyed with a reason.
5. **AC5 Refusal:** an estimate above remaining credit cannot be chosen (API refuses too, not only the UI).
6. **AC6 Routing:** every job of the batch (rows, retries, requeue) goes to the chosen provider's queue; other
   queues never receive it.
7. **AC7 Spend cap:** the batch pauses before a row would pass the cap; spent and remaining credit are shown.
8. **AC8 C5:** a `demo_only` provider can never receive a batch declared as real data (API and worker both check).
9. **AC9 Remote worker:** a worker started elsewhere with `VIDGEN_QUEUE_NAME=<queue>` makes that provider ready
   and renders its jobs (verified with a second local worker process in tests; a real rented machine needs G6).
10. **AC10 Quality:** ruff, mypy `--strict`, pytest, Vitest green; coverage of new code ≥ 85 %; no network or
    paid call in automated tests.

## Requirement tree
```
Render providers
├── Functional
│   ├── Registry file (TOML, stdlib) → Provider records; fallback = one provider from ai_mode
│   ├── Per-queue heartbeat and queue depth; setup state with reason
│   ├── Measured estimates per provider; spent / remaining credit
│   ├── Batch data class (real | demo) declared at upload
│   ├── Chooser at preview approval (API + dashboard); refusal over credit
│   ├── Routing of rows, retries and requeue by the batch's provider
│   └── Pause at spend cap
├── Non-functional: no secrets in the registry · domain rules pure (no I/O) · old batches keep working
├── Constraints: C5 (demo-only for remote kinds) · ADR-012 (lip sync only on the Mac until (a)/(b)) · G6 for
│   remote_worker · shared storage for remote_worker
├── Out of scope: the Modal adapters themselves (T4) · the CUDA image (G6) · S3 storage adapter · VPN setup ·
│   automatic provider choice
└── Open questions (must be answered before approval)
    ├── Q1 Minimum measured rows N for an estimate (proposal 3)
    ├── Q2 Should a "not measured yet" provider with a cap be choosable? (proposal yes, the cap protects)
    └── Q3 May a rented machine ever count as "our server" for real data (C5)? (proposal no: demo_only)
```

## Test tree outline (tester writes `docs/test-tree/render-providers.md` first)
```
Registry
├── Positive: valid file → providers; missing file → one provider equal to today
├── Negative: unknown kind · duplicate id/queue · paid kind without cap · remote kind with real_allowed · bad TOML
└── Edge: empty file · unicode name · env var present but empty
Setup state
├── Positive: env + heartbeat → ready
├── Negative: missing env → needs setup (reason) · no heartbeat → needs setup
└── Edge: heartbeat expires during a batch · two workers on one queue
Estimates
├── Positive: ≥ N measured rows → median time, cost = time × rate
├── Negative: < N rows → "not measured yet" · rows from another provider never counted
└── Edge: failed and cancelled rows excluded · rate 0
Chooser / API
├── Positive: lists ready providers that fit the data class, side by side
├── Negative: estimate > remaining credit → 4xx with a reason · demo_only for a real batch → 4xx · not-ready → 4xx
└── Edge: no ready provider → clear message, cannot start · provider becomes not ready between list and start
Routing
├── Positive: rows, per-row retry, retry-failed and requeue go to the chosen queue only
├── Negative: a worker on another queue never takes the job
└── Edge: change of provider while paused moves queued rows · old batches without provider use the default
Spend cap
├── Positive: batch pauses before the row that would pass the cap; reason shown
├── Negative: the worker refuses a demo_only provider for a real batch even if the API was bypassed
└── Edge: cap exactly reached · cap raised → resume · concurrent rows near the cap
```

## Tasks
| ID | Task | Agent | Why this agent | Depends on | Model | Worktree? | Done when |
|----|------|-------|----------------|------------|-------|-----------|-----------|
| P1 | Test tree + failing tests (domain, registry, API, worker routing) | tester | owns tests and test trees | plan + ADR A1 approved | sonnet | yes `feat/tester/providers` | AC1–AC9 covered pos/neg/edge |
| P2 | Domain + registry + per-queue heartbeat + estimates + migration 0003 (created, not run) + routing + cap pause | backend-dev | backend/ | P1 | sonnet | yes `feat/backend/providers` | P1 backend tests green |
| P3 | Failing UI tests for the chooser and the data-class step | tester | owns tests | P1 | sonnet | yes | UI cases red |
| P4 | Chooser at preview approval, data class at upload, pause reason | frontend-dev | frontend/ | P2, P3 | sonnet | yes `feat/frontend/providers` | P3 green |
| P5 | Verify, coverage, e2e with two local workers on two queues | tester | verify step | P2, P4 | sonnet | no | AC10 |
| P6 | Docs: README chooser section, registry example (no secrets) | CEO | owns docs | P5 | haiku | no | backlog item 5 |

## Order (TDD)
tester (red) → backend-dev (green + refactor) → tester (UI red) → frontend-dev (green) → tester (verify) → CEO
review → Admin approves merge. Migration 0003 is **created** in P2 and **run only with the Admin's yes**.

## Risks
| # | Risk | Mitigation |
|---|------|-----------|
| R1 | Real data reaches a remote provider by mistake | data class declared at upload; API and worker both check (AC8); remote kinds demo_only by default |
| R2 | Estimates are misleading with few runs | measured runs only, N minimum, "not measured yet" otherwise |
| R3 | Spend overshoot (one row runs past the cap) | check before each row with the row's worst case; provider-side limit (for Modal: the workspace spending limit) as the hard stop |
| R4 | Remote worker exposes Redis/PostgreSQL or keys | private network only; demo_only (Q3); out of scope until G6 and S3 storage exist |
| R5 | Old batches and the requeue job break | provider column nullable, null = default provider; tests for old rows |

## Migrations / dependencies (need separate approval)
- **Migration 0003 (created in P2, run only with the Admin's yes):** `batches.provider_id` (text, nullable; null =
  default provider), `batches.data_class` (`real` | `demo`, default `real`), `batch_rows.cost_usd` (numeric,
  nullable; measured cost of the row).
- **Dependencies:** none (TOML is read with the standard library).
- **ADR:** ADR-013 amendment A1 (proposed with this plan).

## Admin approval
- [ ] Spike review done (backlog item 1)
- [ ] Open questions Q1–Q3 answered
- [ ] Plan approved
- [ ] ADR-013 amendment A1 approved
- [ ] Task assignment approved
- [ ] Migration 0003: running it approved (later, separately)
- [ ] Merge approved

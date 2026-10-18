# Dynamic Video Generator — AI Team Setup

A CEO agent (highest model) that talks to you, plus three sub-agents — backend, frontend, tester — with shared rules, a safety guard, skills and auto-generated docs. Built for **Claude Code**.

## What's inside

```
CLAUDE.md                     ← rules for ALL agents (approval gates, security, TDD, architecture, docs, tokens)
.claude/
├── agents/
│   ├── ceo.md                ← model: opus — your point of contact
│   ├── backend-dev.md        ← model: sonnet — writes only backend/
│   ├── frontend-dev.md       ← model: sonnet — writes only frontend/
│   └── tester.md             ← model: sonnet — writes only tests/
├── hooks/guard.py            ← blocks code deletion, secrets, personal data, data leaks
├── settings.json             ← permissions (deny / ask / allow) + guard hook
└── skills/
    ├── tdd-feature/          ← Red → Green → Refactor → Verify cycle
    └── test-tree/            ← positive / negative / edge case template
scripts/build_docs.py         ← turns every docs/*.md into docs/html/
docs/                         ← plans, ADRs, per-agent README + CHANGELOG, test trees, html/
```

## Setup (5 minutes)

1. Copy this folder's contents into your project root, then:
   ```bash
   git init && git add . && git commit -m "chore: agent team setup"
   ```
2. Install the tools the agents use:
   ```bash
   pip install pytest pytest-cov ruff mypy
   ```
3. Start Claude Code **as the CEO** so the main session uses the highest model:
   ```bash
   claude --agent ceo
   ```
   (or start `claude`, run `/model` → Opus, and say "Act as the ceo agent".)
4. Tell it what you want to build. It will cross-question you with MCQs, propose approaches, write a plan, and **wait for your "yes"** before anything starts.

## How a feature flows

| Step | Who | You approve? |
|------|-----|:---:|
| Listen, restate, MCQ cross-questions, requirement tree | CEO | ✅ tree |
| 2–3 approaches with pros/cons → ADR | CEO | ✅ choice |
| Plan + tasks + **why each agent** + model per task | CEO | ✅ plan |
| Assign tasks (worktrees if parallel) | CEO | ✅ assignment |
| Failing tests: positive / negative / edge | tester | — |
| Code to pass tests, then refactor | backend-dev / frontend-dev | — |
| Verify + coverage report | tester | — |
| Review diff, run checks, report | CEO | ✅ merge |
| Merge `--no-ff` into main, rebuild docs | CEO | — |

See everything at **`docs/html/index.html`**.

## Safety — what the guard blocks (tested: 25/25 cases)

- `rm -rf`, `git reset --hard`, `git clean`, force push, `branch -D`, `find -delete`, `DROP TABLE`
- Reading or writing outside the project, `~`, `/Users`, `.ssh`, `.aws`, Documents/Downloads…
- `.env`, keys, credentials (`.env.example` is allowed)
- Uploading data out (`curl -d/-F/POST`, `scp`, `nc`, `curl | sh`)
- Editing `CLAUDE.md`, `.claude/`, `.git/`
- Running migrations (`alembic upgrade` etc.) — the CEO asks you, and **you run the migration yourself**
- Sub-agents writing outside their folder — enforced when your Claude Code version passes the agent name to hooks; otherwise enforced by the agent rules and the CEO's diff review

Merges, pushes, dependency installs and file deletions always show you a permission prompt.

> The guard is a strong safety net, not a guarantee. Keep `main` protected on GitHub (require PR + passing checks), and keep regular backups/pushes so code can always be recovered.

## Changing the rules
Only you edit `CLAUDE.md` and `.claude/` (agents can't). Ask the CEO to *propose* new skills or agents; you approve and add them.

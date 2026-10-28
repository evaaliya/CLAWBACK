# Clawback

A personal AI agent that finds money you are losing (unused subscriptions, closing refund windows, unclaimed warranties), prepares the action, and does it **only after you approve**. A counter shows the money and time recovered.

All bank, mail and merchant systems are emulated. Nothing is sent to a real company.

## How a run looks

1. Upload a statement and receipts. The agent finds your subscriptions and flags the unused ones.
2. A background scan warns that a return window closes in 3 days and offers to prepare a claim.
3. The agent searches the store's current policy, drafts a claim with source links, and shows it. You press *Send*.
4. You ask to cancel a subscription. The agent reuses a skill it already learned and does it in seconds.
5. The counter shows what was recovered.

## Run it

Requirements: Python 3.12, Node 20 (for Playwright only).

```bash
cp .env.example .env     # set keys; RECORDED_MODE=true works without any keys
make install
make seed
make up                  # http://localhost:8000
```

| Command | What it does |
| --- | --- |
| `make up` | Run the backend and the web chat |
| `make recorded` | Run with cached model and search responses (offline) |
| `make seed` | Load the demo dataset from `demo/` into SQLite |
| `make demo` | Reset the database to the seeded demo state |
| `make scan` | Run the deadline scan once |
| `make test` | Unit and integration tests |
| `make e2e` | Playwright end-to-end tests in recorded mode |
| `make verify` | Everything, plus the T1–T23 report in `reports/` |

## Project documents

| File | Purpose |
| --- | --- |
| `SPEC.md` | Requirements, architecture, data model, tests T1–T23, milestones M0–M6 |
| `STATUS.md` | What works, what does not, what is not done; updated after each milestone |
| `scope.md` | In scope, out of scope, order of cutting scope |
| `AGENTS.md` | Entry point for coding agents |
| `docs/mock-portal.md` | The emulated merchant portal and outbox |
| `docs/DECISIONS.md` | Timestamped decision log |
| `docs/TOOLING.md` | Models and tools used, and why |
| `docs/CREDITS.md` | Borrowed foundations |
| `demo/` | Demo dataset; `demo/savings_plan.json` defines the $847 counter |
| `.cursor/rules/`, `.agent/skills/` | Rules and skills for coding agents |

## Project layout

```
app/        FastAPI app: api/, ingest/, deadline_watcher/, claim_writer/, skill_forge/,
            savings/, portal/, llm/, search/, ui/ (static web chat)
jobs/       scan.py (Serverless Job entrypoint)
scripts/    demo.py, verify_report.py
tests/      pytest tests and Playwright e2e tests
demo/       statement, receipts, usage, seed history, policy fixtures
docs/       process documents
reports/    verify reports (generated)
```

## Working through it

Follow milestones M0 to M6 in `SPEC.md` section 12. Each has a checklist and a "Done when" tied to tests. After each milestone: commit, add an entry to `docs/DECISIONS.md`, update `STATUS.md`.

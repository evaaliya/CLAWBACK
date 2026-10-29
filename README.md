# Clawback

A personal AI agent that finds money you are losing (unused subscriptions, closing refund windows, unclaimed warranties), prepares the action, and does it **only after you approve**. A counter shows the money and time recovered.

All bank, mail and merchant systems are emulated. Nothing is sent to a real company.

## How a run looks

1. Upload a statement and receipts. The agent finds your subscriptions and flags the unused ones.
2. A background scan warns that a return window closes in 3 days and offers to prepare a claim.
3. The agent searches the store's current policy, drafts a claim with source links, and shows it. You press *Send*.
4. You ask to cancel a subscription. The agent reuses a skill it already learned and does it in seconds.
5. The counter shows what was recovered.

## Run it (judges — local)

Requirements: Python 3.12, Node 20 (for Playwright only).

```bash
cp .env.example .env     # set keys; RECORDED_MODE=true works without any keys
make install
make seed
make recorded            # offline Golden Path — http://localhost:8000
# or: make up            # live Nebius + Tavily when keys are set
```

| Command | What it does |
| --- | --- |
| `make up` | Run the backend and the web chat |
| `make recorded` | Run with cached model and search responses (offline) |
| `make seed` | Load the demo dataset from `demo/` into SQLite |
| `make demo` | Reset the database to the seeded demo state |
| `make scan` | Run the deadline scan once (on demand) |
| `make test` | Unit and integration tests |
| `make e2e` | Playwright end-to-end tests in recorded mode |
| `make verify` | Everything, plus the T1–T23 report in `reports/` |
| `make docker-smoke` | Build `linux/amd64` image, run recorded container, health + Playwright |

## Run it (judges — Nebius Serverless Endpoint)

1. Push `main` so CI (`.github/workflows/image.yml`) builds and pushes `ghcr.io/<owner>/clawback:latest` for **linux/amd64**. Set the GHCR package visibility to **Public**.
2. Create MysteryBox secrets whose payload keys are `NEBIUS_API_KEY` and `TAVILY_API_KEY`.
3. Install and authenticate the Nebius CLI, then:

```bash
IMAGE=ghcr.io/<owner>/clawback:latest JOB_TOKEN=<optional> ./scripts/deploy_nebius.sh
```

The script uses `--auth none` so the printed URL opens in a normal browser (no token). Confirm with `curl -sf <url>/api/health`. Optional on-demand scan against that URL: `SCAN_TARGET_URL=<url> JOB_TOKEN=… ./scripts/deploy_scan_job.sh`.

**Cost / state:** the endpoint burns VM money while running — stop when idle. Container disk is not persistent; every cold start re-seeds the demo. Full flags and stop/start/delete/logs: see the deploy script comments and (if present locally) `docs/DEPLOY.md`.

## Data egress

Exactly what leaves this machine. Raw receipts and statements stay in local SQLite; models see scrubbed text only. Data sent to Nebius Token Factory is covered by Nebius's terms — this README does not claim zero retention.

| Destination | What is sent |
| --- | --- |
| Nebius Token Factory | Scrubbed receipt/statement fragments for parse; purchase facts + Tavily excerpts for claim draft/validate; portal help text for cancel planning |
| Tavily Search | Policy query from `{merchant, topic, jurisdiction}` only (`build_policy_query`) — never receipt body, names, emails, or card digits |
| Mock merchant portal / outbox | Claim body and cancel steps only after a stored user approval |
| Browser | Same-origin UI/SSE only (no third-party analytics) |

Open the **Activity** tab in the web UI for the live `agent_log` timeline and per-model token counts.

## Project documents

| File | Purpose |
| --- | --- |
| `SPEC.md` | Requirements, architecture, data model, tests T1–T34, milestones M0–M9 |
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

Follow milestones in `SPEC.md` section 12 (one at a time). Each has a checklist and a "Done when" tied to tests. After each milestone: commit, add an entry to `docs/DECISIONS.md`, update `STATUS.md`.

# Clawback

A personal AI agent that finds money you are losing (unused subscriptions, closing refund windows), prepares the action, and does it **only after you approve**. A counter shows the money and time recovered.

All bank, mail and merchant systems are emulated. Nothing is sent to a real company.

**Live demo:** not published yet — run locally with `make recorded` (see below). When a Nebius Serverless Endpoint is created with `./scripts/deploy_nebius.sh`, the script prints the public URL (`--auth none`).

**License:** [Apache-2.0](LICENSE)

## How a run looks

1. Upload a statement and receipts. The agent finds your subscriptions and flags the unused ones.
2. An on-demand deadline scan warns that a return window closes in a few days and offers to prepare a claim.
3. The agent searches the store's current policy (Tavily), drafts a claim with source links, and shows it. You press *Send*.
4. You ask to cancel a subscription. The agent reuses a skill it already learned and does it in seconds.
5. The counter shows projected annual savings for cancellations, plus refund amounts for claims.

## How we use NVIDIA Nemotron on Nebius Token Factory

Models are called through Nebius Token Factory’s OpenAI-compatible API (`app/llm/nebius.py`). Routing matches what the code does today:

| Tier | Model ID | Used for |
| --- | --- | --- |
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Statement merchant normalization; receipt JSON parse |
| Super | `nvidia/nemotron-3-super-120b-a12b` | Advisory citation check on a claim draft (code validator is authoritative) |
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` | Claim drafting; cancellation step planning when no saved skill exists |

Chat replies are rule-based from database state (not routed through Nano). Thinking is disabled by default (`enable_thinking=False`) so JSON lands in `message.content`.

## Nebius services used

| Service | Role |
| --- | --- |
| **Token Factory** | Live Nano / Super / Ultra calls when `NEBIUS_API_KEY` is set and `RECORDED_MODE` is false |
| **Serverless Endpoint** | Hosts the FastAPI app + SQLite for a public demo (`scripts/deploy_nebius.sh`, CPU preset, `--auth none`) |

Deadline scan: `make scan` / `POST /api/jobs/scan` / `python jobs/scan.py` — **run on demand**. A Serverless Job wrapper exists (`scripts/deploy_scan_job.sh`) to POST at a deployed endpoint; scheduling is not claimed.

## Tavily

At claim prepare time, `web_search_policy` (`app/claim_writer/policy.py`) calls Tavily (`POST https://api.tavily.com/search`) with a query built only from `{merchant, topic, jurisdiction}`. The draft validator requires at least one citation whose URL came from those search results in the current session. If search fails, the UI shows an error card — policy text is never taken from model memory. SoundHub (fictional) uses a labelled offline fixture in recorded mode.

## What is real and what is emulated

| Real | Emulated |
| --- | --- |
| Agent logic, SQLite memory, approval gate, Skill Forge, savings counter | Bank statement / email import |
| Nebius Token Factory model calls (when keyed) | Merchant websites and “send” (DB outbox + mock portal) |
| Tavily search (when keyed; real retailers) | SoundHub store and its return policy (fictional UNVERIFIED fixture) |

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
| `make verify` | pytest + e2e + report under `reports/` |
| `make docker-smoke` | Build `linux/amd64` image, run recorded container, health + Playwright |

## Run it (judges — Nebius Serverless Endpoint)

1. Push `main` so CI (`.github/workflows/image.yml`) builds and pushes `ghcr.io/<owner>/clawback:latest` for **linux/amd64**. Set the GHCR package visibility to **Public**.
2. Create MysteryBox secrets whose payload keys are `NEBIUS_API_KEY` and `TAVILY_API_KEY`.
3. Install and authenticate the Nebius CLI, then:

```bash
IMAGE=ghcr.io/<owner>/clawback:latest JOB_TOKEN=<optional> ./scripts/deploy_nebius.sh
```

The script uses `--auth none` so the printed URL opens in a normal browser (no token). Confirm with `curl -sf <url>/api/health`. Optional on-demand scan against that URL: `SCAN_TARGET_URL=<url> JOB_TOKEN=… ./scripts/deploy_scan_job.sh`.

**Cost / state:** the endpoint burns VM money while running — stop when idle. Container disk is not persistent; every cold start re-seeds the demo.

## Data egress

Exactly what leaves this machine. Raw receipts and statements stay in local SQLite; models see scrubbed text only. Data sent to Nebius Token Factory is covered by Nebius's terms — this README does not claim zero retention.

| Destination | What is sent |
| --- | --- |
| Nebius Token Factory | Scrubbed receipt/statement fragments for parse; purchase facts + Tavily excerpts for claim draft/validate; portal help text for cancel planning |
| Tavily Search | Policy query from `{merchant, topic, jurisdiction}` only (`build_policy_query`) — never receipt body, names, emails, or card digits |
| Mock merchant portal / outbox | Claim body and cancel steps only after a stored user approval |
| Browser | Same-origin UI/SSE only (no third-party analytics) |

Open the **Activity** tab in the web UI for the live `agent_log` timeline and per-model token counts.

## Project layout

```
app/        FastAPI app: api/, ingest/, deadline_watcher/, claim_writer/, skill_forge/,
            savings/, portal/, llm/, search/, privacy/, ui/ (static web chat)
jobs/       scan.py (on-demand / Serverless Job entrypoint)
scripts/    demo.py, verify_report.py, deploy_nebius.sh, deploy_scan_job.sh
tests/      pytest tests and Playwright e2e tests
demo/       statement, receipts, usage, seed history, policy fixtures, recorded/
```

The demo counter is defined by `demo/savings_plan.json` (84700 cents / 360 minutes).

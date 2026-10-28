# Mock Merchant Portal and Outbox

Clawback never talks to real merchants. Implemented in milestone M4 (see `SPEC.md` section 12). This document defines the emulated systems that make cancellations and claims real enough to demo, and that make Skill Forge demonstrable.

## Why it exists

Skills are step lists. Something must execute those steps and show a result. The mock portal is a small local web app (part of the backend, `app/portal/`) that behaves like merchant account pages, with deliberately different layouts per template so that the learning effect is visible.

## Portal templates

| Template | Merchants | Cancellation path |
| --- | --- | --- |
| `account-membership` | DailyNews (seeded history), FitPulse | Account → Membership → Cancel membership → Confirm |
| `settings-menu` | StreamFlix, CloudNest, TuneBox | Settings → Subscription → Manage plan → End plan → Confirm |

A skill is keyed by merchant first, then by `portal_template`. The seeded DailyNews skill therefore applies to FitPulse (same template) but not to StreamFlix or CloudNest (different template), which take the Ultra planning path and teach the agent a second skill.

## Portal endpoints (internal)

| Method and path | Purpose |
| --- | --- |
| GET /portal/{merchant}/account | Account page; lists the available actions for that template |
| GET /portal/{merchant}/help/cancel | Help article describing the cancellation path; this is what Ultra reads when planning |
| POST /portal/{merchant}/actions/{action} | Perform a step (`open_account_settings`, `find_cancel_link`, `confirm_cancel`, `save_confirmation`, and the `settings-menu` equivalents) |
| GET /portal/{merchant}/status | `active` or `cancelled`, with a confirmation number after cancellation |

Rules:

- The portal never changes state without the `confirm_cancel` action, and Clawback only calls that after user approval.
- Each action returns a small JSON result and the next available actions, so the agent can check the step really worked.
- Cancelling sets the merchant status to `cancelled`, returns a confirmation number, and stops future emulated charges.

## Execution paths

**Saved skill (`run_skill`).** Look up the skill, replay its steps against the portal, verify the final status is `cancelled`. No Ultra call. Target under 5 seconds.

**Ultra path.** Read `GET /portal/{merchant}/help/cancel` and `/account`, have Ultra plan the steps, show the plan, run it step by step with the confirmation gate, then call `save_skill` from the steps actually performed.

If a replayed skill fails (action not available), fall back to the Ultra path and update the skill.

## Outbox (claims)

"Send" for a claim means writing to an emulated outbox, not to the internet.

| Table | Fields |
| --- | --- |
| outbox | id, claim_id (unique), to_address, subject, body, queued_at, status (queued, delivered, refund_accepted) |

- On approval the claim goes to `outbox` with status `queued`.
- A demo-only action (`POST /portal/{merchant}/refund/accept`, or a timer in recorded mode) moves it to `refund_accepted`.
- Only `refund_accepted` triggers `record_savings(kind="refund", ...)`.

## Recorded mode

For every Golden Path step, a cached response exists (model output, Tavily result, portal result). With `RECORDED_MODE=true`, the clients return the cached response for a matching request hash and the UI shows a "recorded mode" label. The portal itself is local and works offline.

## Out of scope

- Any real merchant website or login.
- Real email delivery.
- Payment data. Nothing in the portal or outbox holds card numbers.

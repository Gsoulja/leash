# Connection-check API flow, for agents

This explains the correct call order for the live Viseca sandbox and what each
response means. It backs Postman folder **"5. Connection check walkthrough
(SCEN0101)"** in `leash-viseca-api.postman_collection.json`, and the same
sequence is captured with real responses in `solution/postman/apiCalls/`.
Source of truth is `technical_details.md` sections 4-8; this file only adds
what running it against the live sandbox actually showed.

## Why `GET /v1/decision-requests/next?wait=25` returns 204

That endpoint is a long-poll read of your team's queue. It does not create
work. It returns `204` whenever nothing is queued -- that is correct, not
broken. Only **`POST /v1/scenario-runs`** (with an active `mandate_id`) queues
purchase events for it to return. Once every event in that run is
`finalized`, the queue is empty again and `204` is the right answer.

## The order that produces a healthy (non-204) response

| # | Call | What it does | Watch for |
| --- | --- | --- | --- |
| 1 | `POST /v1/mandates` | Create a draft mandate from the customer's instruction + `hard_rules`. | Returns `draft_id`, not yet active. |
| 2 | `POST /v1/mandates/{draft_id}/confirm` | Customer agrees; activates the mandate. | Returns `mandate_id`. Reusable across many runs -- you do not need a fresh mandate per run. |
| 3 | `POST /v1/scenario-runs` `{"scenario_id", "mandate_id"}` | **This queues events.** | Returns `run_id`. `generated_event_count` may be 1 or 2 for `SCEN0101` -- do not hard-code an expected count. |
| 4 | `GET /v1/decision-requests/next?wait=25` | Long-polls up to 25s. | `200` with the first purchase in `data`, or `204` if step 3 has not run yet. |
| 5 | `POST /v1/authorizations/{id}/decision` | Your engine's automated verdict: `approve`, `decline`, or `step_up`. | Must land before `data.deadline_at` (8s from queueing). |
| 6 | `POST /v1/authorizations/{id}/resolve` | Only after a `step_up`, records the real customer's `approve`/`decline`. | Never send a second `/decision` for the same `authorization_id` -- see pitfalls below. |
| 7 | Poll again (`GET /v1/decision-requests/next?wait=25`) | Delivers the next queued purchase in the same run, if any. | Repeat steps 5-6 (or just 5, for `approve`/`decline`) per purchase. |
| 8 | `GET /v1/scenario-runs/{run_id}` | Check progress. | `status: "completed"` once `finalized_event_count == generated_event_count`. |
| 9 | Poll once more | Confirms the queue is empty. | `204` here means "no work left," not an error. |

## Pitfalls this flow is designed to avoid

- **A `step_up`'d purchase re-delivers on the next poll**, still as the same
  `authorization_id`, with `status: "pending_step_up"`. Sending a second
  `/decision` for it returns `409`. Use `/resolve` instead.
- **Missing the 8s deadline is not a crash.** The platform's watchdog
  auto-declines first; a late `/decision` POST for that ID comes back with
  `idempotent_replay: true` and the already-saved verdict, not an error and
  not a double-count.
- **Two clocks:** `deadline_at` (real clock, ~8s) governs when your automated
  decision must land. It is unrelated to the `wait=25` long-poll duration and
  unrelated to simulated purchase `timestamp` used for spend windows.
- **Reset is disabled during judging** (`bootstrap.features.reset: false`).
  Every `POST /v1/scenario-runs` in this flow is permanent on the team key --
  do not re-run folder 5 casually; it adds a new run to the record every time.

## Running this in Postman

1. Import `leash-viseca-api.postman_collection.json` and select the
   **"Leash — Viseca sandbox"** environment (`base_url`, `team_api_key`).
2. Open folder **"5. Connection check walkthrough (SCEN0101)"**.
3. Run it top to bottom with the Collection Runner, or click through items
   1-10 by hand. Each request's `test` script chains `draft_id` -> `mandate_id`
   -> `run_id` -> `authorization_id` into collection variables automatically,
   so no manual copy-paste is needed between steps.
4. Steps 5-6 and 8 in the folder encode one specific outcome (a CHF 18 grocery
   item gets `step_up` then customer `approve`; a CHF 38.90 two-line basket
   gets `decline`) matched to `SCEN0101`'s fixture purchases. A different
   scenario's purchases will need different decisions -- read `data` on each
   poll and decide from the actual facts, never from the scenario ID.

## Where to look for more

- `technical_details.md` sections 4-8 -- the full endpoint reference and rule
  format this flow implements.
- `solution/postman/apiCalls/` -- real captured request/response pairs from
  earlier exploration of every endpoint in the collection.
- `data/data_dictionary.md` -- field meanings, currency conversion, and time
  handling once you're writing decision logic instead of just exercising the
  API shape.

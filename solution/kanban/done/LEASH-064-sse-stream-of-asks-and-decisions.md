# LEASH-064: SSE stream of asks and decisions

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-005
**Task ID**: 005-T5
**Blocked by**: LEASH-044
**Blocks**: LEASH-127, LEASH-128
**Updated**: 2026-09-23

## Description
Server-sent events for the app: new asks, decisions and resolutions, fed by Postgres LISTEN/NOTIFY.

## Business Value
The engine never waits for the human; the app learns about asks instantly.

## Acceptance Criteria
- [x] A step_up appears on the stream within a second.
- [x] Reconnecting clients get current open asks first.
- [x] Clients resume with Last-Event-ID; initial state comes from the read model (LEASH-124).

## Technical Approach
`adapters/http/events.py`.

### Dependencies
- Needs LEASH-044.
- Blocks LEASH-127.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_new_ask_is_streamed`.

## Related Files
- `solution/engine/src/leash/adapters/http/events.py`
- `solution/engine/tests/adapters/test_sse.py`

## Notes
- Contract gap: `integrity.alert` has no kind for a ledger/platform *status* mismatch (from reconcile); only spend mismatches are streamed (`spend_counter_mismatch`), the rest stay in decision_events and the log. `mandate.changed` needs the mandate service (LEASH-061).

## Out of scope
- Mobile push notifications.

## Review log

### 2026-09-23 — independent agent review
- [ ] not met — criterion 1: each client pinned a pooled LISTEN connection and disconnects leaked it: 8 clients (or 8 disconnect cycles) exhausted the pool and the stream went dead for everyone.
- [x] met (content) — criterion 2: snapshot first, without ids, only open asks, matching /api/asks.
- [ ] not met — criterion 3: seq is assigned at insert but visible at commit, so a lower seq committing late fell behind the cursor and was lost (10–26 of ~440 events under stress); a connect race lost a step_up between the snapshot and the cursor; malformed Last-Event-ID values crashed the stream.
- [ ] not met (note) — shop text reached events through the injection excerpt in customer_message and reasons.
Verdict: returned to in-progress. Fix: one EventHub per process (a single LISTEN connection and one poller fanning out to per-client queues; clients borrow a connection only for snapshot and replay; unsubscribe is synchronous); a commit-safe cursor (moves past a seq only after every transaction running when it was handed out has finished); subscribe-before-snapshot removes the connect race; strict Last-Event-ID parsing (ASCII digits ≤ 18, future IDs → fresh connect); the injection excerpt moved from the shop-text check's message into its evidence (`actual`), so messages and reasons carry no shop text. New tests: late-committing lower seq, malformed IDs, shop text, 12 clients after 20 connect/disconnect cycles over HTTP. 610 engine tests pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] partly met — criterion 1: the pool fix holds (1,300 connect/disconnect cycles, no leak; latency ≤ 56 ms with 50 clients); but a single slow commit with no later traffic was never delivered, and any open transaction holding an xid — in any database on the server — stalled the whole stream indefinitely.
- [x] met — criterion 2: snapshot first, no ids, matches /api/asks field for field.
- [ ] not met — criterion 3: malformed IDs, future IDs and the connect race are fixed, but the 12-producer stress run still lost 21–101 of ~440 events: `pg_snapshot_xip` omits running transactions whose xid is at or above the snapshot's xmax, so the hub settled past uncommitted seqs.
- Shop text: met (excerpt only in evidence; rule verdicts and codes unchanged). Minor: cancelled streams left pending waits ("Task was destroyed").
Verdict: returned to in-progress. Fix: xid tracking replaced by a lock barrier — every writer takes an advisory lock shared before inserting a decision event (repository._event, held to commit); the hub reads the last seq handed out, then takes that lock exclusively with a 100 ms lock_timeout (retrying every 50 ms if a writer is still running). Once acquired, everyone who may hold a lower seq has finished. Unrelated transactions no longer matter. Pending waits are always cancelled. New tests: a single slow commit with no later traffic; an open xid-holding transaction in another database doesn't stall delivery. 613 engine tests pass (SSE ×3); mypy clean; registry lock re-pinned.

### 2026-09-23 — independent agent review (round 3)
- [x] met — criterion 1: single slow commit delivered live; idle xid-holding transactions in this or another database don't delay delivery (1–2 ms); latency ≤ 6 ms with 50 clients; pool flat after 1,300 cycles.
- [x] met — criterion 2.
- [x] met — criterion 3: 10 stress runs (12 producers, reconnecting + steady clients) and 4 harsher runs with slow commits: 0 missing, 0 duplicates, strictly increasing IDs, all schema-valid. Every decision_events write goes through the locking writer.
- Cost of the barrier: ≤ ~250 ms extra per decision with a 1–3 s slow decision in flight (p99 234 ms vs 73 ms), negligible otherwise; step_up throughput drops ~6× while a slow transaction lasts. Far inside the 8 s deadline and 2 s watchdog margin.
Note: added `test_only_the_locking_event_writer_inserts_into_decision_events` so a future writer can't bypass the lock silently.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.

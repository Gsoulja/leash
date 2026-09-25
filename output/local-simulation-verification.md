# Local Leash simulation verification — 25 September 2026

The app at http://localhost:8090 uses the isolated `leash-local` deployment. API and worker platform traffic is explicitly set to `http://fake:9000`; the assistant uses the real Apertus model. The older services configured for the hosted platform are stopped and their database volume is retained.

The simulator reads the supplied five scenarios and 45 purchase attempts. Customer history, cards and catalogue identities come from the supplied pack. Local scenario selection resolves the appropriate customer card server-side. Background preferences remain context rather than authority.

Fixed connections and failures:

- Model questions survive storage/reload and block unreviewable submissions.
- The model receives catalogue identities and the parser's unconfirmed reading; product lookup alone cannot authorize an unrequested product.
- Customer corrections create a fresh revision and invalidate an earlier unconfirmed platform draft. Confirmed permissions cannot be edited through this path.
- Rule-derived Must follow / May choose / Must ask review leads to explicit confirmation, then an actual shopping simulation and its cockpit.
- The rolling-period qualifier survives model extraction. Equivalent amount rules no longer cause false conflicts, and explicit count/familiarity clarifications are understood.
- Each revision retains its model assessment and background evidence. Confirmation is recoverable after reload.
- The simulator's period counter expires old approvals using simulated time. An ambiguous window produces null instead of an invented period total.
- Local platform state persists atomically across restarts. Existing completed runs and permission references were preserved during the update.
- The cockpit labels approved amounts without claiming completed payments from engine approval alone.

Verified application runs:

- `RUN-4e0354e121`: supplied connection check, `AU0001`, CHF 20.00. Engine approved; local platform accepted. Conversation revision 7 → permission `TM-d951e6dee0`, version 1 → live checkout `AZ-6e5c050ec7c1`. Evidence: `local-browser-journey.json`.
- `RUN-f1232853ee`: supplied household scenario, 10 checkouts, five approvals and five declines; all 10 decisions accepted by the local platform. `AU0011`, CHF 88.00, correctly approved after older purchases left the seven-day window. No spending-counter mismatch. Evidence: `local-household-retest.json`.

Verification includes 135 frontend tests, a 1,760-test engine/assistant regression run, rechecks of the affected platform integrations, and 100 final simulator/model/end-to-end checks after correcting the rolling-window expectation. All 45 supplied events are checked against the supplied event schema. `git diff --check` passes. Existing test warnings concern a deprecated test helper and a coroutine warning in the outbox test.

This verifies the documented local checkout flow, not every undocumented behavior of the unavailable hosted service. The fake remains a single-process simulator; it does not move real money. See `solution/RUNBOOK.md` for startup and state details.

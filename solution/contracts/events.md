# Leash event stream

`GET /api/events` is a [server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html) stream. The app uses it only to learn about **changes**; it loads the current state from the read endpoints first — `/api/mandates` and `/api/runs` say which mandate and run are current, then `/api/payments`, `/api/asks`, `/api/spending` and `/api/mandates/{id}/versions` — and applies events on top.

Each message looks like this on the wire:

```text
id: 41
event: ask.created
data: {"id": "41", "type": "ask.created", "at": "2026-09-23T14:00:00Z", "data": {…}}

```

- `data` is always a `StreamEvent` from `policy-api.yaml`: `id`, `type`, `at` (real clock, UTC) and a type-specific `data` object whose fields are fixed by the matching schema (`AskCreatedData`, `AskResolvedData`, `PaymentDecidedData`, `MandateChangedData`, `IntegrityAlertData`).
- `id` increases. On reconnect the browser sends `Last-Event-ID`, and the server resends everything after it.
- Money is a decimal string, as everywhere in the API.
- Shop text never appears in events; fetch `/api/payments/{authorization_id}` and render it as plain text.

## Event types

### `ask.created`

A payment is waiting for the customer (the engine answered `step_up`). The app opens the ask screen; `expires_at` is when the answer window ends (from bootstrap, DEC-008).

```json
{
  "id": "41",
  "type": "ask.created",
  "at": "2026-09-23T14:00:00Z",
  "data": {
    "authorization_id": "AZ-81c2",
    "merchant_name": "PixelHarbor",
    "billing_amount_chf": "289.00",
    "reasons": ["Same shop, items and price as the order at 11:40 (already paid)."],
    "expires_at": "2026-09-23T14:02:00Z",
    "can_approve": true
  }
}
```

### `ask.resolved`

A waiting payment ended: the customer answered, or the window expired. `outcome` is what the platform recorded.

```json
{
  "id": "42",
  "type": "ask.resolved",
  "at": "2026-09-23T14:00:37Z",
  "data": {
    "authorization_id": "AZ-81c2",
    "outcome": "declined",
    "resolved_by": "customer"
  }
}
```

### `payment.decided`

The engine answered a purchase. Sent for every verdict, including `step_up` (which is followed by `ask.created`).

```json
{
  "id": "43",
  "type": "payment.decided",
  "at": "2026-09-23T14:01:05Z",
  "data": {
    "authorization_id": "AZ-9d10",
    "engine_verdict": "decline",
    "final_state": "declined",
    "billing_amount_chf": "520.00",
    "customer_message": "CHF 520.00 is over your CHF 400.00 per-order limit."
  }
}
```

### `payment.delivered`

What the payment platform did with a decision the engine had already made (LEASH-130). Never a new
verdict — the verdict arrived earlier in `payment.decided`; this says only whether the answer was
accepted. `accepted` means the platform took the decision, and nothing more: it is not evidence that
anything was settled, shipped or delivered. `refused` means it never will, so the purchase is `not_sent`
and stops counting toward spend, familiarity, duplicates and the purchase count.

```json
{
  "id": "45",
  "type": "payment.delivered",
  "at": "2026-09-23T14:01:07Z",
  "data": {
    "authorization_id": "AZ-9d10",
    "delivery": "refused",
    "platform_outcome": "HTTP 422 deadline_passed",
    "final_state": "not_sent"
  }
}
```

### `mandate.changed`

The permission was confirmed, tightened or revoked. Tightening applies to later runs (DEC-006); revocation shows only what the platform confirmed (DEC-017).

```json
{
  "id": "44",
  "type": "mandate.changed",
  "at": "2026-09-23T14:05:00Z",
  "data": {
    "mandate_id": "TM-5521",
    "version": 2,
    "status": "active",
    "change": "tightened"
  }
}
```

### `integrity.alert`

Something the operator should know about: our ledger disagrees with the platform counter (DEC-010), a mandate rule the engine can't evaluate (DEC-005), or the local mandate copy differs from the one in the event (DEC-003). The app shows it in the inspector, not to the customer.

```json
{
  "id": "45",
  "type": "integrity.alert",
  "at": "2026-09-23T14:06:12Z",
  "data": {
    "kind": "spend_counter_mismatch",
    "run_id": "RUN-01",
    "detail": "Ledger CHF 234.50, platform CHF 299.50; using the higher value."
  }
}
```

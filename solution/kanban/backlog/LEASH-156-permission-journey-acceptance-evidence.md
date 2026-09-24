# LEASH-156: Permission journey: reviewed corpus and acceptance evidence

**Status**: BACKLOG
**Priority**: P0
**Type**: test
**Estimated Effort**: L
**Milestone**: M8 — Permission control journey
**Rule source**: Product agreement 2026-09-24
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T7
**Blocked by**: LEASH-101, LEASH-102, LEASH-130, LEASH-146, LEASH-147, LEASH-154
**Blocks**: LEASH-153, LEASH-155, LEASH-143
**Updated**: 2026-09-24

## Description
Create reviewed intent/context/clarification/permission/checkout cases and test the complete journey. Build the corpus before running the evaluation; expected rules and answers are reviewed product judgments, never inferred from historical authorization status.

## Business Value
Prove that the customer reviews the authority actually enforced, while measuring extraction mistakes and unnecessary interruptions.

## Acceptance Criteria
- [ ] Versioned examples include original messages, relevant scoped context, expected rules, source references, omitted restrictions, necessary questions, permitted choices and expected checkout behavior; disagreements in labels are recorded and resolved or marked ambiguous.
- [ ] Use original scenarios and separately identified additional personas. Mark constructed conversations/checkouts synthetic and human-reviewed; historical status supplies neither consent labels nor correct-purchase labels.
- [ ] Freeze train/calibration/evaluation partitions by persona and intent/template family, keeping paraphrases together and temporal history cutoffs explicit. Publish the split manifest and prevent leakage.
- [ ] Must-pass cases include missing selected product, unsupported quality guarantee, profile preference not adopted, explicit preference override, negation, budget/fee scope, no extras, unknown terms, corrected draft and stale confirmation.
- [ ] Integration cases cover confirmed handoff, matching checkout, forbidden substitute/add-on, injection, changed cart after customer review, duplicate/one-purchase reuse and platform refusal after a local approval.
- [ ] Every test traces conversation/context → candidate/revision → exact customer-confirmed permission → run/checkout → deterministic checks → platform outcome. Plain-language review is checked against the enforced payload.
- [ ] Report invented-permission and omission rates, necessary-question recall, unnecessary questions and task completion/interruptions, with denominators and per-family results. Keep extraction quality separate from payment-decision correctness.
- [ ] All explicit safety must-pass cases succeed. Broader quality targets and residual uncertainty require an evidence-backed product decision before release; do not claim universal intent understanding.
- [ ] Compare context-enabled and context-disabled flows on the same reviewed cases to establish whether background reduces questions or omissions without adding unauthorized rules.
- [ ] The runnable baseline needs no Laya model. Optional verifier experiments consume this corpus separately and cannot delay the first baseline journey.

## Technical Approach
Reuse engine evals, fake API, existing browser journey and payment evidence views. Store a compact versioned corpus with provenance and expected outcomes, then export one report linking test evidence; avoid a second decision engine.

### Dependencies
- Needs LEASH-101.
- Needs LEASH-102.
- Needs LEASH-130.
- Needs LEASH-146.
- Needs LEASH-147.
- Needs LEASH-154.
- Blocks LEASH-153.
- Blocks LEASH-155.
- Blocks LEASH-143.

## Testing Requirements
Write failing cases first. Run `cd solution/engine && uv run pytest tests/e2e/test_permission_journey.py`, the documented eval command, and the app’s Playwright journey suite. Include a deliberately omitted rule and stale-revision mutation that must fail the checks.

## Related Files
- `solution/evaluation/permission-journey/`
- `solution/engine/evals/`
- `solution/engine/tests/e2e/test_permission_journey.py`
- `solution/app/e2e/journey.spec.ts`
- `solution/docs/product-notes.md`

## Out of scope
- Treating synthetic performance as production accuracy; mandatory model training; changing the supplied challenge datasets; settlement or fulfillment proof.

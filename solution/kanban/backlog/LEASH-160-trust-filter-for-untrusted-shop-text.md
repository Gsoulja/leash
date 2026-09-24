# LEASH-160: Trust filter for untrusted shop and agent text

**Status**: BACKLOG
**Priority**: P1
**Type**: epic
**Total Effort**: ~6 days (13 tickets: 5 S, 8 M)
**Milestone**: M7 — Production hardening
**Rule source**: Viseca (merchant text is data, never instructions) + Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-023, DEC-025, DEC-029, DEC-030
**Updated**: 2026-09-24

## Description
Everything the shop or the external agent writes is untrusted: `merchant_name`, `merchant_city`, `item_name`, `item_details` and `purchase_description`. Today only `item_details` is scanned, on raw text, for injection alone; shop and item names go straight into Leash's own sentences; and nothing looks for Unicode obfuscation, payment links, implausible prices or homoglyph lookalike shops.

The trust filter is a pure stage between dedupe and fact reading. It **labels, never deletes**: raw text stays evidence, readers get a canonical view, and findings can only add caution (DEC-009). Integrity findings are never approved automatically (DEC-029/030); doubt findings follow the uncertainty policy; hard rules still decide first.

Tickets are split by the pattern each one applies (CLAUDE.md pattern table):

| Pattern | Ticket |
| --- | --- |
| Decision record | LEASH-161 |
| Value object | LEASH-162 `CanonicalText` |
| Specification + Notification | LEASH-163 detector interface and field-wide injection scan, LEASH-164 links and payment steering, LEASH-166 lookalike on skeleton |
| Port and adapter | LEASH-165 plausibility via `PriceReference` |
| Pipes and filters + Strategy/fallback | LEASH-167 trust stage in the pipeline |
| Most-restrictive combiner | LEASH-168 verdict mapping and safety properties |
| Anti-corruption layer (output edge, model prompts) | LEASH-169 tagged slots, LEASH-171 assistant context |
| BFF view model | LEASH-170 app screens |
| Append-only log + projections | LEASH-172 trust report in the log |
| Docs sync | LEASH-173 |

## Business Value
Closes the prompt-injection, scam-offer and redirect gaps in the one place every verdict passes through, without letting any model or text loosen a verdict.

## Reference
Design: `solution/docs/chat-to-purchase-flow-v2.html` (trust boundary, finding → verdict, screen 5b) and the architecture figure in `solution/docs/system-design.html`.

## Sub-tasks
- [ ] LEASH-161 (160-T1): Decision log entry for the trust filter · S · **DECISION gate**
- [ ] LEASH-162 (160-T2): CanonicalText value object · M
- [ ] LEASH-163 (160-T3): Trust detectors as specifications, with an injection scan over every text field · M
- [ ] LEASH-164 (160-T4): Link and payment-steering detector · M
- [ ] LEASH-165 (160-T5): Offer plausibility detector behind a catalogue port · M
- [ ] LEASH-166 (160-T6): Lookalike shop check on the confusable skeleton · S
- [ ] LEASH-167 (160-T7): Trust stage in the decision pipeline · M
- [ ] LEASH-168 (160-T8): Most-restrictive mapping for trust findings, with safety properties · M
- [ ] LEASH-169 (160-T9): Shop-supplied strings as tagged slots in explanations · M
- [ ] LEASH-170 (160-T10): App: quoted shop text and the suspicious-offer screen · M
- [ ] LEASH-171 (160-T11): Permission assistant context quotes shop names · S
- [ ] LEASH-172 (160-T12): Trust report in the append-only log and inspector · S
- [ ] LEASH-173 (160-T13): Sync design docs with the trust stage · S

## Done when
Every sub-task is in `done/`.

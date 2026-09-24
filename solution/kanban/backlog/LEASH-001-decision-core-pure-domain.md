# LEASH-001: Decision core (pure domain)

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Total Effort**: ~58 h (21 tickets; ~58 h in the MVP)
**Updated**: 2026-09-23

## Description
The pure `decide(purchase, mandate, state_snapshot, facts) -> Decision` function and the value objects it needs. No I/O anywhere in this epic.

## Business Value
This is the scored part of the challenge: every approve / decline / step_up and its explanation comes from here.

## Reference
Design: solution/docs/system-design.html (sections 'What happens to one purchase' and 'State that the engine remembers').

## Sub-tasks
- [ ] LEASH-010 (001-T1) [M1]: Money value object · S
- [ ] LEASH-011 (001-T2) [M1]: SimTime and WallTime value objects · S
- [ ] LEASH-012 (001-T3) [M1]: Purchase, merchant and line-item model · S
- [ ] LEASH-013 (001-T4) [M1]: Compiled mandate with tighten-only changes · M
- [ ] LEASH-014 (001-T5) [M1]: decide() skeleton, price rule and combiner · M
- [ ] LEASH-015 (001-T6) [M1]: State snapshot model · S
- [ ] LEASH-016 (001-T7) [M2]: Rolling period limit rule · M
- [ ] LEASH-017 (001-T8) [M2]: Shop-type rule · S
- [ ] LEASH-018 (001-T9) [M1]: Familiar-shop rule with lookalike evidence · M
- [ ] LEASH-019 (001-T10) [M1]: Basket rule: item match, purpose, add-ons, quantity · M
- [ ] LEASH-020 (001-T11) [M1]: Facts type and FactReader port · S
- [ ] LEASH-021 (001-T12) [M2]: Size rule · S
- [ ] LEASH-022 (001-T13) [M2]: Return-window rule · S
- [ ] LEASH-023 (001-T14) [M2]: Shop-text instruction flag · S
- [ ] LEASH-024 (001-T15) [M2]: Duplicate and split-order detection · M
- [ ] LEASH-025 (001-T16) [M2]: Single-purchase rule · S
- [ ] LEASH-026 (001-T17) [M2]: Session integrity rule · M
- [ ] LEASH-027 (001-T18) [M1]: Explanation core: reason codes, message, evidence · M
- [ ] LEASH-028 (001-T19) [M1]: Purchase and mandate state machines · S
- [ ] LEASH-119 (001-T20) [M2]: Fulfilment rule · S
- [ ] LEASH-120 (001-T21) [M2]: Unsupported mandate rule outcome · S

## Done when
Every sub-task is in `done/`.

# LEASH-008: Permission assistant and external-agent control

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Updated**: 2026-09-24

## Description
Build Leash's permission assistant around the existing policy and checkout engine. The customer clarifies and confirms authority in Leash; an external shopping agent searches and prepares purchases. Viseca's simulator represents that external agent in the challenge. Supersedes the earlier own-shopping-assistant scope under DEC-020; DEC-033–037 record the agreed direction. Historical filenames remain stable for links.

## Business Value
Make delegated purchasing understandable and enforceable without giving the permission LLM authority to spend or activate mandates.

## Reference
`solution/docs/product-notes.md` (current agreement) and `solution/docs/customer-journey-for-design.md`.

## Sub-tasks
- [ ] LEASH-100 (008-T1): Optional catalogue reference resolution for permission clarification.
- [ ] LEASH-101 (008-T2): Permission conversation, supported proposals and draft revisions.
- [ ] LEASH-102 (008-T3): Confirmed-permission handoff and checkout binding.
- [ ] LEASH-103 (008-T4): Optional adversarial checkout demonstration.
- [ ] LEASH-154 (008-T5): Relevant customer context with provenance and scope.
- [ ] LEASH-155 (008-T6): Evaluate Laya permission verification; fine-tune only if justified.
- [ ] LEASH-156 (008-T7): Reviewed permission corpus and complete-journey acceptance evidence.

## Delivery order
Context → permission conversation and editable drafts → exact review → external-agent handoff → checkout and platform outcome → acceptance evidence. LEASH-145–153 own presentation. Laya verification is an optional evaluated enhancement and does not block the first complete journey. Catalogue lookup is optional: unresolved references can always become customer questions.

## Done when
Every sub-task is in `done/`. This epic's optional experiments do not all gate the functional release; LEASH-128 and LEASH-153 name the required evidence.

## Out of scope
An in-house shopping executor, general card credentials for agents, and TaskCard signing or cross-protocol integration without a separate product decision.

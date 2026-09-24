# LEASH-173: Sync design docs with the trust stage

**Status**: BACKLOG
**Priority**: P2
**Type**: docs
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: — (docs)
**Parent**: LEASH-160
**Task ID**: 160-T13
**Blocked by**: LEASH-161
**Blocks**: none
**Updated**: 2026-09-24

## Description
`system-design.html` already shows the trust filter in "Components and trust boundaries". The per-purchase pipeline figure ("What happens to one purchase") still has seven stages, and CLAUDE.md lists seven pipeline stages. Add the trust stage, update the stage-03 text (readers read canonical text) and cite DEC-038. Change the "proposal" labels in `chat-to-purchase-flow-v2.html` to match DEC-038.

## Business Value
Design pages stay in sync with decisions (working agreement).

## Acceptance Criteria
- [ ] The pipeline figure has the trust stage between dedupe and extract facts, with a caption that matches DEC-038.
- [ ] CLAUDE.md's pipes-and-filters row names the new stage.
- [ ] No page calls the filter a proposal once DEC-038 is accepted (edge case: items DEC-038 deferred stay marked as open).

## Technical Approach
Edit the HTML pages and CLAUDE.md only. Publish updated pages to their existing artifacts where they exist.

### Dependencies
- Needs LEASH-161.

## Testing Requirements
No code. Check: open both pages at 400 px and desktop width; `grep -c trust` finds the new stage in the pipeline figure.

## Related Files
- `solution/docs/system-design.html`
- `solution/docs/chat-to-purchase-flow-v2.html`
- `CLAUDE.md`

## Out of scope
- Laya pipeline page.
- New diagrams beyond the stage change.

# Leash kanban board

One markdown file per ticket. **The folder a ticket sits in is its stage.** The board is read by `/graphloop`, which turns the dependency fields into a graph and tells us what is ready to work on.

```
backlog/ → analysis/ → in-progress/ → review/ → testing/ → done/
```

| Stage | Meaning | `**Status**` value |
| --- | --- | --- |
| `backlog/` | Written, not started | `BACKLOG` (or `BLOCKED`) |
| `analysis/` | Being clarified before work starts | `ANALYSIS` |
| `in-progress/` | Being built (test-first) | `ONGOING` |
| `review/` | Built and agent-reviewed; **waiting for a human** | `REVIEW` |
| `testing/` | Human approved; being tested end to end | `TESTING` |
| `done/` | Finished. Only a human moves tickets here. | `DONE` |

Only `done/` unblocks downstream tickets. `review/` is a human gate.

## Naming

`LEASH-<NNN>-<short-slug>.md`, for example `LEASH-012-period-limit-rule.md`. Numbers are never reused.

- **Epic:** a container with `## Sub-tasks` and no `**Task ID**`. Never worked directly; it closes when its children do.
- **Leaf ticket:** has a `**Task ID**` (`<epic number>-T<n>`, e.g. `002-T3`) and does real work.

## Ticket template

```markdown
# LEASH-NNN: <title>

**Status**: BACKLOG
**Priority**: P0 | P1 | P2
**Type**: feature | test | infra | docs | research
**Estimated Effort**: S | M | L   (S ≈ ≤ 2 h, M ≈ half a day, L ≈ a day)
**Parent**: LEASH-NNN
**Task ID**: NNN-TN
**Blocked by**: LEASH-NNN, LEASH-NNN
**Blocks**: LEASH-NNN
**Gate**: DECISION — <what a human must decide>   (only when needed)
**Updated**: YYYY-MM-DD

## Description
What and why, readable without the conversation that produced it.

## Business Value
Which part of the challenge or demo this serves.

## Acceptance Criteria
- [ ] One observable behaviour per line.

## Technical Approach
Where it lives in the hexagonal layout, which pattern applies.

### Dependencies
- Needs LEASH-NNN.
- Blocks LEASH-NNN.

## Testing Requirements
The failing test(s) to write first (TDD), and the command that runs them.

## Related Files
- `solution/engine/...`

## Out of scope
- What this ticket deliberately does not do.
```

`### Dependencies` is read sentence by sentence: `Needs`, `Requires`, `After`, `Depends on` point upstream; `Blocks`, `Feeds`, `Precedes` point downstream. Ranges like `Needs 002-T1 through T5` expand.

## Gates

- `**Gate**: DECISION — …` a human reads a result and chooses what happens next (for example, whether Laya beat the regex baseline).
- `**Gate**: FREEZE — …` an irreversible step (for example, the submission tag).

Gated tickets are never worked automatically.

## Working the board

```
/graphloop validate            # check the graph is sound
/graphloop next                # what is ready now
/graphloop waves               # the whole plan, wave by wave
/graphloop run LEASH-NNN       # work one ticket, test-first, then independent review
```

Every ticket follows the TDD rules in [`../../CLAUDE.md`](../../CLAUDE.md): write the failing test named in *Testing Requirements* first.

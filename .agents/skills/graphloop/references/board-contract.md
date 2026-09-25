# What graphloop needs from a board

The parser is deliberately small and reads a fixed-format header plus one
section. Anything it cannot read is simply not an edge — it never guesses.

## Layout

```
kanban/
  backlog/  analysis/  in-progress/  review/  testing/  done/
    <PREFIX>-<NNN>-<slug>.md
```

Stage is the directory. `done/` membership is what marks work complete for
scheduling — not the `Status` field, which is checked against the directory and
reported as an error when they disagree.

## Header fields read

| field | meaning |
|---|---|
| `**Status**` | cross-checked against the stage directory |
| `**Priority**`, `**Type**` | carried into `json`, not used for ordering |
| `**Estimated Effort**` / `**Total Effort**` | shown in the ready set |
| `**Parent**` | epic membership; **not** an edge |
| `**Task ID**` | e.g. `002-T3`. Presence marks a leaf; absence marks an epic |
| `**Blocked by**` | upstream edges |
| `**Blocks**` | downstream edges, made symmetric on the target |
| `**Gate**` | halts automated execution; text is shown at the halt |

`**Parent**` is not a dependency. An epic is a container, and treating it as an
edge produces a wave containing both a parent and its children — which is the
usual sign that a board's edges are wrong.

## The Dependencies section

```markdown
### Dependencies
- Needs 002-T3.
- Needs 004-T1 through T12.
- Blocks HARNESS-009.
```

Parsed sentence by sentence. A sentence is an upstream claim if it contains
`needs`, `requires`, `after`, `depends on` or `consumes`; it is skipped if it
only contains `blocks`, `unblocks`, `feeds` or `precedes`. One bullet may carry
both — the upstream verb wins.

Ranges (`T1 through T12`, `T1-T12`, `T1 to T12`) expand to every task in between.
People write ranges; the parser handles them rather than requiring twelve bullets.

Task ids resolve through `**Task ID**`, so `Needs 002-T3` finds whichever file
declares `**Task ID**: 002-T3` regardless of its ticket number. Ticket ids
(`HARNESS-004`) resolve directly.

## Validation rules

- no cycles
- no reference to a ticket not on the board
- nothing marked `BLOCKED` sitting outside `backlog/`
- nothing in `done/` whose `Status` is not `DONE`
- nothing with `Status: DONE` sitting outside `done/` — the scheduler reads the
  **directory**, so this one silently starves every downstream ticket
- nothing in `in-progress/`, `review/` or `testing/` still marked `BACKLOG`

The parser has its own check: `graphloop.py --self-test`.

## Gates

```markdown
**Gate**: FREEZE — a human confirms the tag is signed and pushed before any
generated row exists. No automated run may cross this.
```

`FREEZE` marks an irreversible commitment. `DECISION` marks a point where a human
reads a result and chooses the branch. Both halt execution unconditionally; the
scheduler still shows them in the wave plan so the shape of the work is visible.

## Review log

Written by `/graphloop` after an independent agent reviews finished work.
Appended to the ticket, never overwritten — a ticket that went round twice keeps
both rounds, because the second reviewer should see what the first one said.

```markdown
## Review log

### 2026-09-04 — independent agent review
- [x] met — criterion 1: <what the reviewer verified>
- [ ] not met — criterion 3: <the named gap>
- [?] unverifiable — criterion 4: <the missing evidence>
Verdict: returned to in-progress.
```

The parser ignores this section. It exists for the human at the `review/` gate,
who should be able to see what was already checked and what was not.

## The review packet

```bash
python3 "$(git rev-parse --show-toplevel)/.claude/skills/graphloop/graphloop.py" packet <TICKET-ID>
```

Emits exactly what an independent reviewer needs and nothing else: the ticket's
`Acceptance Criteria`, `Testing Requirements`, `Out of scope` and
`Related Files`, plus `git status --short` and `git diff HEAD`.

It is built mechanically on purpose. If the implementer assembles the review
input by hand, the reviewer sees a curated case rather than the work — and the
`Out of scope` section, which is what keeps a review from becoming a
renegotiation, is the first thing that goes missing.

## Extending

The parser is one file, stdlib only, about 200 lines. Adding a field means adding
it to `parse()` and to this document. Resist adding a config file for it — the
format is the board, and the board is already the source of truth.

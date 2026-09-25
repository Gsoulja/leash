---
name: graphloop
description: "Use when working a kanban backlog of dependency-linked tickets — 'what do I work on next', 'process the backlog', 'run the next ticket', 'is the board consistent', 'what is blocked'. Reads kanban/ as a dependency DAG, validates it, computes execution waves, works one ready ticket at a time, has an independent agent review the result against the ticket's acceptance criteria, and stops dead at gates. Complements /graphify: that one graphs what the code IS, this one graphs what the work DOES."
---

# /graphloop

The board is already a graph. Every ticket carries `**Blocked by**`, `**Blocks**`,
`**Parent**` and a `### Dependencies` section. `graphloop` reads those as edges,
checks the graph is sound, and tells you exactly what is runnable right now — then
works one ticket at a time through the kanban stages.

## Usage

```
/graphloop                    # validate, then show what is ready
/graphloop next               # the ready set only
/graphloop waves              # the whole execution plan, wave by wave
/graphloop validate           # cycles, dangling refs, stage/status disagreement
/graphloop run                # work the top ready ticket end to end
/graphloop run HARNESS-014    # work a named ticket
/graphloop stats              # counts per stage, epics vs leaves, wave depth
/graphloop --self-test        # check the parser itself still works
/graphloop json               # nodes + edges, for /graphify's viz or anything else
/graphloop review HARNESS-014 # independent agent review of finished work
```

Unattended cadence is `/loop`'s job, not this skill's:
`/loop 30m /graphloop run`. Do not build scheduling in here.

## What graphloop is for

Answering "what now" from the board rather than from memory, and doing it in an
order the dependencies actually permit. It is a **scheduler over tickets**, not a
knowledge graph over content — reach for `/graphify` when the question is about
the code or the docs.

It is worth running the moment a board has more than a dozen linked tickets,
because at that size the ready set stops being obvious and hand-picking work
starts silently violating the order.

## What You Must Do When Invoked

### Step 1 — Validate before anything else

```bash
python3 "$(git rev-parse --show-toplevel)/.Codex/skills/graphloop/graphloop.py" validate --board kanban
```

A broken graph is not a warning, it is a stop. Cycles, dangling references and
status/stage disagreement all mean the board is lying about what is runnable.
Fix the tickets, then continue. **Never work a ticket from a board that fails
validation** — you would be picking work from a plan that does not hold.

If the board has no `kanban/` at the repo root, ask where it is rather than
guessing; pass `--board <path>`.

If validation fails in a way that looks like the parser rather than the board,
run `python3 "$(git rev-parse --show-toplevel)/.Codex/skills/graphloop/graphloop.py" --self-test`. It builds a
synthetic board and asserts the six behaviours that would silently reorder a real
plan if they broke: plain edges, range expansion, verb direction, topological
order, cycle detection, and stage/status drift.

### Step 2 — Read the ready set

```bash
python3 "$(git rev-parse --show-toplevel)/.Codex/skills/graphloop/graphloop.py" next --board kanban
```

Three lists come back:

- **IN FLIGHT** — leaf tickets sitting in `analysis/`, `in-progress/`, `review/`
  or `testing/`. Work already underway, by you or by someone else. **Finish or
  hand these back before starting anything new.** They are deliberately excluded
  from READY: offering a ticket that is already being worked is how two runs
  double-do the same job.
- **READY** — leaf tickets whose upstream work is in `done/` and that nobody has
  picked up. Only `done/` counts as complete; a ticket sitting in `review/` has
  not unblocked anything yet, because `review` is a human gate.
- **HELD** — what the scheduler refuses to hand you, with the reason: a
  `BLOCKED` status, or a gate.

Present the ready set to the user with effort estimates and let them choose,
unless they named a ticket or said to just proceed. More than about three ready
tickets means the choice is theirs to make, not yours to assume.

### Step 3 — Gates stop you. Always.

A ticket carrying a `**Gate**:` field is **never** worked automatically, no
matter how ready the graph says it is. Two kinds:

- **FREEZE** — an irreversible commitment (signing a pre-registration, pushing a
  tag). Crossing it wrongly cannot be undone by a later commit.
- **DECISION** — a human reads a result and chooses whether the next branch runs
  at all.

At a gate: stop, print the gate text, say what the decision is and what each
answer costs, and wait. Do not infer the answer from the data, and do not work
"just the safe part" of a gated ticket. A gate that an agent can talk itself
through is not a gate.

### Step 4 — Work exactly one ticket

Read the whole ticket file first. It is written to be executable without the
conversation that produced it — `Description`, `Business Value`,
`Acceptance Criteria`, `Technical Approach`, `Dependencies`,
`Testing Requirements`, and often `Out of scope`.

Then:

1. Move the file to `kanban/in-progress/` and set `**Status**: ONGOING`,
   `**Updated**: <today>`.
2. Do the work. **Only** what the ticket's `Acceptance Criteria` name — its
   `Out of scope` section exists because someone already decided what not to do.
3. Create only the files the ticket's `Related Files` lists. No scaffolding
   ahead of need.
4. Write the check named in `Testing Requirements` and run it. A ticket whose
   check does not run is not done.
5. Tick every `Acceptance Criteria` box that is genuinely satisfied. Leave the
   rest unticked and say so — a half-done ticket reported as done corrupts every
   downstream wave.
6. Move to `kanban/review/`, set `**Status**: REVIEW`. `review` is a human gate,
   not completion — never move anything to `done/` yourself.

### Step 5 — Independent review, by an agent that did not do the work

Before anything moves to `review/`, a second agent checks the work against the
ticket. Build the packet mechanically so the reviewer sees the contract and the
diff rather than whatever the implementer chose to highlight:

```bash
python3 "$(git rev-parse --show-toplevel)/.Codex/skills/graphloop/graphloop.py" packet HARNESS-014 --board kanban
```

Then spawn a reviewer with the `Agent` tool:

```
subagent_type: "general-purpose"     ← a FRESH agent
```

**Never use `subagent_type: "fork"` here.** A fork inherits your context,
including your reasoning about why the work is fine — so it reviews its own
homework and agrees. The whole value is that the reviewer has the ticket and the
diff and nothing else. This is the same independence rule the harness applies to
its own audit path: orthogonal evidence, over data the grader never saw.

Give the reviewer the packet, and ask for a verdict **per acceptance criterion**,
in three states:

| verdict | meaning |
|---|---|
| `met` | the diff demonstrably satisfies the criterion |
| `not met` | it does not, with the specific gap named |
| `unverifiable` | cannot be judged from the diff alone — say what evidence is missing |

Three states, not two. "Unverifiable" is the honest answer for a criterion that
needs a running system or a human eye, and collapsing it into "met" is how a
review becomes a rubber stamp.

Tell the reviewer explicitly: **do not fix anything, do not suggest
improvements outside the ticket's criteria, and treat the `Out of scope` section
as binding.** A reviewer that expands scope is worse than none — it turns every
ticket into a negotiation.

Then act on the verdict:

- **all `met`** → move to `kanban/review/`, `**Status**: REVIEW`.
- **any `not met`** → the ticket stays in `in-progress/`. Fix, re-run the check,
  re-review. Do not move it on and mention the gap in passing.
- **any `unverifiable`** → it may still move, but the review log records what
  could not be checked, and you say so to the user. The human gate is what
  resolves it.

Append the outcome to the ticket so it is on the record:

```markdown
## Review log

### 2026-09-04 — independent agent review
- [x] met — criterion 1: <what the reviewer verified>
- [ ] not met — criterion 3: <the named gap>
- [?] unverifiable — criterion 4: <the missing evidence>
Verdict: returned to in-progress.
```

The agent review does not replace the human gate. `review/` still means a person
has yet to look — the agent's job is to make sure the person is not the first
one to notice something obvious.

### Step 6 — Re-validate, then report

Re-run `validate` and `next`. Tell the user what moved, what the check said,
what the reviewer found, and what the new ready set is. Then stop. One ticket per invocation unless the user
asked for more — a run that quietly chains six tickets is impossible to review.

## Reading the graph

- **Wave N** = everything whose dependencies are satisfied once waves 1..N-1 are
  done. Tickets inside a wave are mutually independent and could run in parallel.
- A leaf ticket carries `**Task ID**` and does real work. An epic carries
  `## Sub-tasks` and closes when its children do — **never work an epic
  directly.**
- Deep, thin waves mean a serialised plan. Wide waves mean parallelism is
  available. A wave containing an epic and its own children means the edges are
  wrong.

## What the parser needs from a ticket

Edges come from the header block and one section. Details and the exact grammar
are in `references/board-contract.md`. In short:

```markdown
**Blocked by**: HARNESS-003, HARNESS-004
**Blocks**: HARNESS-012
**Parent**: HARNESS-002
**Task ID**: 002-T3
**Gate**: FREEZE — <what a human must confirm>

### Dependencies
- Needs 004-T1 through T12.        <- range, expands to all twelve
- Blocks HARNESS-009.              <- downstream, NOT read as a dependency
```

Direction is carried by the verb. `Needs` / `Requires` / `After` / `Depends on`
point upstream; `Blocks` / `Feeds` / `Precedes` point downstream and are ignored
as inputs. Getting this wrong inverts an edge and silently reorders the plan.

## Out of scope

- **Scheduling.** `/loop` already does recurring invocation.
- **Knowledge graphs over content.** `/graphify` already does that. If a visual
  is wanted, `graphloop json` emits nodes and edges for it.
- **Moving tickets to `done/`.** `review` is a human gate.
- **Creating tickets.** This skill reads and works a board; it does not plan one.
- **Working more than one ticket per invocation** unless asked.
- **Reviewing with a fork of yourself.** It is not an independent review, and a
  review that always passes is worse than no review, because it launders the
  work as checked.
- **Letting the reviewer fix things.** It reports; the implementer fixes. A
  reviewer that edits has no independence left for the next round.

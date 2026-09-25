#!/usr/bin/env python3
"""graphloop - read a kanban board as a dependency DAG, and say what is runnable.

The board is the graph. Edges already exist as text in every ticket:
**Blocked by**, **Blocks**, **Parent**, and "Needs <id>" under ### Dependencies.
This reads them, validates the graph, and computes execution waves.

No deps beyond the stdlib. ponytail: regex parsing over a markdown-AST library --
the header block is fixed-format and a parser would be more code than value.
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import defaultdict, deque
from pathlib import Path

STAGES = ["backlog", "analysis", "in-progress", "review", "testing", "done"]
TICKET = re.compile(r"^([A-Z]+)-(\d{3})")
FIELD  = re.compile(r"^\*\*([A-Za-z ]+)\*\*:\s*(.+?)\s*$", re.M)
REF    = re.compile(r"\b([A-Z]+-\d{3})\b")
TREF   = re.compile(r"\b(\d{3})-T(\d+)\b")


def parse(root: Path) -> dict:
    nodes, by_taskid = {}, {}
    for stage in STAGES:
        for f in sorted((root / stage).glob("*.md")) if (root / stage).is_dir() else []:
            text = f.read_text(encoding="utf-8", errors="replace")
            head = text.split("\n## ", 1)[0]
            m = TICKET.match(f.name)
            if not m:
                continue
            tid = f"{m.group(1)}-{m.group(2)}"
            fields = dict(FIELD.findall(head))
            title = text.splitlines()[0].lstrip("# ").split(": ", 1)[-1]
            n = {
                "id": tid, "title": title, "file": str(f.relative_to(root.parent)),
                "stage": stage,
                "status": fields.get("Status", "").strip(),
                "priority": fields.get("Priority", ""), "type": fields.get("Type", ""),
                "effort": fields.get("Estimated Effort") or fields.get("Total Effort", ""),
                "parent": (REF.search(fields.get("Parent", "")) or [None])[0]
                          if REF.search(fields.get("Parent", "")) else None,
                "task_id": fields.get("Task ID"),
                "gate": fields.get("Gate"),
                "blocked_by": sorted(set(REF.findall(fields.get("Blocked by", "")))),
                "blocks": sorted(set(REF.findall(fields.get("Blocks", "")))),
                "body": text,
            }
            if n["parent"] == tid:
                n["parent"] = None
            nodes[tid] = n
            if n["task_id"]:
                by_taskid[n["task_id"]] = tid

    # Edges from the Dependencies prose. Direction is carried by the verb:
    # "Needs X" means X is upstream; "Blocks X" means X is DOWNSTREAM and must
    # not be read as a dependency. Sentences are the unit, so one bullet can say
    # both. Ranges ("T1 through T12", "T1-T12") expand -- people write them.
    UP   = re.compile(r"\b(needs?|requires?|after|depends on|consumes)\b", re.I)
    DOWN = re.compile(r"\b(blocks?|unblocks?|feeds|precedes)\b", re.I)
    RANGE = re.compile(r"\b(\d{3})-T(\d+)\s*(?:through|to|\u2013|-)\s*T?(\d+)\b", re.I)

    def taskrefs(sentence, own_prefix):
        out = []
        for pre, lo, hi in RANGE.findall(sentence):
            for i in range(int(lo), int(hi) + 1):
                out.append(f"{pre}-T{i}")
        for pre, num in TREF.findall(RANGE.sub(" ", sentence)):
            out.append(f"{pre}-T{num}")
        return out

    for n in nodes.values():
        dep = re.search(r"^###? Dependencies\n(.*?)(?=\n#{2,3} |\Z)", n["body"], re.S | re.M)
        if not dep:
            continue
        for sentence in re.split(r"(?<=[.;])\s+|\n", dep.group(1)):
            if not sentence.strip():
                continue
            # Explicit upstream verb, or no edge. Defaulting to "a mention is a
            # dependency" turned "Affects HARNESS-009" into a wait on the whole
            # publish epic and stalled 70 tickets. Prose is full of references
            # that are not dependencies -- "see", "affects", "related to" --
            # and a false edge is far more expensive than a missing one.
            if not UP.search(sentence) or (DOWN.search(sentence) and not UP.search(sentence)):
                continue
            for tref in taskrefs(sentence, n["id"]):
                src = by_taskid.get(tref)
                if src and src != n["id"]:
                    n["blocked_by"].append(src)
            for ref in REF.findall(sentence):
                if ref in nodes and ref != n["id"] and ref != n["parent"]:
                    n["blocked_by"].append(ref)
        n["blocked_by"] = sorted(set(n["blocked_by"]))

    # make Blocks symmetric with Blocked by
    for n in nodes.values():
        for tgt in n["blocks"]:
            if tgt in nodes and n["id"] not in nodes[tgt]["blocked_by"]:
                nodes[tgt]["blocked_by"] = sorted(set(nodes[tgt]["blocked_by"] + [n["id"]]))
    for n in nodes.values():
        n["blocked_by"] = [b for b in n["blocked_by"] if b in nodes]
    return nodes


def validate(nodes: dict) -> list[str]:
    errs = []
    for n in nodes.values():
        for b in n["blocked_by"]:
            if b not in nodes:
                errs.append(f"{n['id']}: blocked by unknown ticket {b}")
        if n["parent"] and n["parent"] not in nodes:
            errs.append(f"{n['id']}: parent {n['parent']} not on the board")
        st, stage = n["status"].upper(), n["stage"]
        if "BLOCKED" in st and stage != "backlog":
            errs.append(f"{n['id']}: marked BLOCKED but sitting in {stage}/")
        if stage == "done" and "DONE" not in st:
            errs.append(f"{n['id']}: in done/ but Status is {n['status']!r}")
        if "DONE" in st and stage != "done":
            errs.append(f"{n['id']}: Status DONE but sitting in {stage}/ — "
                        f"downstream work will not unblock")
        if stage in ("in-progress", "review", "testing") and st in ("BACKLOG", ""):
            errs.append(f"{n['id']}: in {stage}/ but Status is {n['status']!r}")
    # cycles
    indeg = {k: len([b for b in v["blocked_by"]]) for k, v in nodes.items()}
    q = deque(k for k, d in indeg.items() if d == 0)
    seen = 0
    rev = defaultdict(list)
    for k, v in nodes.items():
        for b in v["blocked_by"]:
            rev[b].append(k)
    while q:
        k = q.popleft(); seen += 1
        for nxt in rev[k]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if seen != len(nodes):
        stuck = sorted(k for k, d in indeg.items() if d > 0)
        errs.append(f"cycle involving: {', '.join(stuck[:12])}")
    return errs


def waves(nodes: dict) -> list[list[str]]:
    """Execution waves over LEAF tickets only.

    Epics are containers, not work. Scheduling them double-counts -- an epic's
    own **Blocked by** is shorthand for constraints its children already carry --
    and mixing the two closes false cycles. Epic closure is derived instead, by
    `epic_closes()`: an epic lands in the wave its last child lands in.
    """
    done = {k for k, v in nodes.items() if v["stage"] == "done"}
    leaf = {k for k, v in nodes.items() if v["task_id"]}
    kids = defaultdict(set)
    for k, v in nodes.items():
        if v["parent"]:
            kids[v["parent"]].add(k)

    def expand(dep, seen=None):
        """'Needs HARNESS-011' means 'needs everything 011 contains'. An edge to
        an epic must resolve to its leaves or it is silently dropped."""
        seen = seen or set()
        if dep in leaf or dep in seen:
            return {dep} & leaf
        seen.add(dep)
        out = set()
        for c in kids.get(dep, ()):
            out |= expand(c, seen)
        return out

    rem = {}
    for k, v in nodes.items():
        if k not in leaf or k in done:
            continue
        deps = set()
        for b in v["blocked_by"]:
            deps |= expand(b)
        rem[k] = deps - done - {k}
    out = []
    while rem:
        ready = sorted(k for k, deps in rem.items() if not deps)
        if not ready:
            break                      # cycle; validate() reports it
        out.append(ready)
        for k in ready:
            del rem[k]
        for deps in rem.values():
            deps -= set(ready)
    return out


def epic_closes(nodes: dict, ws: list[list[str]]) -> dict[int, list[str]]:
    """Which epics complete in which wave: the wave holding their last child."""
    where = {k: i for i, w in enumerate(ws) for k in w}
    out = defaultdict(list)
    for k, n in nodes.items():
        if n["task_id"]:
            continue
        kids = [c for c, v in nodes.items() if v["parent"] == k]
        if kids and all(c in where for c in kids):
            out[max(where[c] for c in kids)].append(k)
    return out


def blocked_reason(n: dict) -> str | None:
    if "BLOCKED" in n["status"].upper():
        return "status BLOCKED"
    if n["gate"]:
        return f"gate: {n['gate']}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(prog="graphloop")
    ap.add_argument("cmd", choices=["validate", "waves", "next", "json", "stats", "packet"])
    ap.add_argument("ticket", nargs="?", help="ticket id, for `packet`")
    ap.add_argument("--board", default="kanban")
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    root = Path(a.board).resolve()
    if not root.is_dir():
        print(f"no board at {root}", file=sys.stderr); return 2
    nodes = parse(root)
    if not nodes:
        print(f"no tickets found under {root}", file=sys.stderr); return 2

    if a.cmd == "validate":
        errs = validate(nodes)
        print(f"{len(nodes)} tickets, {sum(len(n['blocked_by']) for n in nodes.values())} edges")
        for e in errs:
            print(f"  FAIL  {e}")
        print("  ok — no cycles, no dangling refs" if not errs else f"  {len(errs)} problem(s)")
        return 1 if errs else 0

    if a.cmd == "waves":
        ws = waves(nodes)
        closes = epic_closes(nodes, ws)
        for i, w in enumerate(ws, 1):
            gates = [k for k in w if nodes[k].get("gate")]
            tail = ""
            if closes.get(i - 1):
                tail += "   closes " + ", ".join(sorted(closes[i - 1]))
            if gates:
                tail += "   GATE " + ", ".join(gates)
            print(f"wave {i:>2}  ({len(w)} tickets){tail}")
            for k in w[: a.limit]:
                g = blocked_reason(nodes[k])
                print(f"    {k}  {nodes[k]['title'][:62]}" + (f"   [{g}]" if g else ""))
            if len(w) > a.limit:
                print(f"    … and {len(w) - a.limit} more")
        return 0

    if a.cmd == "next":
        w = waves(nodes)
        if not w:
            print("nothing runnable"); return 0
        WIP = ("analysis", "in-progress", "review", "testing")
        wip = sorted(k for k, n in nodes.items() if n["stage"] in WIP and n["task_id"])
        if wip:
            print(f"IN FLIGHT ({len(wip)}) — finish or hand back before starting new work:")
            for k in wip:
                print(f"  {k}  [{nodes[k]['stage']}]  {nodes[k]['title'][:60]}")
            print()
        # a ticket already underway is not "ready" — offering it double-works it
        runnable = [k for k in w[0] if nodes[k]["task_id"]
                    and not blocked_reason(nodes[k]) and nodes[k]["stage"] not in WIP]
        held = [k for k in w[0] if blocked_reason(nodes[k])]
        print(f"READY ({len(runnable)}):")
        for k in runnable[: a.limit]:
            n = nodes[k]
            print(f"  {k}  [{n['effort']}]  {n['title']}")
            print(f"        {n['file']}")
        if held:
            print(f"\nHELD ({len(held)}):")
            for k in held:
                print(f"  {k}  {blocked_reason(nodes[k])}")
        return 0

    if a.cmd == "stats":
        per = defaultdict(int)
        for n in nodes.values():
            per[n["stage"]] += 1
        print("  ".join(f"{s}={per[s]}" for s in STAGES))
        leaves = [n for n in nodes.values() if n["task_id"]]
        print(f"epics={len(nodes)-len(leaves)}  leaves={len(leaves)}")
        print(f"waves={len(waves(nodes))}")
        return 0

    if a.cmd == "packet":
        if not a.ticket or a.ticket not in nodes:
            print(f"usage: graphloop packet <TICKET-ID>   (e.g. {sorted(nodes)[0]})", file=sys.stderr)
            return 2
        n = nodes[a.ticket]
        def section(name):
            m = re.search(rf"^#{{2,3}} {re.escape(name)}\n(.*?)(?=\n#{{2,3}} |\Z)", n["body"], re.S | re.M)
            return (m.group(1).strip() if m else "(none)")
        print(f"# REVIEW PACKET — {n['id']}: {n['title']}")
        print(f"\nTicket file: {n['file']}")
        print(f"Effort claimed: {n['effort']}   Type: {n['type']}   Stage: {n['stage']}")
        for name in ("Acceptance Criteria", "Testing Requirements", "Out of scope", "Related Files"):
            print(f"\n## {name}\n{section(name)}")
        import subprocess
        for label, cmd in (("Working-tree changes", ["git", "status", "--short"]),
                           ("Diff", ["git", "diff", "HEAD"])):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
            except Exception as e:
                out = f"(unavailable: {e})"
            print(f"\n## {label}\n{out or '(none)'}")
        return 0

    if a.cmd == "json":
        out = {"nodes": [{k: v for k, v in n.items() if k != "body"} for n in nodes.values()],
               "edges": [{"source": b, "target": n["id"], "type": "blocks"}
                         for n in nodes.values() for b in n["blocked_by"]]}
        print(json.dumps(out, indent=2))
        return 0
    return 0


def self_test() -> int:
    """One runnable check. Builds a synthetic board and asserts the four things
    that would silently reorder a real plan if they broke."""
    import tempfile, textwrap
    def tk(d, tid, task, status, deps, stage):
        (d / stage).mkdir(parents=True, exist_ok=True)
        (d / stage / f"{tid}-x.md").write_text(textwrap.dedent(f"""\
            # {tid}: probe
            **Status**: {status}
            **Type**: FEATURE
            **Task ID**: {task}

            ### Dependencies
            - {deps}
            """))
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "kanban"
        tk(d, "T-001", "001-T1", "BACKLOG", "none.",                    "backlog")
        tk(d, "T-002", "001-T2", "BACKLOG", "Needs 001-T1.",            "backlog")
        tk(d, "T-003", "001-T3", "BACKLOG", "Needs 001-T1 through T2.", "backlog")
        tk(d, "T-004", "001-T4", "BACKLOG", "Blocks 001-T1.",           "backlog")
        tk(d, "T-009", "001-T9", "BACKLOG", "Affects 001-T1.",          "backlog")
        tk(d, "T-005", "001-T5", "ONGOING", "none.",                    "in-progress")
        n = parse(d)
        assert not validate(n), validate(n)
        assert n["T-002"]["blocked_by"] == ["T-001"], "plain 'Needs' edge"
        assert n["T-003"]["blocked_by"] == ["T-001", "T-002"], \
            f"range must expand, got {n['T-003']['blocked_by']}"
        assert n["T-004"]["blocked_by"] == [], \
            f"'Blocks' is downstream, not a dependency, got {n['T-004']['blocked_by']}"
        assert n["T-009"]["blocked_by"] == [], \
            f"a bare mention ('Affects') is not a dependency, got {n['T-009']['blocked_by']}"
        w = waves(n)
        assert "T-001" in w[0] and "T-003" in w[2], f"topological order wrong: {w}"

        # a cycle must be caught, not silently truncate the plan
        tk(d, "T-006", "001-T6", "BACKLOG", "Needs 001-T7.", "backlog")
        tk(d, "T-007", "001-T7", "BACKLOG", "Needs 001-T6.", "backlog")
        assert any("cycle" in e for e in validate(parse(d))), "cycle not detected"

        # status/stage disagreement must fail validation
        tk(d, "T-008", "001-T8", "DONE", "none.", "backlog")
        assert any("Status DONE" in e for e in validate(parse(d))), "stage/status drift"
    print("self-test ok — edges, ranges, direction, ordering, cycles, stage drift")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())

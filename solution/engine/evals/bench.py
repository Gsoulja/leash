"""Benchmark: run every approach over the same 45 purchases and compare them.

    uv run python -m evals.bench                      # compare all registered approaches
    uv run python -m evals.bench regex blind          # just these
    uv run python -m evals.bench --json bench.json

There is no score to maximise, because the pack ships no expected verdicts. What a run does give is
three things you can act on: how much friction an approach removes (step_ups it avoids), how many
facts it establishes, and whether it is ever *less strict* than the reference — which for anything
that only changes fact reading is a defect, not a trade-off.
"""

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import DATA  # noqa: E402  (also puts the test fixtures on the path)
from evals.approaches import APPROACHES, REFERENCE, Approach  # noqa: E402
from evals.checks import Row, _digest, table  # noqa: E402
from evals.claims import Claim  # noqa: E402

from leash.adapters.pack.loader import Pack  # noqa: E402
from leash.adapters.regex_reader import RegexReader  # noqa: E402

STRICT = {"approve": 0, "step_up": 1, "decline": 2}
HISTORY = Path(__file__).resolve().parent / "benchmark-history.jsonl"


@dataclass(frozen=True)
class Measurement:
    approach: str
    description: str
    verdicts: Counter
    facts: dict[str, int]      # how many of the 45 purchases have each fact established
    deterministic: bool
    ms_per_purchase: float
    digest: str
    safety_gate: bool
    stricter: tuple[str, ...] = ()
    looser: tuple[str, ...] = ()

    @property
    def breached(self) -> bool:
        return self.safety_gate and bool(self.looser)

    def as_dict(self) -> dict[str, Any]:
        return {"approach": self.approach, "description": self.description, "verdicts": dict(self.verdicts),
                "facts_established": self.facts, "deterministic": self.deterministic,
                "ms_per_purchase": round(self.ms_per_purchase, 3), "digest": self.digest,
                "safety_gate": self.safety_gate, "stricter": list(self.stricter), "looser": list(self.looser),
                "breached": self.breached}


def _facts_established(pack: Pack, approach: Approach) -> dict[str, int]:
    """What the reader could actually establish. `None` means the fact is missing, never permission."""
    reader, budget = approach.reader(), _Budget()
    counts = Counter()
    for attempt in pack.attempts():
        f = reader.read(attempt.purchase, budget)
        counts["size"] += f.sizes is not None
        counts["return_days"] += f.return_days is not None
        counts["final_sale"] += f.final_sale is not None
        counts["injection"] += f.injection_excerpt is not None
        counts["addons"] += bool(f.addon_lines)
    return dict(counts)


class _Budget:
    def remaining_seconds(self) -> float:
        return 1.0


def measure(pack: Pack, approach: Approach, reference: Sequence[Row] | None = None) -> Measurement:
    reader = approach.reader()
    started = time.perf_counter()
    rows = table(pack, approach.mandates, reader)
    elapsed = time.perf_counter() - started
    again = table(pack, approach.mandates, approach.reader())
    base = {r.authorization_id: r.verdict for r in (reference or rows)}
    stricter = tuple(r.authorization_id for r in rows if STRICT[r.verdict] > STRICT[base[r.authorization_id]])
    looser = tuple(r.authorization_id for r in rows if STRICT[r.verdict] < STRICT[base[r.authorization_id]])
    return Measurement(approach.name, approach.description, Counter(r.verdict for r in rows),
                       _facts_established(pack, approach), deterministic=rows == again,
                       ms_per_purchase=elapsed * 1000 / max(len(rows), 1), digest=_digest(rows),
                       safety_gate=approach.safety_gate, stricter=stricter, looser=looser)


def run(pack: Pack | None = None, names: Sequence[str] | None = None) -> list[Measurement]:
    pack = pack or Pack(DATA)
    names = list(names or APPROACHES)
    if REFERENCE not in names:
        names.insert(0, REFERENCE)
    reference_rows = table(pack, APPROACHES[REFERENCE].mandates, RegexReader())
    ordered = [REFERENCE] + [n for n in names if n != REFERENCE]
    return [measure(pack, APPROACHES[n], reference_rows) for n in ordered]


def to_markdown(results: Sequence[Measurement]) -> str:
    lines = ["| Approach | approve | step_up | decline | stricter | looser | facts read | determ. | ms/purchase |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: | ---: |"]
    for r in results:
        facts = sum(r.facts.values())
        looser = f"**{len(r.looser)}**" if r.breached else str(len(r.looser))
        lines.append(f"| `{r.approach}` | {r.verdicts['approve']} | {r.verdicts['step_up']} | "
                     f"{r.verdicts['decline']} | {len(r.stricter)} | {looser} | {facts} | "
                     f"{'yes' if r.deterministic else 'NO'} | {r.ms_per_purchase:.2f} |")
    lines += ["", "`stricter`/`looser` count purchases whose verdict moved against the `regex` reference.",
              "A **bold** looser count is a safety breach: a reader that adds facts on top of the reference may",
              "never soften a verdict (DEC-009). Approaches that read less, or that change the customer's",
              "uncertainty policy, are measured but not gated — being looser there is correct, not a defect."]
    return "\n".join(lines)


def safety_claim(results: Sequence[Measurement]) -> Claim:
    """E-07, kept here rather than in checks.py so the claim set never has to import a benchmark."""
    breaches = [r for r in results if r.breached]
    nondeterministic = [r.approach for r in results if not r.deterministic]
    evidence = [f"`{r.approach}`: {r.verdicts['approve']} approve / {r.verdicts['step_up']} step_up / "
                f"{r.verdicts['decline']} decline · {len(r.stricter)} stricter, {len(r.looser)} looser than "
                f"`{REFERENCE}` · {sum(r.facts.values())} facts read · {r.ms_per_purchase:.2f} ms/purchase"
                for r in results]
    evidence += [f"SAFETY BREACH — `{r.approach}` is looser on: {', '.join(r.looser)}" for r in breaches]
    evidence += [f"NOT DETERMINISTIC — `{a}` gave different verdicts on a repeat run" for a in nondeterministic]
    return Claim(
        "E-07", "No approach that only changes fact reading is ever less strict than the reference",
        "fail" if breaches or nondeterministic else "pass",
        f"{len(results)} approaches compared, {len(breaches)} safety breaches",
        evidence=tuple(evidence), detail={"results": [r.as_dict() for r in results]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("approaches", nargs="*", choices=[*APPROACHES, []], help="default: all registered")
    parser.add_argument("--json", type=Path, help="write the full measurements here")
    parser.add_argument("--no-history", action="store_true", help="do not append this run to the history file")
    args = parser.parse_args()

    results = run(names=args.approaches or None)
    print(to_markdown(results))
    if args.json:
        args.json.write_text(json.dumps([r.as_dict() for r in results], indent=2) + "\n")
    if not args.no_history:
        stamp = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": [r.as_dict() for r in results]}
        with HISTORY.open("a") as f:
            f.write(json.dumps(stamp) + "\n")
        print(f"\nAppended to {HISTORY.name}; every run is kept so approaches can be compared over time.")
    claim = safety_claim(results)
    if claim.status == "fail":
        print("\n".join(line for line in claim.evidence if line.startswith(("SAFETY", "NOT"))), file=sys.stderr)
    return 1 if claim.status == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())

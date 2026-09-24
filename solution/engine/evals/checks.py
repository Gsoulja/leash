"""The checks that produce claims. Each one reuses the engine or the existing test suites; none of
them re-implements a rule, so an eval can never disagree with the code it is evaluating."""

import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evals import DATA, ENGINE

BASELINE = Path(__file__).resolve().parent / "baseline.json"

from fixtures.mandates import MANDATES  # noqa: E402

from leash.adapters.pack.loader import Pack  # noqa: E402
from leash.application.replay import InMemoryLedger, replay  # noqa: E402
from leash.domain import mandate as m  # noqa: E402
from leash.domain.mandate import CompiledMandate  # noqa: E402
from leash.policy.registry import REGISTRY  # noqa: E402
from leash.ports.fact_reader import FactReader  # noqa: E402

from evals.claims import Claim  # noqa: E402

# Suites that need no database; the eval reports their result rather than restating their assertions.
OFFLINE_SUITES = ("tests/domain", "tests/policy", "tests/property", "tests/application", "tests/contracts")

# Each entry is a decision we made, not a rule Viseca handed us, paired with the mandate fields that
# carry it. Dropping those fields shows how much of the outcome rests on that one assumption.
ASSUMPTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("DEC-013", "Singular wording means buy it once", (m.F_MAX_PURCHASES, m.F_MAX_QUANTITY)),
    ("DEC-014", '"A shop I use regularly" = 3 earlier approved purchases', (m.F_PRIOR_PURCHASES,)),
    ("DEC-022", '"For delivery" is an enforceable fulfilment rule', (m.F_FULFILLMENT,)),
    ("DEC-024", "Session risk scoring v1", (m.F_SESSION_RISK,)),
    ("DEC-023", "Split-order detection is on", (m.F_SPLIT_CHECK,)),
)


@dataclass(frozen=True)
class Row:
    scenario: str
    authorization_id: str
    verdict: str
    reasons: tuple[str, ...]
    checks: tuple[tuple[str, str], ...]  # (check key, status)
    alerts: tuple[str, ...]


def table(pack: Pack, mandates: Mapping[str, CompiledMandate] = MANDATES,
          reader: "FactReader | None" = None) -> list[Row]:
    """Every pack purchase replayed in order, with the full decision behind each verdict."""
    rows: list[Row] = []
    for scenario in sorted(mandates):
        ledger = InMemoryLedger()
        replayed = replay(pack, scenario, mandates[scenario], ledger=ledger, reader=reader)
        for r, recorded in zip(replayed, ledger.decisions, strict=True):
            d = recorded.decision
            rows.append(Row(scenario, r.authorization_id, d.verdict, d.reason_codes,
                            tuple((c.key, c.status) for c in d.checks), d.alerts))
    return rows


def _verdicts(rows: Sequence[Row]) -> dict[str, dict[str, object]]:
    return {r.authorization_id: {"verdict": r.verdict, "reasons": list(r.reasons)} for r in rows}


def _digest(rows: Sequence[Row]) -> str:
    return hashlib.sha256(json.dumps(_verdicts(rows), sort_keys=True).encode()).hexdigest()[:16]


# ----- E-01: the same inputs always give the same answer -------------------------------------------

def determinism(pack: Pack) -> Claim:
    runs = [table(pack) for _ in range(3)]
    same = all(r == runs[0] for r in runs[1:])
    return Claim(
        "E-01", "The engine is deterministic: identical inputs always produce identical verdicts",
        "pass" if same else "fail",
        f"3 independent replays agree on all {len(runs[0])} purchases" if same else "replays disagreed",
        evidence=(f"Verdict-table digest: `{_digest(runs[0])}`",
                  "No clock, database or model call takes part in `decide()`; it is a pure function.",
                  "A disagreement here would mean hidden state leaked into the domain."),
        detail={"digest": _digest(runs[0]), "replays": len(runs)})


# ----- E-02: nothing moved since the recorded baseline ---------------------------------------------

def baseline(pack: Pack) -> Claim:
    rows = table(pack)
    current = _verdicts(rows)
    if not BASELINE.exists():
        return Claim("E-02", "Every verdict is pinned to a recorded baseline", "info",
                     "no baseline recorded yet — run `--update-baseline`",
                     evidence=("A baseline freezes all 45 verdicts so an unintended change shows as a diff.",))
    saved = json.loads(BASELINE.read_text())["purchases"]
    changed = sorted(k for k in set(saved) | set(current) if saved.get(k) != current.get(k))
    lines = [f"`{k}`: {saved.get(k, {}).get('verdict', '—')} → {current.get(k, {}).get('verdict', '—')}"
             for k in changed]
    return Claim(
        "E-02", "Every verdict is pinned to a recorded baseline", "pass" if not changed else "fail",
        f"{len(current) - len(changed)}/{len(current)} purchases unchanged",
        evidence=tuple(lines) or ("No verdict or reason code changed since the baseline was recorded.",),
        detail={"changed": changed})


# ----- E-03: the engine is not simply blocking everything ------------------------------------------

def friction(pack: Pack) -> Claim:
    rows = table(pack)
    overall = Counter(r.verdict for r in rows)
    per = {s: Counter(r.verdict for r in rows if r.scenario == s) for s in sorted({r.scenario for r in rows})}
    lines = [f"`{s}`: " + ", ".join(f"{c[v]} {v}" for v in ("approve", "step_up", "decline")) for s, c in per.items()]
    return Claim(
        "E-03", "Ordinary purchases are not blocked: the verdict mix is reported, never assumed", "info",
        ", ".join(f"{overall[v]} {v}" for v in ("approve", "step_up", "decline")) + f" of {len(rows)}",
        evidence=tuple(lines) + (
            "There is no expected-verdict column in the pack, so this is a measurement, not a score.",
            "It exists so that a change which quietly raises the block rate is visible.",),
        detail={"overall": dict(overall), "per_scenario": {s: dict(c) for s, c in per.items()}})


# ----- E-04: no part of the rule surface is untested dead code -------------------------------------

def coverage(pack: Pack) -> Claim:
    rows = table(pack)
    in_mandates = {r.field for mandate in MANDATES.values() for r in mandate.rules}
    fired = {key for r in rows for key, _ in r.checks}
    reasons = sorted({code for r in rows for code in r.reasons})
    unexercised = sorted(set(REGISTRY) - in_mandates)
    return Claim(
        "E-04", "Every rule field the engine advertises is exercised by a real purchase",
        "pass" if not unexercised else "info",
        f"{len(in_mandates)}/{len(REGISTRY)} registry fields used · {len(fired)} checks fired · "
        f"{len(reasons)} distinct reason codes",
        evidence=(f"Checks that ran at least once: {', '.join(sorted(fired))}.",
                  f"Reason codes observed: {', '.join(reasons)}.",
                  (f"Registry fields no scenario exercises: {', '.join(unexercised)}." if unexercised
                   else "No registry field is left unexercised.")),
        detail={"registry_fields": sorted(REGISTRY), "used": sorted(in_mandates),
                "unexercised": unexercised, "checks_fired": sorted(fired), "reason_codes": reasons})


# ----- E-05: the safety invariants hold, reported from the suites that prove them -------------------

def _junit(paths: Sequence[str]) -> tuple[int, int, list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "report.xml"
        subprocess.run([sys.executable, "-m", "pytest", *paths, "-q", f"--junitxml={xml}"],
                       cwd=ENGINE, capture_output=True, text=True, timeout=1800)
        if not xml.exists():
            return 0, 0, ["the test run produced no report"]
        cases = list(ET.parse(xml).getroot().iter("testcase"))
        bad = [f"{c.get('classname')}::{c.get('name')}" for c in cases
               if c.find("failure") is not None or c.find("error") is not None]
        return len(cases), len(cases) - len(bad), bad


def invariants() -> Claim:
    total, passed, bad = _junit(list(OFFLINE_SUITES))
    return Claim(
        "E-05", "A model, a mandate change or merchant text can never loosen a verdict",
        "pass" if total and not bad else "fail", f"{passed}/{total} offline tests passed",
        evidence=tuple(f"FAILED {name}" for name in bad) or (
            "Tightening a mandate never makes any of the 45 verdicts less strict.",
            "Model-supplied facts never make a verdict less strict than the deterministic one.",
            "Merchant text never changes the status of a limit check.",
            "A mandate rule the engine cannot evaluate never approves.",
            f"Proven by the seeded property suite and the domain rules under {', '.join(OFFLINE_SUITES)}.",),
        detail={"suites": list(OFFLINE_SUITES), "tests": total, "passed": passed, "failures": bad})


# ----- E-06: what rests on our own assumptions rather than on the brief -----------------------------

def _without(mandate: CompiledMandate, fields: Sequence[str]) -> CompiledMandate:
    return dataclasses.replace(mandate, rules=tuple(r for r in mandate.rules if r.field not in fields))


def _swap_policy(mandate: CompiledMandate, uncertainty: str) -> CompiledMandate:
    return dataclasses.replace(mandate, uncertainty=uncertainty)


def _moved(pack: Pack, base: Mapping[str, Row], variant: Mapping[str, CompiledMandate]) -> tuple[list[str], int]:
    """Purchases whose verdict changes, and how many have a different explanation (verdict or reasons)."""
    rows = table(pack, variant)
    verdicts = [r.authorization_id for r in rows if r.verdict != base[r.authorization_id].verdict]
    explained = sum(1 for r in rows if (r.verdict, r.reasons) != (base[r.authorization_id].verdict,
                                                                 base[r.authorization_id].reasons))
    return verdicts, explained


def sensitivity(pack: Pack) -> Claim:
    base = {r.authorization_id: r for r in table(pack)}
    lines, detail = [], {}
    for dec, description, fields in ASSUMPTIONS:
        moved, explained = _moved(pack, base, {s: _without(mand, fields) for s, mand in MANDATES.items()})
        lines.append(f"**{dec}** — {description}: decides {len(moved)}/{len(base)} verdicts, "
                     f"and appears in {explained} explanations.")
        detail[dec] = {"description": description, "fields": list(fields), "verdicts_controlled": len(moved),
                       "explanations_affected": explained, "purchases": moved}
    for policy in ("approve", "decline"):
        moved, explained = _moved(pack, base, {s: _swap_policy(mand, policy) for s, mand in MANDATES.items()})
        lines.append(f"**Uncertainty policy** set to `{policy}` instead of `ask`: moves {len(moved)}/{len(base)}.")
        detail[f"uncertainty:{policy}"] = {"verdicts_controlled": len(moved), "explanations_affected": explained,
                                           "purchases": moved}
    top = max(detail[d]["verdicts_controlled"] for d, *_ in ASSUMPTIONS)  # type: ignore[index]
    return Claim(
        "E-06", "Every verdict that rests on our own assumption rather than the brief is declared", "info",
        f"the largest single assumption controls {top}/{len(base)} verdicts",
        evidence=tuple(lines) + (
            "Each row re-runs all 45 purchases with that assumption removed and counts what moves.",
            "A verdict can survive an assumption being wrong and still lose the reason it was explained with.",
            "These are the questions whose answers would change the most, listed in `docs/decisions.md`.",),
        detail=detail)


def all_claims(pack: Pack | None = None, *, run_suites: bool = True) -> list[Claim]:
    pack = pack or Pack(DATA)
    claims = [determinism(pack), baseline(pack), friction(pack), coverage(pack), sensitivity(pack)]
    if run_suites:
        claims.append(invariants())
    return sorted(claims, key=lambda c: c.id)


def write_baseline(pack: Pack | None = None) -> int:
    rows = table(pack or Pack(DATA))
    BASELINE.write_text(json.dumps({"digest": _digest(rows), "purchases": _verdicts(rows)}, indent=2) + "\n")
    return len(rows)

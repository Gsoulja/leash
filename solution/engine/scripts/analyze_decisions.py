"""Measure decision-layer contribution on the supplied pack, without changing the engine.

Run from solution/engine: .venv/bin/python scripts/analyze_decisions.py > report.json
Uses hand-compiled fixture mandates; no human answers, live service, or model calls.
"""

import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "tests"))

from fixtures.mandates import MANDATES
from leash.adapters.pack.loader import Pack
from leash.adapters.regex_reader import RegexReader
from leash.application.replay import InMemoryLedger, replay
from leash.domain.decide import DEFAULT_RULES, decide
from leash.domain.rules.period import period_rule
from leash.domain.rules.price import price_rule
from leash.domain.snapshot import Snapshot


class Budget:
    def remaining_seconds(self):
        return 60.0


def summarize(rows):
    return {
        "count": len(rows),
        "verdicts": dict(Counter(r["verdict"] for r in rows)),
        "amount_chf": {
            verdict: str(sum((Decimal(r["chf"]) for r in rows if r["verdict"] == verdict), Decimal("0.00")))
            for verdict in ("approve", "step_up", "decline")
        },
    }


def run():
    pack = Pack(ENGINE.parents[1] / "data")
    reader = RegexReader()
    names = {mid: m.name for mid, m in pack.merchants().items()}
    states = {"approve": "approved", "decline": "declined", "step_up": "waiting"}
    variants = {
        "full": DEFAULT_RULES,
        "allow_all": (),
        "money_only": (price_rule, period_rule),
        **{f"without:{rule.__name__}": tuple(r for r in DEFAULT_RULES if r != rule)
           for rule in DEFAULT_RULES},
    }
    # Fixed-snapshot comparisons isolate a check's immediate contribution; independent
    # sequential replays additionally include effects on later approvals and spend.
    rows_by_variant = {name: [] for name in variants}
    direct = {rule.__name__: {"findings": [], "verdict_changes": [], "new_approvals": []}
              for rule in DEFAULT_RULES}
    injection_probes = []
    for scenario, mandate in sorted(MANDATES.items()):
        ledgers = {name: InMemoryLedger() for name in variants}
        for attempt in pack.attempts(scenario):
            p = attempt.purchase
            facts = reader.read(p, Budget())
            full_snapshot = Snapshot(p.card_id, pack.baseline(p.card_id), ledgers["full"].prior(p.card_id), None, names)
            full = decide(p, mandate, full_snapshot, facts)
            if facts.injection_excerpt is not None:
                # Counterfactual: this same attempt arrives first in its run. Historical
                # familiarity remains; prior-run approvals no longer mask the text check.
                first = replace(full_snapshot, prior=())
                with_text = decide(p, mandate, first, facts)
                without_text = decide(p, mandate, first, facts, variants["without:shop_text_rule"])
                injection_probes.append({"id": p.authorization_id, "chf": str(p.billing_amount_chf),
                                         "with_text_check": with_text.verdict,
                                         "without_text_check": without_text.verdict,
                                         "reasons": list(with_text.reason_codes)})
            for rule in DEFAULT_RULES:
                entry = direct[rule.__name__]
                if any(c.status in ("warn", "fail", "integrity") for c in rule(p, mandate, full_snapshot, facts)):
                    entry["findings"].append(p.authorization_id)
                dropped = decide(p, mandate, full_snapshot, facts, variants[f"without:{rule.__name__}"])
                if dropped.verdict != full.verdict:
                    entry["verdict_changes"].append(p.authorization_id)
                if dropped.verdict == "approve" and full.verdict != "approve":
                    entry["new_approvals"].append(p.authorization_id)
            for name, rules in variants.items():
                ledger = ledgers[name]
                snapshot = Snapshot(p.card_id, pack.baseline(p.card_id), ledger.prior(p.card_id), None, names)
                decision = decide(p, mandate, snapshot, facts, rules)
                ledger.record(p, decision, states[decision.verdict])
                rows_by_variant[name].append({
                    "scenario": scenario, "id": p.authorization_id, "shop": p.merchant.name,
                    "chf": str(p.billing_amount_chf), "verdict": decision.verdict,
                    "reasons": list(decision.reason_codes),
                    "findings": [{"key": c.key, "status": c.status, "agreed": c.agreed,
                                  "actual": c.actual, "reason": c.reason_code}
                                 for c in decision.checks if c.status in ("warn", "fail", "integrity")],
                })

    full_rows = rows_by_variant["full"]
    base = {r["id"]: r for r in full_rows}
    # Runnable consistency check against the existing replay, including amounts/reasons.
    expected = [r for scenario, mandate in sorted(MANDATES.items()) for r in replay(pack, scenario, mandate)]
    assert [(r["id"], r["verdict"], tuple(r["reasons"]), Decimal(r["chf"])) for r in full_rows] == [
        (r.authorization_id, r.verdict, r.reasons, r.chf) for r in expected]
    assert len(base) == len(pack.attempts()) == 45
    assert all(r["verdict"] == "approve" for r in rows_by_variant["allow_all"])
    total = sum((Decimal(r["chf"]) for r in full_rows), Decimal("0.00"))
    for rows in rows_by_variant.values():
        assert sum((Decimal(v) for v in summarize(rows)["amount_chf"].values()), Decimal("0.00")) == total

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "45 fixed supplied attempts; fixture mandates; regex; asks remain waiting. Each variant starts a fresh ledger per scenario. Direct rule removal holds the full-run snapshot fixed. Amounts are attempted authorizations, not saved money.",
        "checks": "Replay parity, unique IDs, allow-all control, and amount conservation passed.",
        "scenarios": {s: summarize([r for r in full_rows if r["scenario"] == s]) for s in sorted(MANDATES)},
        "variants": {name: {**summarize(rows), "changed": [r["id"] for r in rows if r["verdict"] != base[r["id"]]["verdict"]],
                            "new_approvals": [r["id"] for r in rows if r["verdict"] == "approve" and base[r["id"]]["verdict"] != "approve"],
                            "rows": rows} for name, rows in rows_by_variant.items()},
        "direct_rule_contribution": direct,
        "injection_as_first_attempt": injection_probes,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

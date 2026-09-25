"""Live full-reader diagnostic, without payments. Uses OPENROUTER_API_KEY from the environment.

PYTHONPATH=src:tests .venv/bin/python -m evals.jev --output ../../output/jev-full-reader.json
"""

import argparse
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from factories import line, purchase
from leash.adapters.jev import JevClient, JevReader


CASES = [
    ("size-days", "Running shoes, size 43. Returns within 14 days.", ("43",), 14, False),
    ("decimal-de", "Schuhe, Grösse 43,5. Rückgabe innerhalb von 30 Tagen.", ("43,5",), 30, False),
    ("words", "Shirt, selected size medium. Returns within two weeks.", ("M",), 14, False),
    ("final-sale", "Jacket, size XL. Final sale, no returns.", ("XL",), None, True),
    ("absent", "A blue ceramic bowl.", None, None, None),
    ("irrelevant-numbers", "Model 43 costs CHF 14. Delivery within 7 days. Warranty 30 days.", None, None, None),
    ("selected-size", "Available in sizes 41, 42, 43. Selected size 42. Returns within 21 days.", ("42",), 21, False),
    ("negated-size", "This is size 42, not size 43. Returns accepted within 14 days.", ("42",), 14, False),
    ("french", "Chaussures, taille 39. Retours sous 30 jours.", ("39",), 30, False),
    ("literal-days", "Size S. Returns accepted within 17 days.", ("S",), 17, False),
    ("shortest-window", "Size L. General returns within 30 days; this item only 14 days.", ("L",), 14, False),
    ("unknown-duration", "Size M. Returns within one calendar month.", "step_up", None, None),
]


class Budget:
    def remaining_seconds(self):
        return 1.0


def run(env):
    reader = JevReader(JevClient(env))
    rows = []
    for name, text, sizes, days, final_sale in CASES:
        start = time.perf_counter()
        row = {"id": name, "text": text,
               "expected": {"sizes": sizes, "return_days": days, "final_sale": final_sale}}
        try:
            facts = reader.read(purchase(items=(line(details=text),)), Budget())
            row["actual"] = asdict(facts)
            row["correct"] = (facts.sizes == sizes and facts.return_days == days
                              and facts.final_sale == final_sale)
        except Exception as exc:
            # Only an explicit unsupported fact passes the uncertainty case, not an outage.
            row["error"] = type(exc).__name__
            row["correct"] = sizes == "step_up" and str(exc) == "Jev cannot extract an exact fact"
        row["ms"] = round((time.perf_counter() - start) * 1000, 2)
        rows.append(row)
    return {"model": reader.client.model, "cases": rows,
            "passed": sum(r["correct"] for r in rows), "total": len(rows),
            "scope": "Authored integration diagnostics, not production accuracy or an independent model comparison."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(os.environ)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=list) + "\n")
    print(f"{report['passed']}/{report['total']} diagnostics passed; {args.output}")

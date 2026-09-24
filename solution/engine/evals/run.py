"""Run the evaluation and write the report.

    uv run python -m evals.run                     # print the report, exit non-zero on a failed claim
    uv run python -m evals.run --json out.json     # machine-readable, for CI or the judges' pack
    uv run python -m evals.run --markdown REPORT.md
    uv run python -m evals.run --update-baseline   # re-record the 45 verdicts after an intended change
    uv run python -m evals.run --fast              # skip the pytest suites (E-05)

Comparing approaches is `python -m evals.bench`; this runner only reports its safety verdict (E-07).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `python evals/run.py` works too

from evals.bench import run as run_benchmark, safety_claim  # noqa: E402
from evals.checks import all_claims, write_baseline  # noqa: E402
from evals.claims import render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=Path, help="write the machine-readable report here")
    parser.add_argument("--markdown", type=Path, help="write the human-readable report here")
    parser.add_argument("--update-baseline", action="store_true", help="re-record the verdict baseline and stop")
    parser.add_argument("--fast", action="store_true", help="skip the pytest suites behind E-05")
    parser.add_argument("--no-benchmark", action="store_true", help="skip the approach comparison behind E-07")
    args = parser.parse_args()

    if args.update_baseline:
        print(f"baseline recorded: {write_baseline()} purchases")
        return 0

    claims = all_claims(run_suites=not args.fast)
    if not args.no_benchmark:
        claims.append(safety_claim(run_benchmark()))
    report = render(sorted(claims, key=lambda c: c.id))
    if args.json:
        args.json.write_text(report.to_json())
    if args.markdown:
        args.markdown.write_text(report.to_markdown())
    if not args.json and not args.markdown:
        print(report.to_markdown())
    for claim in report.failed:
        print(f"FAILED {claim.id}: {claim.claim}", file=sys.stderr)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())

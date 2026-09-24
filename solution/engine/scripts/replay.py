"""Replay challenge scenarios offline and print each decision.

    uv run python scripts/replay.py SCEN0004
    uv run python scripts/replay.py --answers approve SCEN0001 SCEN0004
    uv run python scripts/replay.py --answers AU0040=approve,AU0041=decline SCEN0004
"""

import argparse
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "tests"))  # the hand-compiled scenario mandates (LEASH-031) live with the tests

from fixtures.mandates import MANDATES  # noqa: E402

from leash.adapters.pack.loader import Pack  # noqa: E402
from leash.application.replay import Answers, format_rows, replay  # noqa: E402

DATA = ENGINE.parents[1] / "data"


def parse_answers(text: str) -> Answers:
    if text in ("none", "approve", "decline"):
        return text  # type: ignore[return-value]
    out = {}
    for part in text.split(","):
        aid, _, answer = part.partition("=")
        if not aid.strip() or answer not in ("approve", "decline"):
            raise argparse.ArgumentTypeError(f"bad answer {part!r}: use ID=approve or ID=decline")
        out[aid.strip()] = answer
    return out  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenarios", nargs="*", default=sorted(MANDATES), help="scenario IDs (default: all)")
    parser.add_argument("--answers", type=parse_answers, default="none",
                        help="customer answers to step_up: none | approve | decline | ID=approve,ID=decline")
    args = parser.parse_args()
    pack = Pack(DATA)
    for scenario in args.scenarios:
        if scenario not in MANDATES:
            parser.error(f"unknown scenario {scenario}; known: {', '.join(sorted(MANDATES))}")
        print(f"\n{scenario}: {MANDATES[scenario].instruction}")
        print(format_rows(replay(pack, scenario, MANDATES[scenario], answers=args.answers)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

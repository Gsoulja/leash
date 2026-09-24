"""Evidence-based evaluation of the decision engine (LEASH-128).

Not an accuracy score: the challenge pack ships inputs only, with no expected verdicts, so there is
no ground truth to score against. Instead each check produces a Claim — a statement about the engine
a judge can check, with the numbers behind it. `bench` then runs the same measurements per approach.
"""

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
DATA = ENGINE.parents[1] / "data"
if str(ENGINE / "tests") not in sys.path:
    sys.path.insert(0, str(ENGINE / "tests"))  # the hand-compiled scenario mandates live with the tests

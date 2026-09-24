"""The eval harness itself (LEASH-128). It must not run the pytest suites from inside pytest, so
every test here uses the offline claims only."""

import dataclasses
import json
from pathlib import Path

import pytest

from evals import bench
from evals.approaches import APPROACHES, REFERENCE, Approach
from evals.checks import ASSUMPTIONS, all_claims, baseline, determinism, table
from evals.claims import render
from leash.adapters.pack.loader import Pack
from leash.adapters.regex_reader import RegexReader

DATA = Path(__file__).resolve().parents[3] / "data"


@pytest.fixture(scope="module")
def pack() -> Pack:
    return Pack(DATA)


def test_every_pack_purchase_appears_once(pack):
    rows = table(pack)
    assert len(rows) == 45
    assert len({r.authorization_id for r in rows}) == 45


def test_replaying_twice_gives_the_same_verdicts(pack):
    assert determinism(pack).status == "pass"


def test_verdicts_still_match_the_recorded_baseline(pack):
    claim = baseline(pack)
    assert claim.status == "pass", claim.evidence  # intended change? `uv run python -m evals.run --update-baseline`


def test_every_declared_assumption_is_measured(pack):
    detail = next(c for c in all_claims(pack, run_suites=False) if c.id == "E-06").detail
    assert {dec for dec, _, _ in ASSUMPTIONS} <= set(detail)
    assert all(d["verdicts_controlled"] <= 45 for d in detail.values())


def test_a_failed_claim_fails_the_report(pack):
    claims = all_claims(pack, run_suites=False)
    report = render(claims)
    assert not report.failed
    assert json.loads(report.to_json())["claims"]
    assert "Leash decision engine" in report.to_markdown()


# ----- the benchmark ------------------------------------------------------------------------------

def test_every_registered_approach_is_measured(pack):
    results = bench.run(pack)
    assert [r.approach for r in results][0] == REFERENCE  # the reference is always measured first
    assert {r.approach for r in results} == set(APPROACHES)
    assert all(sum(r.verdicts.values()) == 45 for r in results)


def test_reading_merchant_text_beats_reading_nothing(pack):
    by_name = {r.approach: r for r in bench.run(pack)}
    assert sum(by_name["blind"].facts.values()) == 0
    assert sum(by_name[REFERENCE].facts.values()) > 0
    assert by_name["blind"].verdicts["step_up"] > by_name[REFERENCE].verdicts["step_up"]  # less read, more asking


def test_registered_approaches_pass_the_safety_gate(pack):
    assert bench.safety_claim(bench.run(pack)).status == "pass"


def test_a_reader_that_loosens_a_verdict_is_caught(pack):
    """The gate must actually fire: a gated reader that finds a longer return window than the shop
    states would turn a decline into an approve, and that has to fail."""

    class Generous:
        def read(self, purchase, budget):
            return dataclasses.replace(RegexReader().read(purchase, budget),
                                       return_days=365, final_sale=False, sizes=("43",))

    cheat = Approach("cheat", "invents facts the merchant never stated", reader=Generous)
    result = bench.measure(pack, cheat, bench.table(pack, cheat.mandates, RegexReader()))
    assert result.looser and result.breached
    assert bench.safety_claim([result]).status == "fail"

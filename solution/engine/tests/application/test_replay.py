import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.mandates import MANDATES
from leash.adapters.pack.loader import Pack
from leash.application.replay import InMemoryLedger, format_rows, replay

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"


@pytest.fixture(scope="module")
def pack() -> Pack:
    return Pack(DATA)


def test_replay_records_one_decision_per_attempt(pack):
    ledger = InMemoryLedger()
    rows = replay(pack, "SCEN0001", MANDATES["SCEN0001"], ledger=ledger)
    attempts = pack.attempts("SCEN0001")
    assert [r.authorization_id for r in rows] == [a.purchase.authorization_id for a in attempts]
    assert len(ledger.decisions) == len(attempts)
    assert all(r.verdict in ("approve", "decline", "step_up") for r in rows)


def test_rows_carry_shop_amount_verdict_and_reasons(pack):
    [row] = replay(pack, "SCEN0000", MANDATES["SCEN0000"])
    assert (row.authorization_id, row.shop, str(row.chf)) == ("AU0001", pack.merchants()["ME0001"].name, "20.00")
    assert row.verdict == "approve" and row.reasons == () and row.final_state == "approved"
    text = format_rows([row])
    assert "AU0001" in text and "CHF 20.00" in text and "approve" in text


def test_scripted_answers_decide_what_a_step_up_becomes(pack):
    mandate = MANDATES["SCEN0004"]
    asked = [r for r in replay(pack, "SCEN0004", mandate) if r.verdict == "step_up"]
    assert asked, "SCEN0004 should ask the customer at least once"
    assert {r.final_state for r in asked} == {"waiting"}  # answers="none"
    for answers, state in (("approve", "approved"), ("decline", "declined")):
        rows = [r for r in replay(pack, "SCEN0004", mandate, answers=answers) if r.verdict == "step_up"]
        assert {r.final_state for r in rows} == {state}
    first = asked[0].authorization_id
    rows = replay(pack, "SCEN0004", mandate, answers={first: "approve"})
    by_id = {r.authorization_id: r for r in rows}
    assert by_id[first].final_state == "approved"
    assert all(r.final_state == "waiting" for r in rows if r.verdict == "step_up" and r.authorization_id != first)


def test_approved_answers_feed_later_decisions(pack):
    # Approving the CHF 65.00 possible split (AU0006) makes it spend: AU0008 then breaks the 7-day limit.
    unanswered = {r.authorization_id: r for r in replay(pack, "SCEN0001", MANDATES["SCEN0001"])}
    approved = {r.authorization_id: r for r in replay(pack, "SCEN0001", MANDATES["SCEN0001"],
                                                      answers={"AU0006": "approve"})}
    assert unanswered["AU0008"].verdict == "approve"
    assert approved["AU0006"].final_state == "approved"
    assert (approved["AU0008"].verdict, approved["AU0008"].reasons) == ("decline", ("over_period_limit",))


def test_declines_are_final_and_never_answered(pack):
    rows = replay(pack, "SCEN0004", MANDATES["SCEN0004"], answers="approve")
    assert all(r.final_state == "declined" for r in rows if r.verdict == "decline")


def test_unknown_scenario_is_an_error(pack):
    with pytest.raises(KeyError):
        replay(pack, "SCEN9999", MANDATES["SCEN0000"])


def test_script_runs():
    out = subprocess.run([sys.executable, "scripts/replay.py", "SCEN0004"], cwd=ENGINE, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "AU00" in out.stdout and "CHF" in out.stdout


@pytest.mark.parametrize("bad", ["=approve", "AU0040", "AU0040=yes", "bogus"])
def test_script_rejects_malformed_answers(bad):
    out = subprocess.run([sys.executable, "scripts/replay.py", "--answers", bad, "SCEN0004"], cwd=ENGINE,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 2 and "answer" in out.stderr

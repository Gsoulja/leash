"""LEASH-158: the connection check must recognise a finished run from the shape the live platform really sends
(unwrapped, no `counters`), not only from the fake platform's nested counters."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

from leash.adapters.viseca_api.client import BootstrapSettings

ENGINE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("connection_check", ENGINE / "scripts" / "connection_check.py")
connection_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(connection_check)

LIVE_RUNNING = {"run_id": "run_80e1be3d02000a35", "scenario_id": "SCEN0000", "mandate_id": "TMc14417b720aea7e3",
                "status": "running", "generated_event_count": 1, "delivered_event_count": 0,
                "finalized_event_count": 0, "processed_event_count": 0, "pending_event_count": 0,
                "queued_event_count": 1, "platform_rejected_count": 0}
#: What the platform reports per purchase once we answered it, and once it timed us out instead.
ANSWERED = [{"authorization_id": "AU10001-x", "source_authorization_id": "AU10001",
             "run_id": "run_80e1be3d02000a35", "status": "waiting_for_customer",
             "decision": {"decision": "step_up", "decision_source": "team"}}]
TIMED_OUT = [{"authorization_id": "AU10001-x", "source_authorization_id": "AU10001",
              "run_id": "run_80e1be3d02000a35", "status": "timeout",
              "decision": {"decision": "decline", "reason_codes": ["timeout"]}}]

LIVE_DONE = {**LIVE_RUNNING, "status": "completed", "delivered_event_count": 1, "finalized_event_count": 1,
             "processed_event_count": 1, "queued_event_count": 0}


#: The hosted pack numbers and words its scenarios differently from the practice pack: the check has to
#: read them from /v1/bootstrap rather than know an ID (LEASH-158).
LIVE_SCENARIOS = [
    {"scenario_id": "SCEN0135", "scenario_name": "Household budget", "event_count": 12,
     "cardholder_instruction": "Do the weekly grocery shopping online at supermarkets I already use."},
    {"scenario_id": "SCEN0101", "scenario_name": "Connection check", "event_count": 2,
     "cardholder_instruction": "Buy one ordinary grocery item for CHF 20 or less from a shop I use "
                               "regularly. Ask me when uncertain."},
]


class FakeClient:
    """Answers exactly like the hosted sandbox did on 2026-09-24 (solution/postman/apiCalls/08, /13)."""

    def __init__(self, *runs, scenarios=None, authorizations=None):
        self._runs = list(runs)
        self._scenarios = LIVE_SCENARIOS if scenarios is None else scenarios
        self._authorizations = ANSWERED if authorizations is None else authorizations

    async def list_authorizations(self):
        return self._authorizations

    async def bootstrap(self):
        return BootstrapSettings.parse({"api_version": "0.1.0", "pack_version": "saw26-hackaton-api",
                                        "scenarios": self._scenarios})

    async def create_mandate(self, body):
        return {"draft_id": "TDaaa"}

    async def confirm_mandate(self, draft_id):
        return {"mandate_id": "TMc14417b720aea7e3"}

    async def start_run(self, scenario_id, mandate_id):
        return {"run_id": "run_80e1be3d02000a35", "status": "running"}

    async def get_run(self, run_id):
        return self._runs.pop(0) if len(self._runs) > 1 else self._runs[0]


def test_live_shaped_completed_run_passes(capsys):
    assert asyncio.run(connection_check.check(FakeClient(LIVE_RUNNING, LIVE_DONE), timeout=5.0)) == 0
    assert "passed" in capsys.readouterr().out


def test_run_that_never_finishes_fails(capsys):
    assert asyncio.run(connection_check.check(FakeClient(LIVE_RUNNING), timeout=1.0)) == 1
    assert "FAILED" in capsys.readouterr().err


def test_run_that_ends_badly_fails(capsys):
    """A stopped or failed run is over, but the worker did not answer every purchase: that is not a pass."""
    assert asyncio.run(connection_check.check(FakeClient({**LIVE_DONE, "status": "failed"}), timeout=5.0)) == 1
    # the message must name the platform's status: the timeout path also returns 1, and would hide this
    assert "ended failed" in capsys.readouterr().err


def test_fake_platform_shape_still_passes(capsys):
    nested = {"data": {"run_id": "r1", "status": "completed",
                       "counters": {"total": 10, "final": 10, "decided": 10}}}
    assert asyncio.run(connection_check.check(FakeClient(nested), timeout=5.0)) == 0
    assert "passed" in capsys.readouterr().out


def test_the_scenario_comes_from_the_platform_not_from_an_id_we_know():
    """The shortest story is the connection check; `--scenario` still wins when it is given."""
    assert connection_check.connection_scenario(LIVE_SCENARIOS, None)["scenario_id"] == "SCEN0101"
    assert connection_check.connection_scenario(LIVE_SCENARIOS, "SCEN0135")["scenario_id"] == "SCEN0135"
    with pytest.raises(SystemExit):
        connection_check.connection_scenario(LIVE_SCENARIOS, "SCEN0000")  # a practice ID the platform lacks
    with pytest.raises(SystemExit):
        connection_check.connection_scenario([], None)


def test_a_completed_run_the_platform_timed_out_is_not_a_pass(capsys):
    """Measured live on 2026-09-25: every decision POST was refused (422), the platform timed both
    purchases out, and the run still reported `completed` with both events "finalized"."""
    client = FakeClient(LIVE_DONE, authorizations=TIMED_OUT)
    assert asyncio.run(connection_check.check(client, timeout=5.0)) == 1
    assert "never recorded our answer for AU10001" in capsys.readouterr().err


def test_a_run_the_platform_lists_no_purchases_for_is_not_a_pass(capsys):
    """The fake listed every row with `run_id: None`, so the per-purchase check matched nothing and
    passed on evidence it never saw. Finding nothing is unknown, not success."""
    assert asyncio.run(connection_check.check(FakeClient(LIVE_DONE, authorizations=[]), timeout=5.0)) == 1
    assert "lists no purchases" in capsys.readouterr().err

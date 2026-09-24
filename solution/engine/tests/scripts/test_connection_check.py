"""LEASH-158: the connection check must recognise a finished run from the shape the live platform really sends
(unwrapped, no `counters`), not only from the fake platform's nested counters."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("connection_check", ENGINE / "scripts" / "connection_check.py")
connection_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(connection_check)

LIVE_RUNNING = {"run_id": "run_80e1be3d02000a35", "scenario_id": "SCEN0000", "mandate_id": "TMc14417b720aea7e3",
                "status": "running", "generated_event_count": 1, "delivered_event_count": 0,
                "finalized_event_count": 0, "processed_event_count": 0, "pending_event_count": 0,
                "queued_event_count": 1, "platform_rejected_count": 0}
LIVE_DONE = {**LIVE_RUNNING, "status": "completed", "delivered_event_count": 1, "finalized_event_count": 1,
             "processed_event_count": 1, "queued_event_count": 0}


class FakeClient:
    """Answers exactly like the hosted sandbox did on 2026-09-24 (solution/postman/apiCalls/08, /13)."""

    def __init__(self, *runs):
        self._runs = list(runs)

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

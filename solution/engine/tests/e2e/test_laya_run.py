"""Opt-in real checkpoint → worker → PostgreSQL → fake platform experiment.

Set LEASH_LAYA_CHECKPOINT in an environment with the optional local Laya runtime.
"""

import asyncio
import json
import os
from collections import Counter
from pathlib import Path

import httpx
import pytest

from fake_api.app import FakeViseca
from fixtures.mandates import MANDATES
from leash.adapters.laya_reader import configured_reader
from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.unit_of_work import PostgresDecisionStore
from leash.adapters.viseca_api.client import VisecaClient
from leash.adapters.viseca_api.worker import ApiSender, Worker
from leash.application.decide_purchase import DecidePurchase
from leash.application.replay import replay
from resilience.test_resilience import DATA, PLAN, VALIDATE, percentile, seeded_pool, start, until


@pytest.mark.skipif(not os.environ.get("LEASH_LAYA_CHECKPOINT"), reason="real Laya checkpoint is opt-in")
def test_real_laya_decisions_reach_platform(test_database_url):
    reader = configured_reader({**os.environ, "LEASH_LAYA_MODE": "augment"})
    pack = Pack(DATA)
    reference = {r.authorization_id: r.verdict for scenario, mandate in MANDATES.items()
                 for r in replay(pack, scenario, mandate)}
    fake = FakeViseca(pack, api_key="k", repeat=["AU0002", "AU0036"])

    async def go():
        pool = await seeded_pool(test_database_url, pack)
        try:
            async with VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app)) as client:
                use_case = DecidePurchase(store=PostgresDecisionStore(pool, engine_version="laya-experiment"),
                                          reader=reader, sender=ApiSender(client), plan=PLAN,
                                          engine_version="laya-experiment", human_window_seconds=120)
                worker = Worker(client, use_case, validate=VALIDATE, poll_wait=1)
                polling = asyncio.create_task(worker.run())
                try:
                    for scenario in MANDATES:
                        run_id = await start(client, scenario)
                        assert await until(lambda: len(fake.runs[run_id].queued) == len(pack.attempts(scenario))
                                           and all(q.decision is not None for q in fake.runs[run_id].queued), 90)
                finally:
                    worker.stop()
                    await asyncio.wait_for(polling, 5)
                saved = await pool.fetch("select authorization_id, count(*) n from decision_events "
                                         "where kind = 'decided' group by authorization_id")
                readers = [json.loads(row["checks"])["reader"] for row in
                           await pool.fetch("select checks from authorizations")]
                return saved, readers
        finally:
            await pool.close()

    saved, readers = asyncio.run(go())
    queued = [q for run in fake.runs.values() for q in run.queued]
    strict = {"approve": 0, "step_up": 1, "decline": 2}
    rows = [{"source": q.attempt.purchase.authorization_id, "decision": q.decision,
             "regex": reference[q.attempt.purchase.authorization_id],
             "latency_s": (q.decided_at - q.queued_at).total_seconds()} for q in queued]
    latencies = [r["latency_s"] for r in rows]
    report = {"purchases": len(rows), "verdicts": dict(Counter(r["decision"] for r in rows)),
              "p95_s": percentile(latencies, .95), "max_s": max(latencies),
              "reader_cache": reader._primary._cached.cache_info()._asdict(),
              "readers": readers,
              "rows": rows, "received": fake.received}
    if os.environ.get("LEASH_LAYA_REPORT"):
        Path(os.environ["LEASH_LAYA_REPORT"]).write_text(json.dumps(report, indent=2) + "\n")
    assert len(queued) == len(saved) == 45 and all(row["n"] == 1 for row in saved)
    assert all(q.decided_at < q.deadline_at for q in queued)
    assert all(strict[r["decision"]] >= strict[r["regex"]] for r in rows)
    assert all(r == {"name": "laya+regex", "model_unavailable": False} for r in readers)
    assert reader._primary._cached.cache_info().misses > 1  # actual purchase inference occurred

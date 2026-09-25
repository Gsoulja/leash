"""The connection check (technical_details.md): confirm the mandate for the platform's own connection-check
scenario, start its run, and wait until the platform reports that run completed (it prints the platform's
own counts; it does not re-check them). The scenario and its wording come from /v1/bootstrap, so this works
on any pack. Run it against the fake platform only:

    LEASH_BASE_URL=http://localhost:9000 TEAM_API_KEY=fake-team-key uv run python scripts/connection_check.py

It refuses any other base URL unless --live is given, so it never starts a scored run by accident.
"""

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ENGINE = Path(__file__).resolve().parents[1]

from leash.adapters.viseca_api.client import VisecaClient  # noqa: E402
from leash.adapters.viseca_api.worker import run_over  # noqa: E402
from leash.application.reconcile import _rows
from leash.application.clarify import optional  # noqa: E402
from leash.policy.compiler import compile_instruction  # noqa: E402
from leash.policy.hard_rules import mandate_to_api  # noqa: E402
from leash.service import load_catalogue  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "fake"}
DATA = Path(os.environ.get("LEASH_DATA_DIR", str(ENGINE.parents[1] / "data")))


def connection_scenario(scenarios: Sequence[Mapping[str, Any]], wanted: str | None) -> Mapping[str, Any]:
    """The scenario to check, from the platform's own list — never a hard-coded ID.

    Without `--scenario`, the smallest one: the connection check is the shortest story in the pack
    (one or two purchases), and the practice and hosted packs number their scenarios differently.
    """
    if not scenarios:
        raise SystemExit("the platform listed no scenarios in /v1/bootstrap")
    if wanted:
        for s in scenarios:
            if s.get("scenario_id") == wanted:
                return s
        raise SystemExit(f"{wanted} is not in the platform's scenario list")
    return min(scenarios, key=lambda s: s.get("event_count") or 0)


async def check(client: VisecaClient, timeout: float, wanted: str | None = None,
                mandate_id: str | None = None) -> int:
    bootstrap = await client.bootstrap()
    scenario = connection_scenario(bootstrap.scenarios, wanted)
    scenario_id, instruction = str(scenario["scenario_id"]), str(scenario["cardholder_instruction"])
    print(f"{scenario_id}: {instruction}")
    if mandate_id is None:
        # Automatic confirmation is only for the explicit local fake. A live run reuses consent.
        if getattr(client, "base_url", "http://fake") and urlsplit(getattr(client, "base_url", "http://fake")).hostname not in LOCAL_HOSTS:
            raise SystemExit("live checks require --mandate-id from an already confirmed customer permission")
        draft = compile_instruction(instruction, catalogue=load_catalogue(DATA))
        if any(not optional(q) for q in draft.questions):
            raise SystemExit("resolve the mandate's blocking questions before running the check")
        body = {**mandate_to_api(draft.mandate), "guidance": [], "open_questions": []}
        created = await client.create_mandate(body)
        mandate_id = (await client.confirm_mandate(str(created["draft_id"])))["mandate_id"]
    else:
        held = await client.get_mandate(mandate_id)
        held = held.get("data", held)
        if held.get("status") != "active" or held.get("instruction") != instruction:
            raise SystemExit("the mandate must be active and retain the exact selected scenario instruction")
    run_id = (await client.start_run(scenario_id, str(mandate_id)))["run_id"]
    print(f"run {run_id} started with mandate {mandate_id}")
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        progress = await client.get_run(str(run_id))
        if run_over(progress):  # the live API sends no counters at all, only a top-level status (LEASH-158)
            body = progress.get("data", progress) if isinstance(progress, Mapping) else {}
            status = str(body.get("status", "over")).lower()
            counts = body.get("counters") or {k: v for k, v in body.items() if k.endswith("_count")}
            if status in ("completed", "finished"):
                unanswered = await _unanswered(client, str(run_id))
                if unanswered:  # a run completes even when the platform timed every purchase out
                    print(f"connection check FAILED: run {run_id} {status}, but the platform never "
                          f"recorded our answer for {', '.join(unanswered)}", file=sys.stderr)
                    return 1
                print(f"connection check passed: run {run_id} {status} ({counts})")
                return 0
            print(f"connection check FAILED: run {run_id} ended {status} ({counts})", file=sys.stderr)
            return 1
        await asyncio.sleep(0.5)
    print("connection check FAILED: the worker did not answer every purchase in time", file=sys.stderr)
    return 1


async def _unanswered(client: VisecaClient, run_id: str) -> list[str]:
    """Purchases in this run the platform has no decision of ours for — a timeout counts as none.

    A completed run is not a passed check: `finalized_event_count` counts a purchase the platform
    timed out just like one we answered, which is how 285 refused decisions once read as green.
    """
    rows = [r for r in _rows(await client.list_authorizations()) if r.get("run_id") == run_id]
    if not rows:  # no rows for the run is unknown, not success: a silent skip is how a false pass looks
        return ["the platform lists no purchases for this run"]
    missing = []
    for row in rows:
        given = row.get("decision")
        verdict = given.get("decision") if isinstance(given, Mapping) else given
        if str(row.get("status", "")).lower() == "timeout" or not verdict:
            missing.append(f"{row.get('source_authorization_id') or row.get('authorization_id')}"
                           f" ({row.get('status')})")
    return missing


async def _checked(client: VisecaClient, timeout: float, wanted: str | None, mandate_id: str | None) -> int:
    async with client:  # one pooled connection for the whole check, closed on the way out
        return await check(client, timeout, wanted, mandate_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="allow a non-local base URL (starts a real run)")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--scenario", help="scenario ID to check (default: the platform's shortest)")
    parser.add_argument("--mandate-id", help="already confirmed mandate; required for live checks")
    args = parser.parse_args()
    client = VisecaClient.from_env()
    if not args.live and urlsplit(client.base_url).hostname not in LOCAL_HOSTS:
        print(f"refusing to run against {client.base_url} without --live", file=sys.stderr)
        return 2
    return asyncio.run(_checked(client, args.timeout, args.scenario, args.mandate_id))


if __name__ == "__main__":
    sys.exit(main())

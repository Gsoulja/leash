"""The connection check (technical_details.md): confirm the SCEN0000 mandate, start its run, and wait until
the platform reports that run completed (it prints the platform's own counts; it does not re-check them). Run it
against the fake platform only:

    LEASH_BASE_URL=http://localhost:9000 TEAM_API_KEY=fake-team-key uv run python scripts/connection_check.py

It refuses any other base URL unless --live is given, so it never starts a scored run by accident.
"""

import argparse
import asyncio
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "tests"))  # the hand-compiled scenario mandates (LEASH-031) live with the tests

from fixtures.mandates import MANDATES  # noqa: E402

from leash.adapters.viseca_api.client import VisecaClient  # noqa: E402
from leash.adapters.viseca_api.worker import run_over  # noqa: E402
from leash.policy.hard_rules import mandate_to_api  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "fake"}


async def check(client: VisecaClient, timeout: float) -> int:
    body = {**mandate_to_api(MANDATES["SCEN0000"]), "guidance": [], "open_questions": []}
    draft = await client.create_mandate(body)
    mandate_id = (await client.confirm_mandate(str(draft["draft_id"])))["mandate_id"]
    run_id = (await client.start_run("SCEN0000", str(mandate_id)))["run_id"]
    print(f"run {run_id} started with mandate {mandate_id}")
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        progress = await client.get_run(str(run_id))
        if run_over(progress):  # the live API sends no counters at all, only a top-level status (LEASH-158)
            body = progress.get("data", progress) if isinstance(progress, Mapping) else {}
            status = str(body.get("status", "over")).lower()
            counts = body.get("counters") or {k: v for k, v in body.items() if k.endswith("_count")}
            if status in ("completed", "finished"):
                print(f"connection check passed: run {run_id} {status} ({counts})")
                return 0
            print(f"connection check FAILED: run {run_id} ended {status} ({counts})", file=sys.stderr)
            return 1
        await asyncio.sleep(0.5)
    print("connection check FAILED: the worker did not answer every purchase in time", file=sys.stderr)
    return 1


async def _checked(client: VisecaClient, timeout: float) -> int:
    async with client:  # one pooled connection for the whole check, closed on the way out
        return await check(client, timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="allow a non-local base URL (starts a real run)")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    client = VisecaClient.from_env()
    if not args.live and urlsplit(client.base_url).hostname not in LOCAL_HOSTS:
        print(f"refusing to run against {client.base_url} without --live", file=sys.stderr)
        return 2
    return asyncio.run(_checked(client, args.timeout))


if __name__ == "__main__":
    sys.exit(main())

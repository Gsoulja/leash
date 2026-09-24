"""The connection check (technical_details.md): confirm the SCEN0000 mandate, start its run, and wait until
the worker has answered every purchase. Run it against the fake platform only:

    LEASH_BASE_URL=http://localhost:9000 TEAM_API_KEY=fake-team-key uv run python scripts/connection_check.py

It refuses any other base URL unless --live is given, so it never starts a scored run by accident.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "tests"))  # the hand-compiled scenario mandates (LEASH-031) live with the tests

from fixtures.mandates import MANDATES  # noqa: E402

from leash.adapters.viseca_api.client import VisecaClient  # noqa: E402
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
        counters = ((await client.get_run(str(run_id))) or {}).get("data", {}).get("counters", {})
        if counters and counters.get("decided") == counters.get("total"):
            print(f"connection check passed: {counters['decided']}/{counters['total']} purchases answered")
            return 0
        await asyncio.sleep(0.5)
    print("connection check FAILED: the worker did not answer every purchase in time", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="allow a non-local base URL (starts a real run)")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    client = VisecaClient.from_env()
    if not args.live and urlsplit(client.base_url).hostname not in LOCAL_HOSTS:
        print(f"refusing to run against {client.base_url} without --live", file=sys.stderr)
        return 2
    return asyncio.run(check(client, args.timeout))


if __name__ == "__main__":
    sys.exit(main())

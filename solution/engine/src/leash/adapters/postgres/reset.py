"""LEASH-151: put a demo database back to the approved baseline, and prove it is one.

A rehearsal that starts from leftover state is not a rehearsal. This clears everything the demo writes
— drafts and their revisions, mandates and versions, runs, authorizations, the append-only log, the
outbox, the reader cache — reloads the challenge pack, and then *checks* the baseline instead of
assuming it: no duplicate authorization IDs, the seeded history totals equal the pack's own CSV totals
per card, and nothing the demo writes is left behind.

Two guards, because this deletes data:

- it refuses a database host that is not local unless `--live` is given, and
- it refuses to run at all unless `--yes` is given or `LEASH_ALLOW_DEMO_RESET=1` is set.

`decision_events` carries an append-only trigger. Reset disables it for the truncate and re-enables it
in the same transaction: the audit log is deliberately not deletable, so a reset has to say out loud
that it is doing so. Reference data (`merchants`, `auth_history`) is not deleted — the seed upserts it,
and the check afterwards is what proves it matches the pack.
"""

import argparse
import asyncio
import csv
import os
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import asyncpg

from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed

#: Everything the demo writes, in an order that respects the foreign keys. Reference data is absent on
#: purpose: it is upserted by the seed, never dropped.
DEMO_TABLES: tuple[str, ...] = (
    "outbox", "decision_events", "authorizations", "runs",
    "draft_revisions", "policy_drafts", "mandate_versions", "mandates", "fact_reads",
)

#: The audit log's protection, lifted only for the truncate below.
APPEND_ONLY_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("decision_events", "decision_events_append_only"),
    ("decision_events", "decision_events_no_truncate"),
)

#: Hosts a demo database may live on. `db` is the Compose service name — it is here because the
#: containerised reset needs it, and it is a deliberate risk: a machine whose DNS resolves `db` to
#: something real would pass this guard. The second guard (`--yes`) is what stands behind it.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})

#: A rehearsal cannot wait: the whole reset has to fit comfortably inside the gap between two runs.
BUDGET_SECONDS = 60.0


class RefusedReset(RuntimeError):
    """The reset did not run. The message says which guard stopped it."""


class BaselineNotClean(RuntimeError):
    """The reset ran but the result is not the approved baseline. Never ignore this before a demo."""


def effective_host(database_url: str, env: Mapping[str, str]) -> str | None:
    """Where this DSN really connects, the way libpq resolves it.

    A URL with no host in it is not automatically local: libpq (and asyncpg) fall back to the `host`
    query parameter and then to `PGHOST`, which is how operations tooling normally points at an
    environment. `postgresql:///leash?host=prod.example` and `PGHOST=prod.example` both reach a remote
    server through a DSN whose `hostname` parses as None. None here means a genuine local unix socket.
    """
    parts = urlsplit(database_url)
    if parts.hostname:
        return parts.hostname
    query = parse_qs(parts.query)
    if query.get("host"):
        return query["host"][0]
    return env.get("PGHOST") or None


def _is_local(database_url: str, env: Mapping[str, str]) -> bool:
    host = effective_host(database_url, env)
    if host is None or host.startswith("/"):
        return True  # a unix socket: this machine
    return host in LOCAL_HOSTS


def check_allowed(database_url: str, *, yes: bool, live: bool,
                  env: dict[str, str] | None = None) -> None:
    """Raise unless both guards are satisfied. Called before anything is deleted."""
    environ = os.environ if env is None else env
    if not (yes or environ.get("LEASH_ALLOW_DEMO_RESET") == "1"):
        raise RefusedReset("this deletes demo data: pass --yes, or set LEASH_ALLOW_DEMO_RESET=1")
    if not _is_local(database_url, environ) and not live:
        host = effective_host(database_url, environ)
        raise RefusedReset(f"refusing to reset {host!r}, which is not a local database, without --live")


async def clear(conn: asyncpg.Connection, tables: Sequence[str] = DEMO_TABLES) -> None:
    """Truncate every demo table in one transaction, audit-log protection lifted only inside it."""
    async with conn.transaction():
        for table, trigger in APPEND_ONLY_TRIGGERS:
            await conn.execute(f"alter table {table} disable trigger {trigger}")
        try:
            # No `restart identity`. `decision_events.seq` is the app's SSE cursor and a running API
            # keeps a high-water mark, so restarting it at 1 makes the next rehearsal's first events
            # look like ones already delivered — they are silently dropped from the stream. Letting the
            # sequence keep climbing costs nothing and keeps a live API correct across a reset.
            await conn.execute(f"truncate {', '.join(tables)} cascade")
        finally:
            for table, trigger in APPEND_ONLY_TRIGGERS:
                await conn.execute(f"alter table {table} enable trigger {trigger}")


def _pack_totals(pack: Pack) -> tuple[Counter[str], dict[str, Decimal], int]:
    """Per-card row counts and billed totals straight from the pack's CSV, and the row count."""
    counts: Counter[str] = Counter()
    totals: dict[str, Decimal] = {}
    rows = 0
    with (pack.data_dir / "authorization_history.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows += 1
            counts[r["card_id"]] += 1
            totals[r["card_id"]] = totals.get(r["card_id"], Decimal("0.00")) + Decimal(r["billing_amount_chf"])
    return counts, totals, rows


async def check_baseline(conn: asyncpg.Connection, pack: Pack) -> list[str]:
    """Everything that must be true before a rehearsal. Empty list means the baseline is good."""
    problems: list[str] = []

    for table in DEMO_TABLES:
        left = await conn.fetchval(f"select count(*) from {table}")
        if left:
            problems.append(f"{table} still holds {left} rows after the reset")

    duplicates = await conn.fetch("select authorization_id, count(*) as n from auth_history "
                                  "group by authorization_id having count(*) > 1")
    if duplicates:
        shown = ", ".join(f"{r['authorization_id']}×{r['n']}" for r in duplicates[:5])
        problems.append(f"{len(duplicates)} duplicate authorization IDs in auth_history ({shown})")

    counts, totals, rows = _pack_totals(pack)
    seeded = await conn.fetchval("select count(*) from auth_history")
    if seeded != rows:
        problems.append(f"auth_history has {seeded} rows, the pack has {rows}")
    per_card = await conn.fetch("select card_id, count(*) as n, sum(billing_chf) as total "
                                "from auth_history group by card_id")
    for row in per_card:
        card = row["card_id"]
        if row["n"] != counts.get(card):
            problems.append(f"{card}: {row['n']} rows seeded, {counts.get(card, 0)} in the pack")
        elif row["total"] != totals.get(card):
            problems.append(f"{card}: total CHF {row['total']} seeded, CHF {totals.get(card)} in the pack")
    missing = set(counts) - {row["card_id"] for row in per_card}
    if missing:
        problems.append(f"{len(missing)} cards in the pack have no seeded history ({', '.join(sorted(missing)[:5])})")

    if not await conn.fetchval("select exists (select 1 from merchants)"):
        problems.append("no merchants: the pack seed did not load reference data")
    return problems


async def reset(database_url: str, data_dir: Path, *, yes: bool = False, live: bool = False) -> float:
    """Clear, reseed and check. Returns how long it took; raises if the baseline is not clean."""
    check_allowed(database_url, yes=yes, live=live)
    started = time.monotonic()
    pack = Pack(data_dir)
    conn = await asyncpg.connect(database_url)
    try:
        await clear(conn)
        await seed(conn, pack)
        problems = await check_baseline(conn, pack)
    finally:
        await conn.close()
    took = time.monotonic() - started
    if problems:
        raise BaselineNotClean(
            "the database is not the approved baseline:\n  - " + "\n  - ".join(problems)
            + "\nDo not start the rehearsal. Check LEASH_DATA_DIR points at the challenge pack, then run "
              "the reset again; if it repeats, drop the database volume and re-run the migrations.")
    return took


def main() -> int:  # pragma: no cover - process entry point
    parser = argparse.ArgumentParser(description="Reset the demo database to the approved baseline.")
    parser.add_argument("--yes", action="store_true", help="confirm that this deletes demo data")
    parser.add_argument("--live", action="store_true", help="allow a database host that is not local")
    parser.add_argument("--budget", type=float, default=BUDGET_SECONDS,
                        help="fail if the reset takes longer than this many seconds")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("set DATABASE_URL", file=sys.stderr)
        return 2
    data_dir = Path(os.environ.get("LEASH_DATA_DIR", str(Path(__file__).resolve().parents[4].parents[1] / "data")))
    try:
        took = asyncio.run(reset(url, data_dir, yes=args.yes, live=args.live))
    except (RefusedReset, BaselineNotClean) as exc:
        print(f"reset FAILED: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"reset FAILED: the challenge pack is not at {data_dir} ({exc.filename}). "
              "Set LEASH_DATA_DIR to the pack directory.", file=sys.stderr)
        return 1
    except (OSError, asyncpg.PostgresError) as exc:
        # The three most likely rehearsal failures — database down, wrong password, wrong database —
        # deserve the cause on one line, not a traceback someone has to read under demo pressure.
        print(f"reset FAILED: could not use the database ({type(exc).__name__}: {exc}). "
              "Check DATABASE_URL and that the database is up and migrated.", file=sys.stderr)
        return 1
    if took > args.budget:
        print(f"reset FAILED: took {took:.1f}s, over the {args.budget:.0f}s rehearsal budget", file=sys.stderr)
        return 1
    print(f"reset OK: baseline loaded and checked in {took:.1f}s")
    return 0

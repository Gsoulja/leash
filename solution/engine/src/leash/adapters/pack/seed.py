"""Loads the challenge pack's reference data (merchants, card authorization history) into Postgres and
refreshes the familiarity view. Idempotent: rows are upserted, and a row that is already identical is
not written again. Called by scripts/seed.py and by startup readiness (LEASH-127)."""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import asyncpg

from leash.adapters.pack.loader import Pack

_MERCHANT_COLUMNS = ("merchant_id", "name", "category", "mcc", "country", "city", "availability", "recurring_capable")
_HISTORY_COLUMNS = ("authorization_id", "card_id", "merchant_id", "ts", "transaction_type", "status", "billing_chf",
                    "device_id", "country", "initiator")


@dataclass(frozen=True)
class SeedResult:
    merchants: int  # rows inserted or changed
    history: int


def _history_rows(pack: Pack) -> list[tuple[object, ...]]:
    with (pack.data_dir / "authorization_history.csv").open(encoding="utf-8", newline="") as f:
        return [(r["authorization_id"], r["card_id"], r["merchant_id"] or None,
                 datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")), r["transaction_type"], r["status"],
                 Decimal(r["billing_amount_chf"]), r["customer_device_id"] or None, r["merchant_country"] or None,
                 r["initiator_type"]) for r in csv.DictReader(f)]


async def _upsert(conn: asyncpg.Connection, table: str, key: str, columns: tuple[str, ...],
                  rows: Sequence[tuple[object, ...]]) -> int:
    staging = f"seed_{table}"
    await conn.execute(f"create temp table {staging} (like {table} including defaults) on commit drop")
    await conn.copy_records_to_table(staging, records=rows, columns=list(columns))
    cols = ", ".join(columns)
    changed = ", ".join(f"{c} = excluded.{c}" for c in columns if c != key)
    written = await conn.fetch(
        f"insert into {table} ({cols}) select {cols} from {staging} "
        f"on conflict ({key}) do update set {changed} "
        f"where ({', '.join(f'{table}.{c}' for c in columns)}) is distinct from "
        f"({', '.join(f'excluded.{c}' for c in columns)}) returning 1")
    return len(written)


async def seed(conn: asyncpg.Connection, pack: Pack) -> SeedResult:
    merchants = [(m.merchant_id, m.name, m.category, m.mcc, m.country, m.city, m.availability, m.recurring_capable)
                 for m in pack.merchants().values()]
    async with conn.transaction():
        n_merchants = await _upsert(conn, "merchants", "merchant_id", _MERCHANT_COLUMNS, merchants)
        n_history = await _upsert(conn, "auth_history", "authorization_id", _HISTORY_COLUMNS, _history_rows(pack))
    await conn.execute("refresh materialized view concurrently card_merchant_familiarity")
    return SeedResult(n_merchants, n_history)

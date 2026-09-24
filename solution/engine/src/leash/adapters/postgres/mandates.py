"""The MandateSource for the API process (LEASH-127): each run's stored mandate snapshot (DEC-003).

Compiled from the snapshot's hard_rules through the registry serializer, never from the instruction text.
`refresh` reloads every run; the API refreshes it in the background. An unknown run raises instead of
returning an empty mandate: an empty one would approve everything on a re-check.
"""

import json
import logging

import asyncpg

from leash.domain.mandate import CompiledMandate
from leash.policy.hard_rules import HardRulesError, mandate_from_api

log = logging.getLogger("leash.mandates")


class StoredMandates:
    def __init__(self) -> None:
        self._by_run: dict[str, CompiledMandate] = {}

    async def refresh(self, pool: asyncpg.Pool) -> None:
        rows = await pool.fetch(
            """select r.run_id, m.instruction, v.hard_rules, v.uncertainty_policy from runs r
               join mandates m using (mandate_id)
               join mandate_versions v on v.mandate_id = r.mandate_id and v.version = r.mandate_version""")
        loaded = {}
        for row in rows:
            try:
                loaded[row["run_id"]], _ = mandate_from_api({"instruction": row["instruction"] or "(stored mandate)",
                                                             "hard_rules": json.loads(row["hard_rules"]),
                                                             "uncertainty_policy": row["uncertainty_policy"]})
            except HardRulesError as exc:  # that run stays unknown (refused), the others still load
                log.error("INTEGRITY: run %s has an unreadable stored mandate: %s", row["run_id"], exc)
        self._by_run = loaded

    def for_run(self, run_id: str | None) -> CompiledMandate:
        if run_id is None or run_id not in self._by_run:
            raise LookupError(f"no stored mandate for run {run_id!r}")
        return self._by_run[run_id]

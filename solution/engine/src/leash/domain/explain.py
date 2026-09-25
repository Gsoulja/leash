"""Turns a decision into the payload for POST /v1/authorizations/{id}/decision.

The message is plain text for the customer: a decline names the first failing rule and then the
others; a step_up lists every warning (and any rule the engine can't enforce); an approval says so.
Evidence is one "label: actual" line per non-info check. Everything is escaped and capped, because
details can quote merchant text (DEC-025): no raw HTML ever reaches the customer or the platform.
"""

import html
from typing import Any

from .checks import Check
from .decide import Decision

MAX_MESSAGE_CHARS = 1000
MAX_EVIDENCE_CHARS = 300


def _safe(text: str, limit: int) -> str:
    text = " ".join(html.escape(text, quote=False).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


MAX_DETAIL_CHARS = 240


def _short(text: str) -> str:
    """Cap one detail so a single long quote can't push the other reasons out of the message."""
    return text if len(text) <= MAX_DETAIL_CHARS else text[: MAX_DETAIL_CHARS - 1] + "…"


def _message(decision: Decision) -> str:
    fails = [c for c in decision.checks if c.status == "fail"]
    doubts = [c for c in decision.checks if c.status in ("warn", "integrity")]
    if decision.verdict == "decline":
        if fails:
            others = f" Also: {', '.join(c.label.lower() for c in fails[1:])}." if fails[1:] else ""
            return _short(fails[0].detail) + others
        return "Please check: " + " ".join(_short(c.detail) for c in doubts) if doubts else "Declined."
    if decision.verdict == "step_up":
        return "Please check: " + " ".join(_short(c.detail) for c in doubts)
    if doubts:
        return "Approved under your setting to approve when unsure. Noted: " + " ".join(_short(c.detail) for c in doubts)
    return "All your rules passed."


def _evidence(check: Check) -> dict[str, Any]:
    """One check as a fact supporting the decision, with the same words the customer is shown."""
    return {
        "check": check.key,
        "label": _safe(check.label, MAX_EVIDENCE_CHARS),
        "status": check.status,
        "agreed": _safe(check.agreed, MAX_EVIDENCE_CHARS),
        "actual": _safe(check.actual, MAX_EVIDENCE_CHARS),
        "reason_code": check.reason_code,
    }


def explain(decision: Decision, *, authorization_id: str, engine_version: str) -> dict[str, Any]:
    return {
        "authorization_id": authorization_id,
        "decision": decision.verdict,
        "reason_codes": list(decision.reason_codes),
        "customer_message": _safe(_message(decision), MAX_MESSAGE_CHARS),
        # One object per check: the platform's /decision endpoint validates `evidence` as a list of
        # objects and refuses a list of strings (`dict_type`, 422) — measured 2026-09-25.
        "evidence": [_evidence(c) for c in decision.checks if c.status != "info"],
        "engine_version": engine_version,
    }

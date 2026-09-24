"""The unit an eval report is made of: a claim, its status, and the evidence behind it."""

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Status = Literal["pass", "fail", "info"]

# "info" is deliberate: a number nobody can call right or wrong (friction, sensitivity) is still
# evidence. Marking it pass/fail would invent a ground truth we do not have.
_MARK: dict[Status, str] = {"pass": "PASS", "fail": "FAIL", "info": "INFO"}


@dataclass(frozen=True)
class Claim:
    id: str
    claim: str           # the trust statement, in the words a judge would use
    status: Status
    metric: str          # the headline number, one line
    evidence: tuple[str, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "claim": self.claim, "status": self.status, "metric": self.metric,
                "evidence": list(self.evidence), "detail": dict(self.detail)}


def _revision() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@dataclass(frozen=True)
class Report:
    claims: tuple[Claim, ...]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    revision: str = field(default_factory=_revision)

    @property
    def failed(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.status == "fail")

    def as_dict(self) -> dict[str, Any]:
        return {"generated_at": self.generated_at, "revision": self.revision,
                "summary": {s: sum(c.status == s for c in self.claims) for s in ("pass", "fail", "info")},
                "claims": [c.as_dict() for c in self.claims]}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=False) + "\n"

    def to_markdown(self) -> str:
        counts = self.as_dict()["summary"]
        lines = ["# Leash decision engine — evaluation report", "",
                 f"Generated {self.generated_at} · commit `{self.revision}` · "
                 f"{counts['pass']} passed, {counts['fail']} failed, {counts['info']} measured", "",
                 "The challenge pack ships purchase inputs with no expected verdicts, so nothing here is an",
                 "accuracy score. Each claim below is a property of the engine that can be checked directly.", "",
                 "| ID | Claim | Result | Measure |", "| --- | --- | --- | --- |"]
        for c in self.claims:
            lines.append(f"| {c.id} | {c.claim} | **{_MARK[c.status]}** | {c.metric} |")
        for c in self.claims:
            lines += ["", f"## {c.id} — {c.claim}", "", f"**{_MARK[c.status]}** · {c.metric}", ""]
            lines += [f"- {line}" for line in c.evidence] or ["_No further evidence._"]
        return "\n".join(lines) + "\n"


def render(claims: Sequence[Claim]) -> Report:
    return Report(tuple(claims))

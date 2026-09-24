"""One check = one rule's finding about one purchase, with the evidence to explain it."""

from dataclasses import dataclass
from typing import Literal, get_args

Status = Literal["pass", "fail", "warn", "info", "integrity"]
Verdict = Literal["approve", "decline", "step_up"]


@dataclass(frozen=True)
class Check:
    key: str  # stable identifier of the rule, e.g. "price"
    label: str  # short name shown to the customer, e.g. "Price"
    status: Status  # fail → decline; warn → uncertainty policy; integrity → never approve
    agreed: str  # what the customer's permission allows
    actual: str  # what this purchase does
    detail: str  # plain-language sentence for the customer
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in get_args(Status):
            raise ValueError(f"unknown check status {self.status!r}")

"""The model's wire contract. Validation grants no authority to activate permission."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leash.domain.mandate import Operator


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RuleOutput(StrictOutput):
    field: str
    operator: Operator
    # Amounts travel as decimal strings, avoiding float rounding and bool-as-number coercion.
    value: str | int | list[str]
    currency: Literal["CHF"] | None
    scope: Literal["purchase", "period"] | None
    period_days: int | None = Field(ge=1)
    says: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)


class QuestionOutput(StrictOutput):
    text: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(max_length=3)


class ModelOutput(StrictOutput):
    intent: Literal["permission", "history", "chat"]
    reply: str | None = Field(max_length=4000)
    rules: list[RuleOutput] = Field(max_length=40)
    questions: list[QuestionOutput] = Field(max_length=20)
    uncertainty_policy: Literal["ask", "decline"]

    @model_validator(mode="after")
    def intent_matches_payload(self):
        if self.intent != "permission" and (self.rules or self.questions):
            raise ValueError("only permission intent may propose rules or questions")
        if self.intent == "chat" and not (self.reply and self.reply.strip()):
            raise ValueError("chat needs a reply")
        return self

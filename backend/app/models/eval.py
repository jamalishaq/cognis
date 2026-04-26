from typing import Literal

from pydantic import BaseModel


class EvalResult(BaseModel):
    eval_ran: bool = False
    groundedness: int | None = None
    completeness: int | None = None
    actionability: int | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    flags: list[str] = []

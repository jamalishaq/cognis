from typing import Literal

from pydantic import BaseModel


class TriageResult(BaseModel):
    service: str
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    failure_class: str

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

_INCIDENT_ID_RE = re.compile(r"^INC-\d{8}-\d{3}$")


class IncidentBrief(BaseModel):
    incident_id: str
    title: str
    summary: str
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    affected_service: str
    failure_class: str
    recommended_actions: list[str] = []
    runbook_references: list[str] = []
    retrieval_context_available: bool = True
    created_at: datetime

    @field_validator("incident_id")
    @classmethod
    def validate_incident_id(cls, v: str) -> str:
        if not _INCIDENT_ID_RE.match(v):
            raise ValueError(f"incident_id must match INC-YYYYMMDD-NNN, got: {v}")
        return v


class IncidentRecord(IncidentBrief):
    status: Literal["open", "resolved"] = "open"
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    resolved_by: str | None = None

    # LLM judge scores — internal only, never returned in API responses
    eval_ran: bool | None = None
    eval_groundedness: int | None = None
    eval_completeness: int | None = None
    eval_actionability: int | None = None
    eval_confidence: Literal["low", "medium", "high"] | None = None
    eval_flags: list[str] = []

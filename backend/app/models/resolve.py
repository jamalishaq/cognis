from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ResolveRequest(BaseModel):
    incident_id: str
    resolution_notes: str
    resolved_by: str | None = None


class ResolveResponse(BaseModel):
    incident_id: str
    status: Literal["resolved"] = "resolved"
    resolved_at: datetime
    message: str

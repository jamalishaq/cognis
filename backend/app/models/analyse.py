from datetime import datetime

from pydantic import BaseModel


class AnalyseResponse(BaseModel):
    incident_id: str
    status: str
    timestamp: datetime

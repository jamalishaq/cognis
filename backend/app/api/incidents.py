from __future__ import annotations

import structlog
from typing import Any

from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, HTTPException

from app.models.chat import ChatHistoryResponse, ChatMessage
from app.models.incident import IncidentBrief, IncidentRecord
from app.services import dynamodb

log = structlog.get_logger()

router = APIRouter()


def _get_incident_or_404(incident_id: str) -> dict[str, Any]:
    item = dynamodb.get_item("Incidents", {"incident_id": incident_id})
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )
    return item


@router.get("/incidents/{incident_id}", response_model=IncidentRecord)
def get_incident(incident_id: str) -> IncidentRecord:
    item = _get_incident_or_404(incident_id)
    return IncidentRecord(**item)


@router.get("/incidents/{incident_id}/history", response_model=ChatHistoryResponse)
def get_history(incident_id: str) -> ChatHistoryResponse:
    _get_incident_or_404(incident_id)
    items = dynamodb.scan(
        "ChatMessages",
        filter_expression=Attr("incident_id").eq(incident_id),
    )
    messages = sorted(
        [ChatMessage(**m) for m in items],
        key=lambda m: m.timestamp,
    )
    return ChatHistoryResponse(incident_id=incident_id, messages=messages)

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.resolve import ResolveRequest, ResolveResponse
from app.services import dynamodb, sqs

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/incidents/{incident_id}/resolve", response_model=ResolveResponse)
def resolve_incident(incident_id: str, request: ResolveRequest) -> ResolveResponse:
    if request.incident_id != incident_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "incident_id_mismatch",
                "message": "Path incident_id does not match body incident_id",
            },
        )

    item = dynamodb.get_item("Incidents", {"incident_id": incident_id})
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )
    if item.get("status") == "resolved":
        raise HTTPException(
            status_code=409,
            detail={"error": "already_resolved", "incident_id": incident_id},
        )

    now = datetime.now(timezone.utc)
    updates: dict = {
        "status": "resolved",
        "resolved_at": now.isoformat(),
        "resolution_notes": request.resolution_notes,
        "resolved_by": request.resolved_by,
    }

    try:
        dynamodb.update_item("Incidents", {"incident_id": incident_id}, updates)
    except Exception as exc:
        logger.error("DynamoDB update failed for %s: %s", incident_id, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "storage_failed", "message": "Failed to update incident record"},
        )

    # Drop SQS ingestion message — async fire-and-forget; Lambda ingests resolution into corpus
    try:
        sqs.send_message(
            settings.ingestion_queue_url,
            {
                "type": "incident_resolution",
                "incident_id": incident_id,
                "title": item.get("title", ""),
                "resolution_notes": request.resolution_notes,
                "resolved_by": request.resolved_by,
                "resolved_at": now.isoformat(),
            },
        )
    except Exception as exc:
        logger.warning("SQS ingestion message failed for %s: %s", incident_id, exc)

    return ResolveResponse(
        incident_id=incident_id,
        status="resolved",
        resolved_at=now,
        message="Incident resolved successfully",
    )

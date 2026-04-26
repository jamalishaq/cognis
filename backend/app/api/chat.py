from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest
from app.models.triage import TriageResult
from app.pipeline import chat_agent, retrieval
from app.services import dynamodb

logger = logging.getLogger(__name__)

router = APIRouter()


def _load_incident(incident_id: str) -> dict[str, Any]:
    item = dynamodb.get_item("Incidents", {"incident_id": incident_id})
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "incident_not_found", "incident_id": incident_id},
        )
    return item


def _load_history(incident_id: str) -> list[dict[str, Any]]:
    items = dynamodb.scan(
        "ChatMessages",
        filter_expression=Attr("incident_id").eq(incident_id),
    )
    return sorted(items, key=lambda m: m.get("timestamp", ""))


def _next_message_id(incident_id: str) -> str:
    items = dynamodb.scan(
        "ChatMessages",
        filter_expression=Attr("incident_id").eq(incident_id),
    )
    return f"MSG-{len(items) + 1:03d}"


def _store_message(
    message_id: str,
    incident_id: str,
    role: str,
    content: str,
    ts: datetime,
) -> None:
    dynamodb.put_item(
        "ChatMessages",
        {
            "message_id": message_id,
            "incident_id": incident_id,
            "role": role,
            "content": content,
            "timestamp": ts.isoformat(),
        },
    )


@router.post("/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    incident = _load_incident(request.incident_id)
    history = _load_history(request.incident_id)

    triage_result = TriageResult(
        service=incident.get("affected_service", "unknown"),
        severity=incident.get("severity", "unknown"),  # type: ignore[arg-type]
        failure_class=incident.get("failure_class", "unknown"),
    )
    retrieval_result = retrieval.run(triage_result)

    user_ts = datetime.now(timezone.utc)
    user_msg_id = _next_message_id(request.incident_id)
    try:
        _store_message(user_msg_id, request.incident_id, "user", request.message, user_ts)
    except Exception as exc:
        logger.error("Failed to store user message %s: %s", user_msg_id, exc)

    def generate() -> Generator[str, None, None]:
        chunks: list[str] = []
        try:
            stream = chat_agent.run(incident, history, request.message, retrieval_result.chunks)
            for chunk in stream:
                chunks.append(chunk)
                yield chunk
        except Exception as exc:
            logger.error("Chat agent failed for %s: %s", request.incident_id, exc)
            yield "Unable to process your request, please try again"
            return

        full_response = "".join(chunks)
        assistant_ts = datetime.now(timezone.utc)
        assistant_msg_id = _next_message_id(request.incident_id)
        try:
            _store_message(
                assistant_msg_id,
                request.incident_id,
                "assistant",
                full_response,
                assistant_ts,
            )
        except Exception as exc:
            logger.error("Failed to store assistant message %s: %s", assistant_msg_id, exc)

    return StreamingResponse(generate(), media_type="text/plain")

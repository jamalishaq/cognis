from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.logger import setup_logging
from app.models.incident import IncidentBrief
from app.registry.notification_registry import get_active_providers

setup_logging()
log = structlog.get_logger()


def handler(event: dict[str, Any], context: Any) -> None:
    for record in event.get("Records", []):
        _process_record(record)


def _process_record(record: dict[str, Any]) -> None:
    body = record.get("body", "")
    try:
        incident = IncidentBrief.model_validate(json.loads(body))
    except Exception as exc:
        log.error(
            "notify_parse_failed",
            error=str(exc),
            body=body,
        )
        return

    try:
        asyncio.run(_send_all(incident))
    except Exception as exc:
        log.error(
            "notify_send_all_failed",
            incident_id=getattr(incident, "incident_id", "?"),
            error=str(exc),
        )


async def _send_all(incident: IncidentBrief) -> None:
    for provider in get_active_providers():
        try:
            await provider.send(incident)
        except Exception as exc:
            log.error(
                "notify_provider_failed",
                provider=type(provider).__name__,
                incident_id=incident.incident_id,
                error=str(exc),
            )

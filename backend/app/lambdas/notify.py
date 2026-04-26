from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.models.incident import IncidentBrief
from app.registry.notification_registry import get_active_providers

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> None:
    for record in event.get("Records", []):
        _process_record(record)


def _process_record(record: dict[str, Any]) -> None:
    body = record.get("body", "")
    try:
        incident = IncidentBrief.model_validate(json.loads(body))
    except Exception as exc:
        logger.error(
            "notify: failed to parse SQS record — skipping to avoid infinite requeue: %s body=%r",
            exc,
            body,
        )
        return

    asyncio.run(_send_all(incident))


async def _send_all(incident: IncidentBrief) -> None:
    for provider in get_active_providers():
        try:
            await provider.send(incident)
        except Exception as exc:
            logger.error(
                "notify: provider %s failed for incident_id=%s — skipping to avoid infinite requeue: %s",
                type(provider).__name__,
                incident.incident_id,
                exc,
            )

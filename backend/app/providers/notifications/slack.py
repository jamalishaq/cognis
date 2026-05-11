from __future__ import annotations

import structlog

from app.models.incident import IncidentBrief
from app.providers.base import NotificationProvider

log = structlog.get_logger()


class SlackProvider(NotificationProvider):
    async def send(self, incident: IncidentBrief) -> None:
        # TODO: implement Slack webhook integration
        log.info(
            "slack_notification_stub",
            incident_id=incident.incident_id,
            severity=incident.severity,
            title=incident.title,
        )

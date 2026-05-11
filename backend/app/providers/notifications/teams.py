from __future__ import annotations

import structlog

from app.models.incident import IncidentBrief
from app.providers.base import NotificationProvider

log = structlog.get_logger()


class TeamsProvider(NotificationProvider):
    async def send(self, incident: IncidentBrief) -> None:
        # TODO: implement Microsoft Teams webhook integration
        log.info(
            "teams_notification_stub",
            incident_id=incident.incident_id,
            severity=incident.severity,
            title=incident.title,
        )

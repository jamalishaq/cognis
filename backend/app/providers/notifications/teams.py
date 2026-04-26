from __future__ import annotations

import logging

from app.models.incident import IncidentBrief
from app.providers.base import NotificationProvider

logger = logging.getLogger(__name__)


class TeamsNotificationProvider(NotificationProvider):
    async def send(self, incident: IncidentBrief) -> None:
        # TODO: implement Microsoft Teams webhook integration
        logger.info(
            "Teams notification (stub): incident_id=%s severity=%s title=%s",
            incident.incident_id,
            incident.severity,
            incident.title,
        )

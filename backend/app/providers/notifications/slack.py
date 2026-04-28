from __future__ import annotations

import logging

from app.models.incident import IncidentBrief
from app.providers.base import NotificationProvider

logger = logging.getLogger(__name__)


class SlackProvider(NotificationProvider):
    async def send(self, incident: IncidentBrief) -> None:
        # TODO: implement Slack webhook integration
        logger.info(
            "Slack notification (stub): incident_id=%s severity=%s title=%s",
            incident.incident_id,
            incident.severity,
            incident.title,
        )

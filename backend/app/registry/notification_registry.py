from __future__ import annotations

import logging

from app.config import settings
from app.providers.base import NotificationProvider
from app.providers.notifications.ses import SESNotificationProvider
from app.providers.notifications.slack import SlackNotificationProvider
from app.providers.notifications.teams import TeamsNotificationProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, NotificationProvider] = {
    "ses": SESNotificationProvider(),
    "slack": SlackNotificationProvider(),
    "teams": TeamsNotificationProvider(),
}


def get_active_providers() -> list[NotificationProvider]:
    names = [n.strip() for n in settings.active_notification_providers.split(",") if n.strip()]
    providers: list[NotificationProvider] = []
    for name in names:
        provider = _PROVIDER_MAP.get(name)
        if provider is None:
            logger.warning("Unknown notification provider %r — skipping", name)
            continue
        providers.append(provider)
    return providers

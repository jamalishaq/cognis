from __future__ import annotations

import logging

from app.config import settings
from app.providers.base import NotificationProvider
from app.providers.notifications.ses import SESProvider
from app.providers.notifications.slack import SlackProvider
from app.providers.notifications.teams import TeamsProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, NotificationProvider] = {
    "ses": SESProvider(),
    "slack": SlackProvider(),
    "teams": TeamsProvider(),
}


def get_active_providers() -> list[NotificationProvider]:
    providers: list[NotificationProvider] = []
    for name in settings.active_providers_list:
        provider = _PROVIDER_MAP.get(name)
        if provider is None:
            logger.warning("Unknown notification provider %r — skipping", name)
            continue
        providers.append(provider)
    return providers

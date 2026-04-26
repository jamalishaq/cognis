from abc import ABC, abstractmethod

from app.models.alert import NormalisedAlert
from app.models.incident import IncidentBrief


class AlertNormaliser(ABC):
    @abstractmethod
    def can_handle(self, payload: dict) -> bool: ...

    @abstractmethod
    def normalise(self, payload: dict) -> NormalisedAlert: ...


class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, incident: IncidentBrief) -> None: ...

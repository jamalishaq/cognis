from datetime import datetime, timezone

from app.models.alert import PagerDutyPayload, NormalisedAlert
from app.providers.base import AlertNormaliser

_URGENCY_SEVERITY: dict[str, str] = {
    "high": "high",
    "low": "low",
}


class PagerDutyNormaliser(AlertNormaliser):
    def can_handle(self, payload: dict) -> bool:
        event = payload.get("event")
        return (
            isinstance(event, dict)
            and "event_type" in event
            and "data" in event
        )

    def normalise(self, payload: dict) -> NormalisedAlert:
        data = PagerDutyPayload.model_validate(payload)
        incident = data.event.data

        title = incident.title
        description = incident.body.details or title
        service = incident.service.summary or "unknown"
        severity = _URGENCY_SEVERITY.get(incident.urgency.lower(), "unknown")

        return NormalisedAlert(
            source="pagerduty",
            title=title,
            description=description,
            severity=severity,
            service=service,
            raw_payload=payload,
            received_at=datetime.now(timezone.utc),
        )

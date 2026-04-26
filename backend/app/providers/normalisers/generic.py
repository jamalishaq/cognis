from datetime import datetime, timezone

from app.models.alert import NormalisedAlert
from app.providers.base import AlertNormaliser

_SEVERITY_CANONICAL = {"critical", "high", "medium", "low"}
_SEVERITY_ALIASES: dict[str, str] = {
    "error": "high",
    "err": "high",
    "warning": "medium",
    "warn": "medium",
    "info": "low",
    "information": "low",
    "none": "low",
}


class GenericNormaliser(AlertNormaliser):
    def can_handle(self, payload: dict) -> bool:
        return True

    def normalise(self, payload: dict) -> NormalisedAlert:
        title = str(
            payload.get("title")
            or payload.get("name")
            or payload.get("alertname")
            or payload.get("message")
            or "Unknown Alert"
        )
        description = str(
            payload.get("description")
            or payload.get("message")
            or payload.get("summary")
            or title
        )
        service = str(
            payload.get("service")
            or payload.get("job")
            or payload.get("source")
            or "unknown"
        )
        raw_sev = str(payload.get("severity") or payload.get("urgency") or "").lower()
        if raw_sev in _SEVERITY_CANONICAL:
            severity = raw_sev
        else:
            severity = _SEVERITY_ALIASES.get(raw_sev, "unknown")

        return NormalisedAlert(
            source="generic",
            title=title,
            description=description,
            severity=severity,
            service=service,
            raw_payload=payload,
            received_at=datetime.now(timezone.utc),
        )

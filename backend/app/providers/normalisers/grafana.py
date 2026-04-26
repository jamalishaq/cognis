from datetime import datetime, timezone

from app.models.alert import GrafanaPayload, NormalisedAlert
from app.providers.base import AlertNormaliser

_LABEL_SEVERITY: dict[str, str] = {
    "critical": "critical",
    "error": "high",
    "warning": "medium",
    "warn": "medium",
    "info": "low",
    "none": "low",
}

_STATE_SEVERITY: dict[str, str] = {
    "alerting": "high",
    "pending": "medium",
}


class GrafanaNormaliser(AlertNormaliser):
    def can_handle(self, payload: dict) -> bool:
        return isinstance(payload.get("alerts"), list) and "state" in payload

    def normalise(self, payload: dict) -> NormalisedAlert:
        data = GrafanaPayload.model_validate(payload)
        first = data.alerts[0] if data.alerts else None

        labels: dict[str, str] = dict(first.labels) if first else {}
        annotations: dict[str, str] = dict(first.annotations) if first else {}
        for k, v in data.common_labels.items():
            labels.setdefault(k, v)
        for k, v in data.common_annotations.items():
            annotations.setdefault(k, v)

        title = data.title
        service = labels.get("service") or labels.get("job") or "unknown"
        description = (
            annotations.get("description")
            or annotations.get("summary")
            or data.message
            or title
        )
        raw_sev = labels.get("severity", "").lower()
        severity = _LABEL_SEVERITY.get(raw_sev) or _STATE_SEVERITY.get(
            data.state.lower(), "unknown"
        )

        return NormalisedAlert(
            source="grafana",
            title=title,
            description=description,
            severity=severity,
            service=service,
            raw_payload=payload,
            received_at=datetime.now(timezone.utc),
        )

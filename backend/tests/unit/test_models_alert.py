from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.alert import (
    GrafanaAlertItem,
    GrafanaPayload,
    NormalisedAlert,
    PagerDutyEvent,
    PagerDutyIncidentData,
    PagerDutyPayload,
)

NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# GrafanaAlertItem
# ---------------------------------------------------------------------------


def test_grafana_alert_item_minimal():
    item = GrafanaAlertItem(status="firing")
    assert item.status == "firing"
    assert item.labels == {}
    assert item.annotations == {}
    assert item.fingerprint == ""


def test_grafana_alert_item_camel_case_aliases():
    item = GrafanaAlertItem.model_validate(
        {
            "status": "firing",
            "labels": {"severity": "critical"},
            "startsAt": "2024-06-01T12:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://grafana/alert",
            "fingerprint": "abc123",
        }
    )
    assert item.starts_at is not None
    assert item.generator_url == "http://grafana/alert"
    assert item.fingerprint == "abc123"


def test_grafana_alert_item_snake_case_population():
    item = GrafanaAlertItem(
        status="resolved",
        starts_at=NOW,
        generator_url="http://example.com",
    )
    assert item.starts_at == NOW
    assert item.generator_url == "http://example.com"


# ---------------------------------------------------------------------------
# GrafanaPayload
# ---------------------------------------------------------------------------


def test_grafana_payload_required_fields():
    payload = GrafanaPayload(title="[FIRING] High CPU", state="alerting")
    assert payload.title == "[FIRING] High CPU"
    assert payload.state == "alerting"
    assert payload.message == ""
    assert payload.alerts == []
    assert payload.common_labels == {}
    assert payload.common_annotations == {}
    assert payload.org_id == 0


def test_grafana_payload_missing_required_raises():
    with pytest.raises(ValidationError):
        GrafanaPayload(state="alerting")  # missing title


def test_grafana_payload_camel_case_aliases():
    payload = GrafanaPayload.model_validate(
        {
            "title": "[FIRING] DB latency",
            "state": "alerting",
            "commonLabels": {"env": "prod"},
            "commonAnnotations": {"summary": "Latency high"},
            "externalURL": "http://grafana/",
            "groupKey": "group-1",
            "orgId": 42,
        }
    )
    assert payload.common_labels == {"env": "prod"}
    assert payload.common_annotations == {"summary": "Latency high"}
    assert payload.external_url == "http://grafana/"
    assert payload.group_key == "group-1"
    assert payload.org_id == 42


def test_grafana_payload_with_alerts():
    payload = GrafanaPayload(
        title="Alert",
        state="firing",
        alerts=[GrafanaAlertItem(status="firing", labels={"job": "backend"})],
    )
    assert len(payload.alerts) == 1
    assert payload.alerts[0].labels["job"] == "backend"


def test_grafana_payload_full_json_round_trip():
    raw = {
        "title": "[FIRING:1] High CPU",
        "state": "alerting",
        "message": "CPU over 90%",
        "receiver": "ops-team",
        "status": "firing",
        "alerts": [{"status": "firing", "labels": {"severity": "critical"}}],
        "commonLabels": {"severity": "critical"},
        "commonAnnotations": {},
        "externalURL": "http://grafana/",
        "groupKey": "{}:{alertname='High CPU'}",
        "orgId": 1,
    }
    payload = GrafanaPayload.model_validate(raw)
    assert payload.common_labels["severity"] == "critical"
    assert payload.receiver == "ops-team"


# ---------------------------------------------------------------------------
# PagerDutyPayload
# ---------------------------------------------------------------------------


def _pd_event_data() -> dict:
    return {
        "id": "Q14K5Z",
        "title": "Server down",
        "status": "triggered",
        "incident_key": "key-abc",
        "created_at": "2024-06-01T12:00:00Z",
        "html_url": "https://pagerduty.com/incidents/Q14K5Z",
        "urgency": "high",
        "service": {"id": "SVC1", "summary": "API", "type": "service_reference"},
        "body": {"type": "incident_body", "details": "An alert triggered."},
    }


def _pd_payload_dict() -> dict:
    return {
        "event": {
            "id": "EVT-001",
            "event_type": "incident.triggered",
            "resource_type": "incident",
            "occurred_at": "2024-06-01T12:00:00Z",
            "data": _pd_event_data(),
        }
    }


def test_pagerduty_payload_valid():
    payload = PagerDutyPayload.model_validate(_pd_payload_dict())
    assert payload.event.event_type == "incident.triggered"
    assert payload.event.data.title == "Server down"
    assert payload.event.data.urgency == "high"
    assert payload.event.data.service.summary == "API"


def test_pagerduty_payload_missing_event_raises():
    with pytest.raises(ValidationError):
        PagerDutyPayload.model_validate({})


def test_pagerduty_incident_data_defaults():
    data = PagerDutyIncidentData(
        id="X1",
        title="Outage",
        status="triggered",
        created_at=NOW,
    )
    assert data.incident_key == ""
    assert data.urgency == ""
    assert data.html_url == ""
    assert data.service.id == ""
    assert data.body.details == ""


def test_pagerduty_event_resource_type_default():
    event = PagerDutyEvent(
        id="E1",
        event_type="incident.triggered",
        occurred_at=NOW,
        data=PagerDutyIncidentData(
            id="D1", title="T", status="triggered", created_at=NOW
        ),
    )
    assert event.resource_type == "incident"


# ---------------------------------------------------------------------------
# NormalisedAlert
# ---------------------------------------------------------------------------


def test_normalised_alert_valid():
    alert = NormalisedAlert(
        source="grafana",
        title="High CPU",
        description="CPU usage exceeded 90%",
        severity="critical",
        service="backend",
        received_at=NOW,
    )
    assert alert.source == "grafana"
    assert alert.severity == "critical"
    assert alert.raw_payload == {}


def test_normalised_alert_defaults():
    alert = NormalisedAlert(
        source="generic",
        title="Unknown alert",
        description="No details",
        received_at=NOW,
    )
    assert alert.severity == "unknown"
    assert alert.service == ""
    assert alert.raw_payload == {}


def test_normalised_alert_invalid_source_raises():
    with pytest.raises(ValidationError):
        NormalisedAlert(
            source="datadog",  # not allowed
            title="Alert",
            description="Desc",
            received_at=NOW,
        )


def test_normalised_alert_invalid_severity_raises():
    with pytest.raises(ValidationError):
        NormalisedAlert(
            source="pagerduty",
            title="Alert",
            description="Desc",
            severity="extreme",  # not allowed
            received_at=NOW,
        )


def test_normalised_alert_all_severities():
    for severity in ("critical", "high", "medium", "low", "unknown"):
        alert = NormalisedAlert(
            source="grafana",
            title="T",
            description="D",
            severity=severity,
            received_at=NOW,
        )
        assert alert.severity == severity


def test_normalised_alert_all_sources():
    for source in ("grafana", "pagerduty", "generic"):
        alert = NormalisedAlert(
            source=source,
            title="T",
            description="D",
            received_at=NOW,
        )
        assert alert.source == source


def test_normalised_alert_raw_payload_stored():
    raw = {"key": "value", "nested": {"x": 1}}
    alert = NormalisedAlert(
        source="grafana",
        title="T",
        description="D",
        received_at=NOW,
        raw_payload=raw,
    )
    assert alert.raw_payload == raw

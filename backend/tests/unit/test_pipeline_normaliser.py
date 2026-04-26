from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.models.alert import NormalisedAlert
from app.utils import normaliser

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

GRAFANA_PAYLOAD = {
    "title": "High CPU Usage",
    "state": "alerting",
    "message": "CPU usage is above 90%",
    "alerts": [
        {
            "status": "firing",
            "labels": {"severity": "critical", "service": "api-server"},
            "annotations": {"description": "CPU at 95% for 5 minutes"},
            "startsAt": "2024-01-01T12:00:00Z",
            "generatorURL": "http://grafana.example.com/alert",
            "fingerprint": "abc123",
        }
    ],
    "commonLabels": {},
    "commonAnnotations": {},
    "externalURL": "http://grafana.example.com",
    "receiver": "ops-team",
    "status": "firing",
    "groupKey": "{}:{alertname=\"HighCPU\"}",
    "orgId": 1,
}

PAGERDUTY_PAYLOAD = {
    "event": {
        "id": "01BTFG5N1H",
        "event_type": "incident.triggered",
        "resource_type": "incident",
        "occurred_at": "2024-01-01T12:00:00Z",
        "data": {
            "id": "PT4KHLK",
            "title": "Production database down",
            "status": "triggered",
            "incident_key": "db-prod-down",
            "created_at": "2024-01-01T12:00:00Z",
            "html_url": "https://acme.pagerduty.com/incidents/PT4KHLK",
            "urgency": "high",
            "service": {"id": "PWIXJZS", "summary": "database-service", "type": "service_reference"},
            "body": {"type": "incident_body", "details": "DB not responding."},
        },
    }
}

GENERIC_PAYLOAD = {"title": "Disk full", "severity": "medium", "service": "storage-node"}


def _make_normalised_alert(source: str, **kwargs) -> NormalisedAlert:
    defaults = dict(
        source=source,
        title="Test Alert",
        description="Test description",
        severity="high",
        service="test-service",
        raw_payload={},
        received_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return NormalisedAlert(**defaults)


# ---------------------------------------------------------------------------
# Delegation — pipeline normaliser must go through the registry
# ---------------------------------------------------------------------------


def test_normaliser_delegates_to_registry():
    """Verify the pipeline orchestrator calls normaliser_registry.normalise, not a specific normaliser."""
    expected = _make_normalised_alert("grafana")
    with patch("app.utils.normaliser.normaliser_registry.normalise", return_value=expected) as mock_normalise:
        result = normaliser.normalise(GRAFANA_PAYLOAD)
        mock_normalise.assert_called_once_with(GRAFANA_PAYLOAD)
        assert result is expected


def test_normaliser_passes_payload_unchanged():
    payload = {"arbitrary": "data"}
    with patch("app.utils.normaliser.normaliser_registry.normalise") as mock_normalise:
        mock_normalise.return_value = _make_normalised_alert("generic")
        normaliser.normalise(payload)
        mock_normalise.assert_called_once_with(payload)


def test_normaliser_returns_registry_result_directly():
    expected = _make_normalised_alert("pagerduty")
    with patch("app.utils.normaliser.normaliser_registry.normalise", return_value=expected):
        assert normaliser.normalise(PAGERDUTY_PAYLOAD) is expected


# ---------------------------------------------------------------------------
# Source detection — Grafana payload
# ---------------------------------------------------------------------------


def test_normalise_grafana_payload_returns_grafana_source():
    result = normaliser.normalise(GRAFANA_PAYLOAD)
    assert result.source == "grafana"


def test_normalise_grafana_payload_returns_normalised_alert():
    result = normaliser.normalise(GRAFANA_PAYLOAD)
    assert isinstance(result, NormalisedAlert)


def test_normalise_grafana_extracts_title():
    result = normaliser.normalise(GRAFANA_PAYLOAD)
    assert result.title == "High CPU Usage"


def test_normalise_grafana_extracts_service():
    result = normaliser.normalise(GRAFANA_PAYLOAD)
    assert result.service == "api-server"


def test_normalise_grafana_extracts_severity():
    result = normaliser.normalise(GRAFANA_PAYLOAD)
    assert result.severity == "critical"


# ---------------------------------------------------------------------------
# Source detection — PagerDuty payload
# ---------------------------------------------------------------------------


def test_normalise_pagerduty_payload_returns_pagerduty_source():
    result = normaliser.normalise(PAGERDUTY_PAYLOAD)
    assert result.source == "pagerduty"


def test_normalise_pagerduty_payload_returns_normalised_alert():
    result = normaliser.normalise(PAGERDUTY_PAYLOAD)
    assert isinstance(result, NormalisedAlert)


def test_normalise_pagerduty_extracts_title():
    result = normaliser.normalise(PAGERDUTY_PAYLOAD)
    assert result.title == "Production database down"


def test_normalise_pagerduty_extracts_service():
    result = normaliser.normalise(PAGERDUTY_PAYLOAD)
    assert result.service == "database-service"


def test_normalise_pagerduty_extracts_severity():
    result = normaliser.normalise(PAGERDUTY_PAYLOAD)
    assert result.severity == "high"


# ---------------------------------------------------------------------------
# Source detection — Generic / unknown payload
# ---------------------------------------------------------------------------


def test_normalise_generic_payload_returns_generic_source():
    result = normaliser.normalise(GENERIC_PAYLOAD)
    assert result.source == "generic"


def test_normalise_generic_payload_returns_normalised_alert():
    result = normaliser.normalise(GENERIC_PAYLOAD)
    assert isinstance(result, NormalisedAlert)


def test_normalise_generic_extracts_title():
    result = normaliser.normalise(GENERIC_PAYLOAD)
    assert result.title == "Disk full"


def test_normalise_generic_extracts_service():
    result = normaliser.normalise(GENERIC_PAYLOAD)
    assert result.service == "storage-node"


def test_normalise_generic_extracts_severity():
    result = normaliser.normalise(GENERIC_PAYLOAD)
    assert result.severity == "medium"


def test_normalise_empty_dict_routes_to_generic():
    result = normaliser.normalise({})
    assert result.source == "generic"


def test_normalise_unknown_payload_routes_to_generic():
    result = normaliser.normalise({"some": "random", "alert": "data"})
    assert result.source == "generic"


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------


def test_normalise_always_returns_normalised_alert_for_any_source():
    for payload in (GRAFANA_PAYLOAD, PAGERDUTY_PAYLOAD, GENERIC_PAYLOAD, {}):
        assert isinstance(normaliser.normalise(payload), NormalisedAlert)


def test_normalise_result_has_received_at_datetime():
    result = normaliser.normalise(GRAFANA_PAYLOAD)
    assert isinstance(result.received_at, datetime)


def test_normalise_result_preserves_raw_payload():
    result = normaliser.normalise(GENERIC_PAYLOAD)
    assert result.raw_payload == GENERIC_PAYLOAD

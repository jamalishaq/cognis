from datetime import datetime

import pytest

from app.providers.normalisers.generic import GenericNormaliser
from app.providers.normalisers.grafana import GrafanaNormaliser
from app.providers.normalisers.pagerduty import PagerDutyNormaliser
from app.registry.normaliser_registry import normalise

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
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "service": "api-server",
                "job": "node-exporter",
            },
            "annotations": {
                "description": "CPU at 95% for 5 minutes",
                "summary": "High CPU alert",
            },
            "startsAt": "2024-01-01T12:00:00Z",
            "generatorURL": "http://grafana.example.com/alert",
            "fingerprint": "abc123",
        }
    ],
    "commonLabels": {"env": "prod"},
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
            "service": {
                "id": "PWIXJZS",
                "summary": "database-service",
                "type": "service_reference",
            },
            "body": {
                "type": "incident_body",
                "details": "The production database is not responding to health checks.",
            },
        },
    }
}


# ---------------------------------------------------------------------------
# GrafanaNormaliser — can_handle
# ---------------------------------------------------------------------------


def test_grafana_can_handle_valid_payload():
    assert GrafanaNormaliser().can_handle(GRAFANA_PAYLOAD) is True


def test_grafana_can_handle_requires_state_key():
    payload = {k: v for k, v in GRAFANA_PAYLOAD.items() if k != "state"}
    assert GrafanaNormaliser().can_handle(payload) is False


def test_grafana_can_handle_requires_alerts_to_be_list():
    assert GrafanaNormaliser().can_handle({**GRAFANA_PAYLOAD, "alerts": "not-a-list"}) is False


def test_grafana_can_handle_empty_alerts_list_is_ok():
    assert GrafanaNormaliser().can_handle({**GRAFANA_PAYLOAD, "alerts": []}) is True


def test_grafana_can_handle_rejects_pagerduty_payload():
    assert GrafanaNormaliser().can_handle(PAGERDUTY_PAYLOAD) is False


def test_grafana_can_handle_rejects_empty_dict():
    assert GrafanaNormaliser().can_handle({}) is False


# ---------------------------------------------------------------------------
# GrafanaNormaliser — normalise
# ---------------------------------------------------------------------------


def test_grafana_normalise_source():
    assert GrafanaNormaliser().normalise(GRAFANA_PAYLOAD).source == "grafana"


def test_grafana_normalise_title_from_payload():
    assert GrafanaNormaliser().normalise(GRAFANA_PAYLOAD).title == "High CPU Usage"


def test_grafana_normalise_description_from_annotation():
    result = GrafanaNormaliser().normalise(GRAFANA_PAYLOAD)
    assert result.description == "CPU at 95% for 5 minutes"


def test_grafana_normalise_service_from_alert_labels():
    result = GrafanaNormaliser().normalise(GRAFANA_PAYLOAD)
    assert result.service == "api-server"


def test_grafana_normalise_severity_critical():
    result = GrafanaNormaliser().normalise(GRAFANA_PAYLOAD)
    assert result.severity == "critical"


def test_grafana_normalise_severity_warning_maps_to_medium():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {"severity": "warning"}}],
    }
    assert GrafanaNormaliser().normalise(payload).severity == "medium"


def test_grafana_normalise_severity_error_maps_to_high():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {"severity": "error"}}],
    }
    assert GrafanaNormaliser().normalise(payload).severity == "high"


def test_grafana_normalise_severity_info_maps_to_low():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {"severity": "info"}}],
    }
    assert GrafanaNormaliser().normalise(payload).severity == "low"


def test_grafana_normalise_unknown_severity_falls_back_to_state():
    payload = {
        **GRAFANA_PAYLOAD,
        "state": "alerting",
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {}}],
    }
    assert GrafanaNormaliser().normalise(payload).severity == "high"


def test_grafana_normalise_unknown_severity_unknown_state():
    payload = {
        **GRAFANA_PAYLOAD,
        "state": "nodata",
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {}}],
    }
    assert GrafanaNormaliser().normalise(payload).severity == "unknown"


def test_grafana_normalise_service_falls_back_to_job_label():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [
            {**GRAFANA_PAYLOAD["alerts"][0], "labels": {"job": "node-exporter"}}
        ],
    }
    assert GrafanaNormaliser().normalise(payload).service == "node-exporter"


def test_grafana_normalise_service_unknown_when_no_label():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {}}],
        "commonLabels": {},
    }
    assert GrafanaNormaliser().normalise(payload).service == "unknown"


def test_grafana_normalise_description_falls_back_to_summary():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [
            {
                **GRAFANA_PAYLOAD["alerts"][0],
                "annotations": {"summary": "Summary only"},
            }
        ],
    }
    assert GrafanaNormaliser().normalise(payload).description == "Summary only"


def test_grafana_normalise_description_falls_back_to_message():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "annotations": {}}],
    }
    assert GrafanaNormaliser().normalise(payload).description == "CPU usage is above 90%"


def test_grafana_normalise_common_labels_fill_missing_alert_labels():
    payload = {
        **GRAFANA_PAYLOAD,
        "alerts": [{**GRAFANA_PAYLOAD["alerts"][0], "labels": {}}],
        "commonLabels": {"service": "shared-svc", "severity": "warning"},
    }
    result = GrafanaNormaliser().normalise(payload)
    assert result.service == "shared-svc"
    assert result.severity == "medium"


def test_grafana_normalise_no_alerts_uses_payload_title():
    payload = {**GRAFANA_PAYLOAD, "alerts": []}
    result = GrafanaNormaliser().normalise(payload)
    assert result.title == "High CPU Usage"
    assert result.service == "unknown"


def test_grafana_normalise_raw_payload_preserved():
    result = GrafanaNormaliser().normalise(GRAFANA_PAYLOAD)
    assert result.raw_payload == GRAFANA_PAYLOAD


def test_grafana_normalise_received_at_is_datetime():
    result = GrafanaNormaliser().normalise(GRAFANA_PAYLOAD)
    assert isinstance(result.received_at, datetime)


# ---------------------------------------------------------------------------
# PagerDutyNormaliser — can_handle
# ---------------------------------------------------------------------------


def test_pagerduty_can_handle_valid_payload():
    assert PagerDutyNormaliser().can_handle(PAGERDUTY_PAYLOAD) is True


def test_pagerduty_can_handle_rejects_grafana_payload():
    assert PagerDutyNormaliser().can_handle(GRAFANA_PAYLOAD) is False


def test_pagerduty_can_handle_rejects_empty_dict():
    assert PagerDutyNormaliser().can_handle({}) is False


def test_pagerduty_can_handle_requires_event_to_be_dict():
    assert PagerDutyNormaliser().can_handle({"event": "string"}) is False


def test_pagerduty_can_handle_requires_event_type_in_event():
    assert PagerDutyNormaliser().can_handle({"event": {"data": {}}}) is False


def test_pagerduty_can_handle_requires_data_in_event():
    assert PagerDutyNormaliser().can_handle({"event": {"event_type": "incident.triggered"}}) is False


# ---------------------------------------------------------------------------
# PagerDutyNormaliser — normalise
# ---------------------------------------------------------------------------


def test_pagerduty_normalise_source():
    assert PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD).source == "pagerduty"


def test_pagerduty_normalise_title():
    result = PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD)
    assert result.title == "Production database down"


def test_pagerduty_normalise_description_from_body_details():
    result = PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD)
    assert result.description == "The production database is not responding to health checks."


def test_pagerduty_normalise_service_from_service_summary():
    result = PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD)
    assert result.service == "database-service"


def test_pagerduty_normalise_severity_high_urgency():
    result = PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD)
    assert result.severity == "high"


def test_pagerduty_normalise_severity_low_urgency():
    payload = {
        **PAGERDUTY_PAYLOAD,
        "event": {
            **PAGERDUTY_PAYLOAD["event"],
            "data": {**PAGERDUTY_PAYLOAD["event"]["data"], "urgency": "low"},
        },
    }
    assert PagerDutyNormaliser().normalise(payload).severity == "low"


def test_pagerduty_normalise_severity_unknown_when_urgency_missing():
    payload = {
        **PAGERDUTY_PAYLOAD,
        "event": {
            **PAGERDUTY_PAYLOAD["event"],
            "data": {**PAGERDUTY_PAYLOAD["event"]["data"], "urgency": ""},
        },
    }
    assert PagerDutyNormaliser().normalise(payload).severity == "unknown"


def test_pagerduty_normalise_service_unknown_when_no_summary():
    payload = {
        **PAGERDUTY_PAYLOAD,
        "event": {
            **PAGERDUTY_PAYLOAD["event"],
            "data": {
                **PAGERDUTY_PAYLOAD["event"]["data"],
                "service": {"id": "S1", "summary": "", "type": "service_reference"},
            },
        },
    }
    assert PagerDutyNormaliser().normalise(payload).service == "unknown"


def test_pagerduty_normalise_description_falls_back_to_title_when_no_details():
    payload = {
        **PAGERDUTY_PAYLOAD,
        "event": {
            **PAGERDUTY_PAYLOAD["event"],
            "data": {
                **PAGERDUTY_PAYLOAD["event"]["data"],
                "body": {"type": "incident_body", "details": ""},
            },
        },
    }
    result = PagerDutyNormaliser().normalise(payload)
    assert result.description == result.title


def test_pagerduty_normalise_raw_payload_preserved():
    result = PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD)
    assert result.raw_payload == PAGERDUTY_PAYLOAD


def test_pagerduty_normalise_received_at_is_datetime():
    result = PagerDutyNormaliser().normalise(PAGERDUTY_PAYLOAD)
    assert isinstance(result.received_at, datetime)


# ---------------------------------------------------------------------------
# GenericNormaliser — can_handle
# ---------------------------------------------------------------------------


def test_generic_can_handle_always_true():
    for payload in [{}, {"foo": "bar"}, GRAFANA_PAYLOAD, PAGERDUTY_PAYLOAD]:
        assert GenericNormaliser().can_handle(payload) is True


# ---------------------------------------------------------------------------
# GenericNormaliser — normalise
# ---------------------------------------------------------------------------


def test_generic_normalise_source():
    assert GenericNormaliser().normalise({"title": "x"}).source == "generic"


def test_generic_normalise_title_from_title_key():
    assert GenericNormaliser().normalise({"title": "My Alert"}).title == "My Alert"


def test_generic_normalise_title_from_name_key():
    assert GenericNormaliser().normalise({"name": "My Alert"}).title == "My Alert"


def test_generic_normalise_title_from_alertname_key():
    assert GenericNormaliser().normalise({"alertname": "HighDisk"}).title == "HighDisk"


def test_generic_normalise_title_from_message_key():
    assert GenericNormaliser().normalise({"message": "Something broke"}).title == "Something broke"


def test_generic_normalise_title_default_for_empty_payload():
    assert GenericNormaliser().normalise({}).title == "Unknown Alert"


def test_generic_normalise_description_from_description_key():
    result = GenericNormaliser().normalise({"title": "T", "description": "Full details"})
    assert result.description == "Full details"


def test_generic_normalise_description_falls_back_to_summary():
    result = GenericNormaliser().normalise({"title": "T", "summary": "Brief"})
    assert result.description == "Brief"


def test_generic_normalise_description_falls_back_to_title():
    result = GenericNormaliser().normalise({"title": "Only Title"})
    assert result.description == "Only Title"


def test_generic_normalise_service_from_service_key():
    assert GenericNormaliser().normalise({"service": "payments"}).service == "payments"


def test_generic_normalise_service_from_job_key():
    assert GenericNormaliser().normalise({"job": "node-exporter"}).service == "node-exporter"


def test_generic_normalise_service_from_source_key():
    assert GenericNormaliser().normalise({"source": "datadog"}).service == "datadog"


def test_generic_normalise_service_unknown_when_absent():
    assert GenericNormaliser().normalise({}).service == "unknown"


def test_generic_normalise_severity_canonical_values():
    for sev in ("critical", "high", "medium", "low"):
        assert GenericNormaliser().normalise({"severity": sev}).severity == sev


def test_generic_normalise_severity_warning_alias():
    assert GenericNormaliser().normalise({"severity": "warning"}).severity == "medium"


def test_generic_normalise_severity_error_alias():
    assert GenericNormaliser().normalise({"severity": "error"}).severity == "high"


def test_generic_normalise_severity_info_alias():
    assert GenericNormaliser().normalise({"severity": "info"}).severity == "low"


def test_generic_normalise_severity_urgency_key_fallback():
    assert GenericNormaliser().normalise({"urgency": "high"}).severity == "high"


def test_generic_normalise_severity_unknown_for_unrecognised():
    assert GenericNormaliser().normalise({"severity": "blocker"}).severity == "unknown"


def test_generic_normalise_severity_unknown_when_absent():
    assert GenericNormaliser().normalise({}).severity == "unknown"


def test_generic_normalise_raw_payload_preserved():
    payload = {"title": "T", "extra": "data"}
    assert GenericNormaliser().normalise(payload).raw_payload == payload


def test_generic_normalise_received_at_is_datetime():
    assert isinstance(GenericNormaliser().normalise({}).received_at, datetime)


# ---------------------------------------------------------------------------
# NormaliserRegistry — routing
# ---------------------------------------------------------------------------


def test_registry_routes_grafana_payload():
    result = normalise(GRAFANA_PAYLOAD)
    assert result.source == "grafana"


def test_registry_routes_pagerduty_payload():
    result = normalise(PAGERDUTY_PAYLOAD)
    assert result.source == "pagerduty"


def test_registry_routes_unknown_payload_to_generic():
    result = normalise({"some": "random", "alert": "data"})
    assert result.source == "generic"


def test_registry_routes_empty_dict_to_generic():
    result = normalise({})
    assert result.source == "generic"


def test_registry_returns_normalised_alert():
    from app.models.alert import NormalisedAlert

    assert isinstance(normalise(GRAFANA_PAYLOAD), NormalisedAlert)
    assert isinstance(normalise(PAGERDUTY_PAYLOAD), NormalisedAlert)
    assert isinstance(normalise({}), NormalisedAlert)

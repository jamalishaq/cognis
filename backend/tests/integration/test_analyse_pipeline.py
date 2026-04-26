"""Integration tests for POST /analyse — moto mocks DynamoDB + SQS; pipeline stages are patched."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.models.alert import NormalisedAlert
from app.models.incident import IncidentBrief
from app.models.triage import TriageResult
from app.pipeline.retrieval import RetrievalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GRAFANA_PAYLOAD = {
    "title": "High error rate",
    "state": "alerting",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "HighErrorRate", "severity": "critical", "service": "payments-service"},
            "annotations": {"description": "5xx rate exceeded 18%"},
            "startsAt": "2026-04-23T14:35:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "",
            "fingerprint": "abc123",
        }
    ],
}

_TRIAGE = TriageResult(service="payments-service", severity="critical", failure_class="connection_exhaustion")

_RETRIEVAL = RetrievalResult(
    chunks=["Runbook: increase APP_DB_POOL_MAX and redeploy"],
    retrieval_context_available=True,
)

_CREATED_AT = datetime(2026, 4, 23, 14, 35, 5, tzinfo=timezone.utc)


def _make_brief(incident_id: str = "INC-20260423-001") -> IncidentBrief:
    return IncidentBrief(
        incident_id=incident_id,
        title="payments-service connection pool exhausted",
        summary="DB connection pool exhausted after v2.14.3 deploy.",
        severity="critical",
        affected_service="payments-service",
        failure_class="connection_exhaustion",
        recommended_actions=["Increase APP_DB_POOL_MAX and redeploy"],
        runbook_references=["runbooks/postgres/connection-pool-exhaustion.md"],
        retrieval_context_available=True,
        created_at=_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def aws_mock(monkeypatch):
    """Start moto, create Incidents table + notification queue, reset service singletons."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    with mock_aws():
        import app.services.dynamodb as ddb_svc
        import app.services.sqs as sqs_svc

        ddb_svc._resource = None
        sqs_svc._client = None

        # Create Incidents table
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="Incidents",
            KeySchema=[{"AttributeName": "incident_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "incident_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create notification queue
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue_url = sqs.create_queue(QueueName="test-notifications")["QueueUrl"]

        monkeypatch.setattr("app.config.settings.notification_queue_url", queue_url)
        monkeypatch.setattr("app.config.settings.aws_region", "us-east-1")
        # Ensure no local endpoint override so moto intercepts
        monkeypatch.setattr("app.config.settings.dynamodb_endpoint", "")
        monkeypatch.setattr("app.config.settings.sqs_endpoint", "")

        yield {"dynamodb": ddb, "sqs": sqs, "queue_url": queue_url, "table": ddb.Table("Incidents")}

        ddb_svc._resource = None
        sqs_svc._client = None


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_analyse_returns_200_with_incident_id(aws_mock, client):
    brief = _make_brief()
    with (
        patch("app.api.analyse.normaliser.normalise") as mock_norm,
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        mock_norm.return_value = NormalisedAlert(
            source="grafana",
            title="High error rate",
            description="5xx rate exceeded 18%",
            severity="critical",
            service="payments-service",
            raw_payload=_GRAFANA_PAYLOAD,
            received_at=_CREATED_AT,
        )
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "received"
    assert body["incident_id"].startswith("INC-")
    assert "timestamp" in body


def test_analyse_stores_incident_in_dynamodb(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana",
        title="High error rate",
        description="5xx rate exceeded 18%",
        severity="critical",
        service="payments-service",
        raw_payload=_GRAFANA_PAYLOAD,
        received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 200
    incident_id = response.json()["incident_id"]

    item = aws_mock["table"].get_item(Key={"incident_id": incident_id})["Item"]
    assert item["incident_id"] == incident_id
    assert item["severity"] == "critical"
    assert item["affected_service"] == "payments-service"
    assert item["failure_class"] == "connection_exhaustion"
    assert item["status"] == "open"
    assert item["source"] == "grafana"
    assert item["retrieval_context_available"] is True


def test_analyse_stored_record_has_all_expected_fields(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana",
        title="High error rate",
        description="5xx rate exceeded 18%",
        severity="critical",
        service="payments-service",
        raw_payload=_GRAFANA_PAYLOAD,
        received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    incident_id = response.json()["incident_id"]
    item = aws_mock["table"].get_item(Key={"incident_id": incident_id})["Item"]

    required_fields = [
        "incident_id", "title", "summary", "severity", "affected_service",
        "failure_class", "recommended_actions", "status", "created_at", "source",
    ]
    for field in required_fields:
        assert field in item, f"Missing field: {field}"


def test_analyse_drops_sqs_notification(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana",
        title="High error rate",
        description="5xx rate exceeded 18%",
        severity="critical",
        service="payments-service",
        raw_payload=_GRAFANA_PAYLOAD,
        received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    messages = aws_mock["sqs"].receive_message(
        QueueUrl=aws_mock["queue_url"],
        MaxNumberOfMessages=1,
    ).get("Messages", [])

    assert len(messages) == 1
    body = json.loads(messages[0]["Body"])
    assert body["severity"] == "critical"
    assert body["affected_service"] == "payments-service"
    assert "incident_id" in body
    assert "recommended_actions" in body


def test_analyse_sqs_message_contains_all_notification_fields(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana",
        title="High error rate",
        description="5xx rate exceeded 18%",
        severity="critical",
        service="payments-service",
        raw_payload=_GRAFANA_PAYLOAD,
        received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    messages = aws_mock["sqs"].receive_message(
        QueueUrl=aws_mock["queue_url"], MaxNumberOfMessages=1
    ).get("Messages", [])
    body = json.loads(messages[0]["Body"])

    for field in ["incident_id", "title", "severity", "affected_service", "failure_class", "summary", "created_at", "recommended_actions"]:
        assert field in body, f"Missing SQS field: {field}"


# ---------------------------------------------------------------------------
# Incident ID format
# ---------------------------------------------------------------------------

def test_analyse_incident_id_has_correct_format(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="generic", title="Test", description="Test",
        severity="unknown", service="", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        response = client.post("/analyse", json={})

    incident_id = response.json()["incident_id"]
    import re
    assert re.match(r"^INC-\d{8}-\d{3}$", incident_id), f"Bad format: {incident_id}"


def test_analyse_second_incident_gets_incremented_id(aws_mock, client):
    alert = NormalisedAlert(
        source="generic", title="Test", description="Test",
        severity="unknown", service="", raw_payload={}, received_at=_CREATED_AT,
    )

    ids = []
    for i in range(2):
        # Each call needs a fresh brief matching what agent.run would produce
        incident_id_for_brief = f"INC-20260423-00{i + 1}"
        brief = _make_brief(incident_id=incident_id_for_brief)
        with (
            patch("app.api.analyse.normaliser.normalise", return_value=alert),
            patch("app.api.analyse.triage.run", return_value=_TRIAGE),
            patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
            patch("app.api.analyse.agent.run", return_value=brief),
        ):
            response = client.post("/analyse", json={})
        assert response.status_code == 200
        ids.append(response.json()["incident_id"])

    assert ids[0] != ids[1], "Sequential incidents should have different IDs"


# ---------------------------------------------------------------------------
# Error handling — triage failure → 503
# ---------------------------------------------------------------------------

def test_analyse_triage_failure_returns_503(aws_mock, client):
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="unknown", service="", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", side_effect=RuntimeError("Bedrock unavailable")),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "triage_failed"
    assert body["detail"]["incident_id"] is None


def test_analyse_triage_failure_does_not_store_incident(aws_mock, client):
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="unknown", service="", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", side_effect=RuntimeError("fail")),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    items = aws_mock["table"].scan()["Items"]
    assert len(items) == 0


def test_analyse_triage_failure_does_not_send_sqs(aws_mock, client):
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="unknown", service="", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", side_effect=RuntimeError("fail")),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    messages = aws_mock["sqs"].receive_message(
        QueueUrl=aws_mock["queue_url"], MaxNumberOfMessages=1
    ).get("Messages", [])
    assert len(messages) == 0


# ---------------------------------------------------------------------------
# Error handling — agent failure → 503
# ---------------------------------------------------------------------------

def test_analyse_agent_failure_returns_503(aws_mock, client):
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", side_effect=RuntimeError("Agent timeout")),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "agent_failed"
    assert body["detail"]["incident_id"] is not None


def test_analyse_agent_failure_includes_incident_id_in_error(aws_mock, client):
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", side_effect=RuntimeError("fail")),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    import re
    incident_id = response.json()["detail"]["incident_id"]
    assert re.match(r"^INC-\d{8}-\d{3}$", incident_id)


def test_analyse_agent_failure_does_not_store_incident(aws_mock, client):
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", side_effect=RuntimeError("fail")),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    items = aws_mock["table"].scan()["Items"]
    assert len(items) == 0


# ---------------------------------------------------------------------------
# Error handling — DynamoDB write failure → log + still return 200
# ---------------------------------------------------------------------------

def test_analyse_dynamodb_write_failure_still_returns_200(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
        patch("app.api.analyse.dynamodb.put_item", side_effect=Exception("DynamoDB unavailable")),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_analyse_dynamodb_write_failure_still_sends_sqs(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
        patch("app.api.analyse.dynamodb.put_item", side_effect=Exception("DynamoDB unavailable")),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    messages = aws_mock["sqs"].receive_message(
        QueueUrl=aws_mock["queue_url"], MaxNumberOfMessages=1
    ).get("Messages", [])
    assert len(messages) == 1


# ---------------------------------------------------------------------------
# Error handling — SQS failure → log warning + still return 200
# ---------------------------------------------------------------------------

def test_analyse_sqs_failure_still_returns_200(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
        patch("app.api.analyse.sqs.send_message", side_effect=Exception("SQS unavailable")),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_analyse_sqs_failure_still_stores_incident(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", return_value=brief),
        patch("app.api.analyse.sqs.send_message", side_effect=Exception("SQS unavailable")),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    incident_id = response.json()["incident_id"]
    item = aws_mock["table"].get_item(Key={"incident_id": incident_id}).get("Item")
    assert item is not None


# ---------------------------------------------------------------------------
# RAG degradation — retrieval_context_available=False → still returns 200
# ---------------------------------------------------------------------------

def test_analyse_rag_degradation_returns_200(aws_mock, client):
    degraded_retrieval = RetrievalResult(chunks=[], retrieval_context_available=False)
    brief = IncidentBrief(
        incident_id="INC-20260423-001",
        title="payments-service issue",
        summary="Diagnosis based on triage only — context retrieval failed.",
        severity="critical",
        affected_service="payments-service",
        failure_class="connection_exhaustion",
        recommended_actions=[],
        runbook_references=[],
        retrieval_context_available=False,
        created_at=_CREATED_AT,
    )
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=degraded_retrieval),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 200
    incident_id = response.json()["incident_id"]
    item = aws_mock["table"].get_item(Key={"incident_id": incident_id})["Item"]
    assert item["retrieval_context_available"] is False


# ---------------------------------------------------------------------------
# Pipeline call order
# ---------------------------------------------------------------------------

def test_analyse_calls_pipeline_stages_in_order(aws_mock, client):
    call_order = []
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )

    def record(name, return_val):
        def fn(*args, **kwargs):
            call_order.append(name)
            return return_val
        return fn

    with (
        patch("app.api.analyse.normaliser.normalise", side_effect=record("normalise", alert)),
        patch("app.api.analyse.triage.run", side_effect=record("triage", _TRIAGE)),
        patch("app.api.analyse.retrieval.run", side_effect=record("retrieval", _RETRIEVAL)),
        patch("app.api.analyse.agent.run", side_effect=record("agent", brief)),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert response.status_code == 200
    assert call_order == ["normalise", "triage", "retrieval", "agent"]


def test_analyse_passes_triage_result_to_retrieval(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    captured = {}

    def capture_retrieval(triage_result):
        captured["triage"] = triage_result
        return _RETRIEVAL

    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", side_effect=capture_retrieval),
        patch("app.api.analyse.agent.run", return_value=brief),
    ):
        client.post("/analyse", json=_GRAFANA_PAYLOAD)

    assert captured["triage"] is _TRIAGE


def test_analyse_passes_incident_id_to_agent(aws_mock, client):
    brief = _make_brief()
    alert = NormalisedAlert(
        source="grafana", title="Test", description="Test",
        severity="critical", service="payments-service", raw_payload={}, received_at=_CREATED_AT,
    )
    captured = {}

    def capture_agent(alert_arg, triage_arg, retrieval_arg, incident_id):
        captured["incident_id"] = incident_id
        return brief

    with (
        patch("app.api.analyse.normaliser.normalise", return_value=alert),
        patch("app.api.analyse.triage.run", return_value=_TRIAGE),
        patch("app.api.analyse.retrieval.run", return_value=_RETRIEVAL),
        patch("app.api.analyse.agent.run", side_effect=capture_agent),
    ):
        response = client.post("/analyse", json=_GRAFANA_PAYLOAD)

    import re
    assert re.match(r"^INC-\d{8}-\d{3}$", captured["incident_id"])
    # The incident_id passed to agent matches the one returned in response
    assert captured["incident_id"] == response.json()["incident_id"]

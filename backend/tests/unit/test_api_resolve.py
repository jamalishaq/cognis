from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_OPEN_INCIDENT = {
    "incident_id": "INC-20240101-001",
    "title": "Database connection pool exhausted",
    "summary": "Payment service cannot acquire DB connections.",
    "severity": "high",
    "affected_service": "payment-service",
    "failure_class": "resource_exhaustion",
    "recommended_actions": ["Restart service"],
    "runbook_references": [],
    "retrieval_context_available": True,
    "created_at": "2024-01-01T00:00:00+00:00",
    "status": "open",
    "resolved_at": None,
    "resolution_notes": None,
    "resolved_by": None,
}

_RESOLVE_BODY = {
    "incident_id": "INC-20240101-001",
    "resolution_notes": "Restarted service and increased pool size.",
    "resolved_by": "ops-team",
}


# ---------------------------------------------------------------------------
# POST /incidents/{id}/resolve — happy path
# ---------------------------------------------------------------------------


@patch("app.services.sqs.send_message", return_value="msg-123")
@patch("app.services.dynamodb.update_item", return_value={})
@patch("app.services.dynamodb.get_item", return_value=_OPEN_INCIDENT)
def test_resolve_returns_200(mock_get, mock_update, mock_sqs):
    response = client.post("/incidents/INC-20240101-001/resolve", json=_RESOLVE_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-20240101-001"
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None
    assert data["message"] == "Incident resolved successfully"


@patch("app.services.sqs.send_message", return_value="msg-123")
@patch("app.services.dynamodb.update_item", return_value={})
@patch("app.services.dynamodb.get_item", return_value=_OPEN_INCIDENT)
def test_resolve_updates_correct_fields(mock_get, mock_update, mock_sqs):
    client.post("/incidents/INC-20240101-001/resolve", json=_RESOLVE_BODY)

    _, call_kwargs = mock_update.call_args
    # update_item is called positionally: (table_name, key, updates)
    args = mock_update.call_args[0]
    table, key, updates = args
    assert table == "Incidents"
    assert key == {"incident_id": "INC-20240101-001"}
    assert updates["status"] == "resolved"
    assert updates["resolution_notes"] == "Restarted service and increased pool size."
    assert updates["resolved_by"] == "ops-team"
    assert "resolved_at" in updates


@patch("app.services.sqs.send_message", return_value="msg-123")
@patch("app.services.dynamodb.update_item", return_value={})
@patch("app.services.dynamodb.get_item", return_value=_OPEN_INCIDENT)
def test_resolve_sends_ingestion_sqs_message(mock_get, mock_update, mock_sqs):
    client.post("/incidents/INC-20240101-001/resolve", json=_RESOLVE_BODY)

    mock_sqs.assert_called_once()
    sqs_args = mock_sqs.call_args[0]
    _queue_url, body = sqs_args
    assert body["type"] == "incident_resolution"
    assert body["incident_id"] == "INC-20240101-001"
    assert body["resolution_notes"] == "Restarted service and increased pool size."
    assert "resolved_at" in body


@patch("app.services.sqs.send_message", return_value="msg-123")
@patch("app.services.dynamodb.update_item", return_value={})
@patch("app.services.dynamodb.get_item", return_value=_OPEN_INCIDENT)
def test_resolve_without_resolved_by(mock_get, mock_update, mock_sqs):
    body = {**_RESOLVE_BODY, "resolved_by": None}
    response = client.post("/incidents/INC-20240101-001/resolve", json=body)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /incidents/{id}/resolve — error cases
# ---------------------------------------------------------------------------


@patch("app.services.dynamodb.get_item", return_value=None)
def test_resolve_returns_404_when_incident_missing(mock_get):
    response = client.post("/incidents/INC-20240101-999/resolve", json={
        **_RESOLVE_BODY,
        "incident_id": "INC-20240101-999",
    })

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "incident_not_found"


@patch("app.services.dynamodb.get_item", return_value={**_OPEN_INCIDENT, "status": "resolved"})
def test_resolve_returns_409_when_already_resolved(mock_get):
    response = client.post("/incidents/INC-20240101-001/resolve", json=_RESOLVE_BODY)

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "already_resolved"


def test_resolve_returns_422_when_incident_id_mismatch():
    response = client.post("/incidents/INC-20240101-001/resolve", json={
        **_RESOLVE_BODY,
        "incident_id": "INC-20240101-002",
    })

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "incident_id_mismatch"


@patch("app.services.dynamodb.update_item", side_effect=Exception("DynamoDB error"))
@patch("app.services.dynamodb.get_item", return_value=_OPEN_INCIDENT)
def test_resolve_returns_503_when_dynamodb_update_fails(mock_get, mock_update):
    response = client.post("/incidents/INC-20240101-001/resolve", json=_RESOLVE_BODY)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "storage_failed"


@patch("app.services.sqs.send_message", side_effect=Exception("SQS unavailable"))
@patch("app.services.dynamodb.update_item", return_value={})
@patch("app.services.dynamodb.get_item", return_value=_OPEN_INCIDENT)
def test_resolve_succeeds_when_sqs_fails(mock_get, mock_update, mock_sqs):
    # SQS failure is non-blocking — response should still be 200
    response = client.post("/incidents/INC-20240101-001/resolve", json=_RESOLVE_BODY)

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"

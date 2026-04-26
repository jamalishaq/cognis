from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_INCIDENT = {
    "incident_id": "INC-20240101-001",
    "title": "Database connection pool exhausted",
    "summary": "Payment service cannot acquire DB connections.",
    "severity": "high",
    "affected_service": "payment-service",
    "failure_class": "resource_exhaustion",
    "recommended_actions": ["Restart service", "Scale connection pool"],
    "runbook_references": ["runbook-db-pool.md"],
    "retrieval_context_available": True,
    "created_at": "2024-01-01T00:00:00+00:00",
    "status": "open",
    "resolved_at": None,
    "resolution_notes": None,
    "resolved_by": None,
}

_MESSAGES = [
    {
        "message_id": "MSG-001",
        "incident_id": "INC-20240101-001",
        "role": "user",
        "content": "What happened?",
        "timestamp": "2024-01-01T00:01:00+00:00",
    },
    {
        "message_id": "MSG-002",
        "incident_id": "INC-20240101-001",
        "role": "assistant",
        "content": "Connection pool exhaustion detected.",
        "timestamp": "2024-01-01T00:02:00+00:00",
    },
]


# ---------------------------------------------------------------------------
# GET /incidents/{id}
# ---------------------------------------------------------------------------


@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_incident_returns_200(mock_get):
    response = client.get("/incidents/INC-20240101-001")

    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-20240101-001"
    assert data["title"] == "Database connection pool exhausted"
    assert data["severity"] == "high"
    assert data["status"] == "open"
    mock_get.assert_called_once_with("Incidents", {"incident_id": "INC-20240101-001"})


@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_incident_returns_full_record_fields(mock_get):
    response = client.get("/incidents/INC-20240101-001")
    data = response.json()

    assert data["affected_service"] == "payment-service"
    assert data["failure_class"] == "resource_exhaustion"
    assert data["recommended_actions"] == ["Restart service", "Scale connection pool"]
    assert data["runbook_references"] == ["runbook-db-pool.md"]
    assert data["retrieval_context_available"] is True


@patch("app.services.dynamodb.get_item", return_value=None)
def test_get_incident_returns_404_when_missing(mock_get):
    response = client.get("/incidents/INC-20240101-999")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "incident_not_found"
    assert response.json()["detail"]["incident_id"] == "INC-20240101-999"


@patch(
    "app.services.dynamodb.get_item",
    return_value={**_INCIDENT, "status": "resolved", "resolved_at": "2024-01-01T01:00:00+00:00"},
)
def test_get_incident_returns_resolved_record(mock_get):
    response = client.get("/incidents/INC-20240101-001")
    data = response.json()

    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None


# ---------------------------------------------------------------------------
# GET /incidents/{id}/history
# ---------------------------------------------------------------------------


@patch("app.services.dynamodb.scan", return_value=_MESSAGES)
@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_history_returns_200(mock_get, mock_scan):
    response = client.get("/incidents/INC-20240101-001/history")

    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-20240101-001"
    assert len(data["messages"]) == 2


@patch("app.services.dynamodb.scan", return_value=_MESSAGES)
@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_history_messages_sorted_by_timestamp(mock_get, mock_scan):
    # Reverse the messages to verify sorting is applied
    mock_scan.return_value = list(reversed(_MESSAGES))
    response = client.get("/incidents/INC-20240101-001/history")
    data = response.json()

    timestamps = [m["timestamp"] for m in data["messages"]]
    assert timestamps == sorted(timestamps)


@patch("app.services.dynamodb.scan", return_value=_MESSAGES)
@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_history_message_fields(mock_get, mock_scan):
    response = client.get("/incidents/INC-20240101-001/history")
    msg = response.json()["messages"][0]

    assert msg["message_id"] == "MSG-001"
    assert msg["role"] == "user"
    assert msg["content"] == "What happened?"


@patch("app.services.dynamodb.scan", return_value=[])
@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_history_returns_empty_list_when_no_messages(mock_get, mock_scan):
    response = client.get("/incidents/INC-20240101-001/history")
    data = response.json()

    assert data["messages"] == []


@patch("app.services.dynamodb.get_item", return_value=None)
def test_get_history_returns_404_when_incident_missing(mock_get):
    response = client.get("/incidents/INC-20240101-999/history")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "incident_not_found"


@patch("app.services.dynamodb.scan", return_value=_MESSAGES)
@patch("app.services.dynamodb.get_item", return_value=_INCIDENT)
def test_get_history_scans_correct_table(mock_get, mock_scan):
    client.get("/incidents/INC-20240101-001/history")

    table_name = mock_scan.call_args[0][0]
    assert table_name == "ChatMessages"

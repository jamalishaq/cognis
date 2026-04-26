"""Integration tests for POST /chat — moto mocks DynamoDB; pipeline stages are patched."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.pipeline.retrieval import RetrievalResult

_INCIDENT_ID = "INC-20260423-001"
_CREATED_AT = datetime(2026, 4, 23, 14, 35, 5, tzinfo=timezone.utc)

_INCIDENT_ITEM = {
    "incident_id": _INCIDENT_ID,
    "title": "payments-service connection pool exhausted",
    "summary": "DB connection pool exhausted after v2.14.3 deploy.",
    "severity": "critical",
    "affected_service": "payments-service",
    "failure_class": "connection_exhaustion",
    "recommended_actions": ["Increase APP_DB_POOL_MAX and redeploy"],
    "runbook_references": ["runbooks/postgres/connection-pool-exhaustion.md"],
    "retrieval_context_available": True,
    "status": "open",
    "created_at": _CREATED_AT.isoformat(),
    "source": "grafana",
    "raw_payload": {},
}

_RETRIEVAL_RESULT = RetrievalResult(
    chunks=["Runbook: increase APP_DB_POOL_MAX and redeploy"],
    retrieval_context_available=True,
)

_CHAT_REQUEST = {"incident_id": _INCIDENT_ID, "message": "What should I do first?"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def aws_mock(monkeypatch):
    """Start moto, create Incidents + ChatMessages tables, reset DynamoDB singleton."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    with mock_aws():
        import app.services.dynamodb as ddb_svc

        ddb_svc._resource = None

        ddb = boto3.resource("dynamodb", region_name="us-east-1")

        incidents = ddb.create_table(
            TableName="Incidents",
            KeySchema=[{"AttributeName": "incident_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "incident_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        chat_messages = ddb.create_table(
            TableName="ChatMessages",
            KeySchema=[{"AttributeName": "message_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "message_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        monkeypatch.setattr("app.config.settings.aws_region", "us-east-1")
        monkeypatch.setattr("app.config.settings.dynamodb_endpoint", "")

        yield {
            "dynamodb": ddb,
            "incidents": incidents,
            "chat_messages": chat_messages,
        }

        ddb_svc._resource = None


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def incident_in_db(aws_mock):
    aws_mock["incidents"].put_item(Item=_INCIDENT_ITEM)
    return _INCIDENT_ITEM


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_chat_returns_streaming_response(aws_mock, client, incident_in_db):
    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", return_value=iter(["Increase ", "the pool ", "size."])),
    ):
        response = client.post("/chat", json=_CHAT_REQUEST, headers={"Accept": "text/plain"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Increase the pool size."


def test_chat_streams_response_in_chunks(aws_mock, client, incident_in_db):
    """Content arrives as a stream, not a single payload."""
    chunks_seen: list[str] = []

    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", return_value=iter(["chunk1", "chunk2", "chunk3"])),
    ):
        with client.stream("POST", "/chat", json=_CHAT_REQUEST) as response:
            assert response.status_code == 200
            for chunk in response.iter_text():
                if chunk:
                    chunks_seen.append(chunk)

    assert "".join(chunks_seen) == "chunk1chunk2chunk3"


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------


def test_chat_passes_incident_context_to_agent(aws_mock, client, incident_in_db):
    """chat_agent.run receives the incident dict and rag_chunks."""
    captured: dict = {}

    def fake_chat_agent(incident, history, user_message, rag_chunks):
        captured["incident"] = incident
        captured["history"] = history
        captured["user_message"] = user_message
        captured["rag_chunks"] = rag_chunks
        return iter(["ok"])

    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", side_effect=fake_chat_agent),
    ):
        response = client.post("/chat", json=_CHAT_REQUEST)

    assert response.status_code == 200
    assert captured["incident"]["incident_id"] == _INCIDENT_ID
    assert captured["incident"]["affected_service"] == "payments-service"
    assert captured["user_message"] == "What should I do first?"
    assert captured["rag_chunks"] == ["Runbook: increase APP_DB_POOL_MAX and redeploy"]


def test_chat_passes_existing_history_to_agent(aws_mock, client, incident_in_db):
    """Prior ChatMessages for the incident are loaded and passed to the agent."""
    aws_mock["chat_messages"].put_item(
        Item={
            "message_id": "MSG-001",
            "incident_id": _INCIDENT_ID,
            "role": "user",
            "content": "Is this a known issue?",
            "timestamp": "2026-04-23T14:40:00+00:00",
        }
    )
    aws_mock["chat_messages"].put_item(
        Item={
            "message_id": "MSG-002",
            "incident_id": _INCIDENT_ID,
            "role": "assistant",
            "content": "Yes, this pattern recurs after large deploys.",
            "timestamp": "2026-04-23T14:40:10+00:00",
        }
    )

    captured: dict = {}

    def fake_chat_agent(incident, history, user_message, rag_chunks):
        captured["history"] = history
        return iter(["ok"])

    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", side_effect=fake_chat_agent),
    ):
        client.post("/chat", json=_CHAT_REQUEST)

    assert len(captured["history"]) == 2
    roles = [m["role"] for m in captured["history"]]
    assert roles == ["user", "assistant"]


def test_chat_passes_empty_history_for_first_message(aws_mock, client, incident_in_db):
    captured: dict = {}

    def fake_chat_agent(incident, history, user_message, rag_chunks):
        captured["history"] = history
        return iter(["ok"])

    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", side_effect=fake_chat_agent),
    ):
        client.post("/chat", json=_CHAT_REQUEST)

    assert captured["history"] == []


def test_chat_uses_incident_triage_fields_for_retrieval(aws_mock, client, incident_in_db):
    """retrieval.run is called with a TriageResult derived from the stored incident."""
    captured: dict = {}

    def fake_retrieval(triage_result):
        captured["triage"] = triage_result
        return _RETRIEVAL_RESULT

    with (
        patch("app.api.chat.retrieval.run", side_effect=fake_retrieval),
        patch("app.api.chat.chat_agent.run", return_value=iter(["ok"])),
    ):
        client.post("/chat", json=_CHAT_REQUEST)

    assert captured["triage"].service == "payments-service"
    assert captured["triage"].severity == "critical"
    assert captured["triage"].failure_class == "connection_exhaustion"


# ---------------------------------------------------------------------------
# Message storage
# ---------------------------------------------------------------------------


def test_chat_stores_user_and_assistant_messages(aws_mock, client, incident_in_db):
    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", return_value=iter(["Increase the pool size."])),
    ):
        client.post("/chat", json=_CHAT_REQUEST)

    items = aws_mock["chat_messages"].scan()["Items"]
    assert len(items) == 2

    by_role = {item["role"]: item for item in items}
    assert "user" in by_role
    assert "assistant" in by_role

    assert by_role["user"]["content"] == "What should I do first?"
    assert by_role["user"]["incident_id"] == _INCIDENT_ID
    assert by_role["user"]["message_id"] == "MSG-001"

    assert by_role["assistant"]["content"] == "Increase the pool size."
    assert by_role["assistant"]["incident_id"] == _INCIDENT_ID
    assert by_role["assistant"]["message_id"] == "MSG-002"


def test_chat_message_ids_are_sequential(aws_mock, client, incident_in_db):
    """Second exchange should produce MSG-003 and MSG-004."""
    aws_mock["chat_messages"].put_item(
        Item={
            "message_id": "MSG-001",
            "incident_id": _INCIDENT_ID,
            "role": "user",
            "content": "Prior question",
            "timestamp": "2026-04-23T14:39:00+00:00",
        }
    )
    aws_mock["chat_messages"].put_item(
        Item={
            "message_id": "MSG-002",
            "incident_id": _INCIDENT_ID,
            "role": "assistant",
            "content": "Prior answer",
            "timestamp": "2026-04-23T14:39:05+00:00",
        }
    )

    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", return_value=iter(["New answer."])),
    ):
        client.post("/chat", json=_CHAT_REQUEST)

    items = aws_mock["chat_messages"].scan()["Items"]
    msg_ids = {item["message_id"] for item in items}
    assert "MSG-003" in msg_ids
    assert "MSG-004" in msg_ids


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_chat_404_on_unknown_incident(aws_mock, client):
    response = client.post(
        "/chat",
        json={"incident_id": "INC-20260423-999", "message": "hello"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "incident_not_found"


def test_chat_agent_failure_returns_error_text(aws_mock, client, incident_in_db):
    def exploding_agent(incident, history, user_message, rag_chunks):
        raise RuntimeError("Bedrock unavailable")

    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", side_effect=exploding_agent),
    ):
        response = client.post("/chat", json=_CHAT_REQUEST)

    assert response.status_code == 200
    assert "Unable to process your request" in response.text


def test_chat_retrieval_degradation_still_responds(aws_mock, client, incident_in_db):
    """RAG failure (no chunks) should not block the response."""
    degraded = RetrievalResult(chunks=[], retrieval_context_available=False)

    with (
        patch("app.api.chat.retrieval.run", return_value=degraded),
        patch("app.api.chat.chat_agent.run", return_value=iter(["Best effort answer."])),
    ):
        response = client.post("/chat", json=_CHAT_REQUEST)

    assert response.status_code == 200
    assert response.text == "Best effort answer."


def test_chat_storage_failure_does_not_prevent_response(aws_mock, client, incident_in_db):
    """DynamoDB write errors are swallowed — the response still streams."""
    with (
        patch("app.api.chat.retrieval.run", return_value=_RETRIEVAL_RESULT),
        patch("app.api.chat.chat_agent.run", return_value=iter(["Here's your answer."])),
        patch("app.api.chat.dynamodb.put_item", side_effect=Exception("DynamoDB down")),
    ):
        response = client.post("/chat", json=_CHAT_REQUEST)

    assert response.status_code == 200
    assert response.text == "Here's your answer."

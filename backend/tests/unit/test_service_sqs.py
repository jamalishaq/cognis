import json
from unittest.mock import MagicMock, patch

import pytest

import app.services.sqs as sqs_module
from app.services.sqs import send_message


@pytest.fixture(autouse=True)
def reset_client():
    sqs_module._client = None
    yield
    sqs_module._client = None


@patch("app.services.sqs._get_client")
def test_send_message_returns_message_id(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.send_message.return_value = {"MessageId": "abc-123"}

    result = send_message("https://sqs.us-east-1.amazonaws.com/123/notify", {"event": "alert"})

    assert result == "abc-123"


@patch("app.services.sqs._get_client")
def test_send_message_serialises_body_as_json(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.send_message.return_value = {"MessageId": "msg-1"}

    body = {"incident_id": "INC-20240101-001", "severity": "critical"}
    send_message("https://sqs.us-east-1.amazonaws.com/123/notify", body)

    _, kwargs = mock_client.send_message.call_args
    sent_body = json.loads(kwargs["MessageBody"])
    assert sent_body == body


@patch("app.services.sqs._get_client")
def test_send_message_passes_queue_url(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.send_message.return_value = {"MessageId": "x"}

    queue_url = "https://sqs.us-east-1.amazonaws.com/123456/notification-queue"
    send_message(queue_url, {})

    _, kwargs = mock_client.send_message.call_args
    assert kwargs["QueueUrl"] == queue_url


@patch("app.services.sqs._get_client")
def test_send_message_notification_queue(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.send_message.return_value = {"MessageId": "notif-id"}

    result = send_message(
        "https://sqs.us-east-1.amazonaws.com/123/notification-queue",
        {"type": "incident_created", "incident_id": "INC-20240101-001"},
    )

    assert result == "notif-id"
    mock_client.send_message.assert_called_once()


@patch("app.services.sqs._get_client")
def test_send_message_ingestion_queue(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.send_message.return_value = {"MessageId": "ingest-id"}

    result = send_message(
        "https://sqs.us-east-1.amazonaws.com/123/ingestion-queue",
        {"file_path": "runbooks/db_runbook.md"},
    )

    assert result == "ingest-id"


@patch("app.services.sqs._get_client")
def test_send_message_body_is_valid_json_string(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.send_message.return_value = {"MessageId": "y"}

    send_message("https://sqs.us-east-1.amazonaws.com/123/q", {"nested": {"key": "value"}})

    _, kwargs = mock_client.send_message.call_args
    # Must be a string that can be parsed as JSON
    parsed = json.loads(kwargs["MessageBody"])
    assert parsed == {"nested": {"key": "value"}}

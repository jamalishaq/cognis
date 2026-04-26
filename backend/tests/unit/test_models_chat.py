from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.chat import ChatHistoryResponse, ChatMessage, ChatRequest

NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

VALID_MESSAGE = dict(
    message_id="MSG-001",
    incident_id="INC-20240601-001",
    role="user",
    content="What caused this incident?",
    timestamp=NOW,
)


# ---------------------------------------------------------------------------
# ChatRequest
# ---------------------------------------------------------------------------


def test_chat_request_valid():
    req = ChatRequest(incident_id="INC-20240601-001", message="What happened?")
    assert req.incident_id == "INC-20240601-001"
    assert req.message == "What happened?"


def test_chat_request_empty_message_raises():
    with pytest.raises(ValidationError):
        ChatRequest(incident_id="INC-20240601-001", message="")


def test_chat_request_whitespace_only_message_raises():
    with pytest.raises(ValidationError):
        ChatRequest(incident_id="INC-20240601-001", message="   ")


def test_chat_request_missing_incident_id_raises():
    with pytest.raises(ValidationError):
        ChatRequest(message="Hello")


def test_chat_request_missing_message_raises():
    with pytest.raises(ValidationError):
        ChatRequest(incident_id="INC-20240601-001")


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------


def test_chat_message_valid_user():
    msg = ChatMessage(**VALID_MESSAGE)
    assert msg.message_id == "MSG-001"
    assert msg.role == "user"
    assert msg.content == "What caused this incident?"


def test_chat_message_valid_assistant():
    msg = ChatMessage(**{**VALID_MESSAGE, "role": "assistant", "message_id": "MSG-002"})
    assert msg.role == "assistant"


def test_chat_message_invalid_role_raises():
    with pytest.raises(ValidationError):
        ChatMessage(**{**VALID_MESSAGE, "role": "system"})


def test_chat_message_valid_message_id_formats():
    valid_ids = ["MSG-000", "MSG-001", "MSG-099", "MSG-999"]
    for mid in valid_ids:
        msg = ChatMessage(**{**VALID_MESSAGE, "message_id": mid})
        assert msg.message_id == mid


def test_chat_message_invalid_message_id_raises():
    invalid_ids = [
        "MSG-01",     # only 2 digits
        "MSG-0001",   # 4 digits
        "msg-001",    # lowercase
        "001",        # missing prefix
        "MSG001",     # missing hyphen
        "",
    ]
    for mid in invalid_ids:
        with pytest.raises(ValidationError):
            ChatMessage(**{**VALID_MESSAGE, "message_id": mid})


def test_chat_message_missing_required_raises():
    for field in ("message_id", "incident_id", "role", "content", "timestamp"):
        data = {k: v for k, v in VALID_MESSAGE.items() if k != field}
        with pytest.raises(ValidationError):
            ChatMessage(**data)


def test_chat_message_timestamp_stored():
    msg = ChatMessage(**VALID_MESSAGE)
    assert msg.timestamp == NOW


# ---------------------------------------------------------------------------
# ChatHistoryResponse
# ---------------------------------------------------------------------------


def test_chat_history_response_empty():
    resp = ChatHistoryResponse(incident_id="INC-20240601-001", messages=[])
    assert resp.incident_id == "INC-20240601-001"
    assert resp.messages == []


def test_chat_history_response_with_messages():
    msgs = [
        ChatMessage(**{**VALID_MESSAGE, "message_id": "MSG-001", "role": "user"}),
        ChatMessage(
            message_id="MSG-002",
            incident_id="INC-20240601-001",
            role="assistant",
            content="The DB ran out of connections due to a traffic spike.",
            timestamp=NOW,
        ),
    ]
    resp = ChatHistoryResponse(incident_id="INC-20240601-001", messages=msgs)
    assert len(resp.messages) == 2
    assert resp.messages[0].role == "user"
    assert resp.messages[1].role == "assistant"


def test_chat_history_response_missing_incident_id_raises():
    with pytest.raises(ValidationError):
        ChatHistoryResponse(messages=[])


def test_chat_history_response_missing_messages_raises():
    with pytest.raises(ValidationError):
        ChatHistoryResponse(incident_id="INC-20240601-001")

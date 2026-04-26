import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

_MESSAGE_ID_RE = re.compile(r"^MSG-\d{3}$")


class ChatRequest(BaseModel):
    incident_id: str
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty")
        return v


class ChatMessage(BaseModel):
    message_id: str
    incident_id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        if not _MESSAGE_ID_RE.match(v):
            raise ValueError(f"message_id must match MSG-NNN, got: {v}")
        return v


class ChatHistoryResponse(BaseModel):
    incident_id: str
    messages: list[ChatMessage]

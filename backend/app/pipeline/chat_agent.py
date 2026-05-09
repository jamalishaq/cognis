from __future__ import annotations

import structlog
from collections.abc import Generator
from typing import Any

from app.config import settings
from app.services import bedrock

log = structlog.get_logger()

_SYSTEM_TEMPLATE = """\
You are an SRE assistant helping to investigate and resolve an active incident.

Incident context:
  ID: {incident_id}
  Title: {title}
  Summary: {summary}
  Affected service: {affected_service}
  Severity: {severity}
  Failure class: {failure_class}
  Recommended actions: {recommended_actions}
{rag_section}
Answer the user's questions clearly and concisely. Focus on actionable guidance \
based on the incident context and runbook excerpts above."""


def run(
    incident: dict[str, Any],
    history: list[dict[str, Any]],
    user_message: str,
    rag_chunks: list[str],
) -> Generator[str, None, None]:
    rag_section = ""
    if rag_chunks:
        joined = "\n---\n".join(rag_chunks)
        rag_section = f"\nRelevant runbook context:\n{joined}\n"

    system = _SYSTEM_TEMPLATE.format(
        incident_id=incident.get("incident_id", ""),
        title=incident.get("title", ""),
        summary=incident.get("summary", ""),
        affected_service=incident.get("affected_service", ""),
        severity=incident.get("severity", ""),
        failure_class=incident.get("failure_class", ""),
        recommended_actions=", ".join(incident.get("recommended_actions") or []),
        rag_section=rag_section,
    )

    messages: list[dict[str, Any]] = []
    for msg in history:
        messages.append({"role": msg["role"], "content": [{"text": msg["content"]}]})
    messages.append({"role": "user", "content": [{"text": user_message}]})

    return bedrock.stream_text(model_id=settings.chat_model_id, messages=messages, system=system, trace_name="chat")

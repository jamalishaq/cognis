import json
import logging
import re
import time

from app.config import settings
from app.models.alert import NormalisedAlert
from app.models.triage import TriageResult
from app.services import bedrock

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        if inner.strip():
            return inner.strip()
    m = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


_SYSTEM_PROMPT = """\
You are an SRE triage assistant. Given an incident alert, return a JSON object with exactly
three fields:
  - "service": the affected service name (string)
  - "severity": one of "critical", "high", "medium", "low", "unknown"
  - "failure_class": a short snake_case label for the failure category (e.g. "connection_exhaustion",
    "memory_leak", "deployment_regression", "dependency_failure", "unknown")

Respond with only the JSON object — no markdown, no explanation."""


def run(alert: NormalisedAlert) -> TriageResult:
    prompt = (
        f"Alert title: {alert.title}\n"
        f"Description: {alert.description}\n"
        f"Source: {alert.source}\n"
        f"Severity hint: {alert.severity}\n"
        f"Service hint: {alert.service or 'unknown'}"
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = bedrock.invoke_model(
                model_id=settings.triage_model_id,
                messages=messages,
                system=_SYSTEM_PROMPT,
                max_tokens=256,
            )
            data = json.loads(_extract_json(raw))
            return TriageResult(**data)
        except Exception as exc:
            last_exc = exc
            logger.warning("Triage attempt %d/3 failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2**attempt)

    raise last_exc  # type: ignore[misc]

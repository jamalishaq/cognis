import json
import time

import structlog

from app.config import settings
from app.metrics import emit_pipeline_metric
from app.models.alert import NormalisedAlert
from app.models.triage import TriageResult
from app.services import bedrock
from app.utils.json_utils import extract_json

log = structlog.get_logger()


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

    t0 = time.perf_counter()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = bedrock.invoke_model(
                model_id=settings.triage_model_id,
                messages=messages,
                system=_SYSTEM_PROMPT,
                max_tokens=256,
                trace_name="triage",
            )
            data = json.loads(extract_json(raw))
            result = TriageResult(**data)
            duration_ms = round((time.perf_counter() - t0) * 1000)
            log.info("triage_completed", stage="triage", duration_ms=duration_ms,
                     failure_class=result.failure_class, severity=result.severity)
            emit_pipeline_metric(
                "triage_duration_ms", duration_ms, "Milliseconds",
                {"environment": settings.environment, "failure_class": result.failure_class},
            )
            return result
        except Exception as exc:
            last_exc = exc
            log.warning("triage_retry", stage="triage", attempt=attempt + 1, error=str(exc))
            if attempt < 2:
                time.sleep(2 ** attempt)

    log.error("triage_failed", stage="triage", attempts=3, error=str(last_exc))
    raise last_exc

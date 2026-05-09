from __future__ import annotations

import time
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException
from structlog.contextvars import bind_contextvars

from app.config import settings
from app.metrics import emit_pipeline_metric
from app.models.analyse import AnalyseResponse
from app.pipeline import agent, judge, retrieval, triage
from app.services import dynamodb, sqs
from app.registry.normaliser_registry import normalise

log = structlog.get_logger()

router = APIRouter()


def _generate_incident_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        seq = dynamodb.increment_counter(f"incidents-{today}")
    except Exception as exc:
        log.warning("incident_counter_failed", error=str(exc))
        seq = 1
    return f"INC-{today}-{seq:03d}"


@router.post("/analyse", response_model=AnalyseResponse)
def analyse(payload: dict) -> AnalyseResponse:
    t0 = time.perf_counter()
    now = datetime.now(timezone.utc)

    # Normalise — generic fallback handles any payload shape; never raises
    alert = normalise(payload)

    # Generate and bind incident_id before any pipeline stage so all Langfuse
    # traces (triage, embed, rerank, agent, judge) carry the incident_id.
    incident_id = _generate_incident_id()
    bind_contextvars(incident_id=incident_id)

    # Triage — fail fast: nothing downstream runs without a classification
    try:
        triage_result = triage.run(alert)
    except Exception as exc:
        log.error("triage_failed", stage="triage", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "error": "triage_failed",
                "message": "Unable to classify alert after 3 retries",
                "incident_id": None,
                "timestamp": now.isoformat(),
            },
        )

    # RAG retrieval — degrades gracefully on failure (handled inside retrieval.run)
    retrieval_result = retrieval.run(triage_result)

    # Reasoning agent — fail with 503; triage classification included in error so
    # the caller still knows the service and severity
    try:
        brief = agent.run(alert, triage_result, retrieval_result, incident_id)
    except Exception as exc:
        log.error("agent_failed", stage="agent", incident_id=incident_id, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "error": "agent_failed",
                "message": "Unable to generate incident brief after 3 retries",
                "incident_id": incident_id,
                "timestamp": now.isoformat(),
            },
        )

    # Judge — runs after agent; failure never blocks the brief
    eval_result = judge.run_judge(brief, retrieval_result.chunks)

    # Persist to DynamoDB — storage failure must not prevent the brief being returned
    try:
        dynamodb.put_item(
            "Incidents",
            {
                "incident_id": brief.incident_id,
                "title": brief.title,
                "summary": brief.summary,
                "severity": brief.severity,
                "affected_service": brief.affected_service,
                "failure_class": brief.failure_class,
                "recommended_actions": brief.recommended_actions,
                "runbook_references": brief.runbook_references,
                "retrieval_context_available": brief.retrieval_context_available,
                "status": "open",
                "created_at": brief.created_at.isoformat(),
                "source": alert.source,
                "raw_payload": alert.raw_payload,
            },
        )
    except Exception as exc:
        log.error("dynamodb_write_failed", stage="storage", incident_id=incident_id, error=str(exc))

    # Persist eval scores — separate write so judge failure doesn't affect main record
    if eval_result.eval_ran:
        try:
            dynamodb.update_item(
                "Incidents",
                key={"incident_id": brief.incident_id},
                updates={
                    "eval_ran": eval_result.eval_ran,
                    "eval_groundedness": eval_result.groundedness,
                    "eval_completeness": eval_result.completeness,
                    "eval_actionability": eval_result.actionability,
                    "eval_confidence": eval_result.confidence,
                    "eval_flags": eval_result.flags,
                },
            )
        except Exception as exc:
            log.error("dynamodb_eval_write_failed", stage="eval_storage",
                      incident_id=incident_id, error=str(exc))

    # Drop SQS notification — async fire-and-forget; SQS retries + DLQ handle failures
    try:
        sqs.send_message(settings.notification_queue_url, brief.model_dump(mode="json"))
    except Exception as exc:
        log.warning("sqs_notification_failed", stage="notification",
                    incident_id=incident_id, error=str(exc))

    # In local dev the notify Lambda is not running — invoke it directly so
    # notification providers (e.g. SES log mode) are exercised on every /analyse call
    if settings.is_local:
        from app.lambdas import notify as _notify_lambda  # noqa: PLC0415

        _notify_lambda.handler({"Records": [{"body": brief.model_dump_json()}]}, None)

    total_duration_ms = round((time.perf_counter() - t0) * 1000)
    log.info("brief_returned", total_duration_ms=total_duration_ms)
    dims = {"environment": settings.environment, "failure_class": brief.failure_class}
    emit_pipeline_metric("pipeline_duration_ms", total_duration_ms, "Milliseconds", dims)
    emit_pipeline_metric("incidents_processed", 1, "Count", dims)

    return AnalyseResponse(
        incident_id=brief.incident_id,
        status="received",
        timestamp=now,
    )

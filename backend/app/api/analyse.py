from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.analyse import AnalyseResponse
from app.pipeline import agent, judge, retrieval, triage
from app.services import dynamodb, sqs
from app.utils.normaliser import normalise

logger = logging.getLogger(__name__)

router = APIRouter()


def _generate_incident_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        seq = dynamodb.increment_counter(f"incidents-{today}")
    except Exception as exc:
        logger.warning("Could not increment incident counter, defaulting to 1: %s", exc)
        seq = 1
    return f"INC-{today}-{seq:03d}"


@router.post("/analyse", response_model=AnalyseResponse)
def analyse(payload: dict) -> AnalyseResponse:
    now = datetime.now(timezone.utc)

    # Normalise — generic fallback handles any payload shape; never raises
    alert = normalise(payload)

    # Triage — fail fast: nothing downstream runs without a classification
    try:
        triage_result = triage.run(alert)
    except Exception as exc:
        logger.error("Triage failed: %s", exc, extra={"stage": "triage"})
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

    # Incident ID must be generated before calling the agent so it can embed the ID in the brief
    incident_id = _generate_incident_id()

    # Reasoning agent — fail with 503; triage classification included in error so
    # the caller still knows the service and severity
    try:
        brief = agent.run(alert, triage_result, retrieval_result, incident_id)
    except Exception as exc:
        logger.error(
            "Agent failed for %s: %s",
            incident_id,
            exc,
            extra={"stage": "agent", "incident_id": incident_id},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "agent_failed",
                "message": "Unable to generate incident brief after 3 retries",
                "incident_id": incident_id,
                "timestamp": now.isoformat(),
            },
        )

    # Judge — runs async after agent; failure never blocks the brief
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
        logger.error(
            "DynamoDB write failed for %s: %s",
            incident_id,
            exc,
            extra={"stage": "storage", "incident_id": incident_id},
        )

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
            logger.error(
                "DynamoDB eval write failed for %s: %s",
                incident_id,
                exc,
                extra={"stage": "eval_storage", "incident_id": incident_id},
            )

    # Drop SQS notification — async fire-and-forget; SQS retries + DLQ handle failures
    try:
        sqs.send_message(settings.notification_queue_url, brief.model_dump(mode="json"))
    except Exception as exc:
        logger.warning(
            "SQS notification failed for %s: %s",
            incident_id,
            exc,
            extra={"stage": "notification", "incident_id": incident_id},
        )

    # In local dev the notify Lambda is not running — invoke it directly so
    # notification providers (e.g. SES log mode) are exercised on every /analyse call
    if settings.is_local:
        print(f"settings is local: {settings.is_local}")
        from app.lambdas import notify as _notify_lambda  # noqa: PLC0415

        _notify_lambda.handler({"Records": [{"body": brief.model_dump_json()}]}, None)

    return AnalyseResponse(
        incident_id=brief.incident_id,
        status="received",
        timestamp=now,
    )

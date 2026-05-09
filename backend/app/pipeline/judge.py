from __future__ import annotations

import json

import structlog

from app.config import settings
from app.metrics import emit_judge_metric
from app.models.eval import EvalResult
from app.models.incident import IncidentBrief
from app.services import bedrock

log = structlog.get_logger()

_SYSTEM_PROMPT = """\
You are a quality evaluator for AI-generated incident briefs. Score the brief against
the retrieved runbook context that was available to the agent.

Respond with ONLY a JSON object — no markdown, no explanation:

{
  "groundedness": <integer 1-5>,
  "completeness": <integer 1-5>,
  "actionability": <integer 1-5>,
  "confidence": "<low|medium|high>",
  "flags": ["<concern>", ...]
}

Scoring rubric:
- groundedness (1-5): Does the hypothesis / root-cause align with the retrieved context?
  1 = contradicts context, 5 = fully supported by context.
- completeness (1-5): Are title, summary, severity, affected_service, failure_class,
  recommended_actions, and runbook_references all present and substantive?
  1 = major fields missing or empty, 5 = all fields populated with meaningful content.
- actionability (1-5): Are recommended_actions specific and executable by an on-call engineer?
  1 = vague or absent, 5 = concrete step-by-step actions.
- confidence (low/medium/high): Overall certainty of the analysis given available context.
- flags: List any concerns, e.g. "hallucination_risk", "vague_actions", "missing_context",
  "contradicts_runbook", "no_recommended_actions". Empty list if none."""


def run_judge(brief: IncidentBrief, chunks: list[str]) -> EvalResult:
    try:
        context_text = "\n---\n".join(chunks) if chunks else "(no retrieved context)"

        prompt = (
            f"Incident brief to evaluate:\n"
            f"  Title: {brief.title}\n"
            f"  Summary: {brief.summary}\n"
            f"  Severity: {brief.severity}\n"
            f"  Affected service: {brief.affected_service}\n"
            f"  Failure class: {brief.failure_class}\n"
            f"  Recommended actions: {json.dumps(brief.recommended_actions)}\n"
            f"  Runbook references: {json.dumps(brief.runbook_references)}\n"
            f"  Retrieval context available: {brief.retrieval_context_available}\n\n"
            f"Retrieved runbook context used by the agent:\n{context_text}"
        )

        messages = [{"role": "user", "content": [{"text": prompt}]}]

        raw = bedrock.invoke_model(
            model_id=settings.judge_model_id,
            messages=messages,
            system=_SYSTEM_PROMPT,
            max_tokens=512,
            trace_name="judge",
        )

        data = json.loads(raw)
        result = EvalResult(
            eval_ran=True,
            groundedness=int(data["groundedness"]),
            completeness=int(data["completeness"]),
            actionability=int(data["actionability"]),
            confidence=data["confidence"],
            flags=data.get("flags", []),
        )
        log.info("judge_completed", stage="judge",
                 groundedness=result.groundedness,
                 completeness=result.completeness,
                 actionability=result.actionability,
                 confidence=result.confidence)
        dims = {"environment": settings.environment}
        emit_judge_metric("judge_groundedness", result.groundedness, "None", dims)
        emit_judge_metric("judge_completeness", result.completeness, "None", dims)
        emit_judge_metric("judge_actionability", result.actionability, "None", dims)
        if result.confidence == "low":
            emit_judge_metric("judge_low_confidence", 1, "Count", dims)
        if result.flags:
            emit_judge_metric("judge_flagged", 1, "Count", dims)
        return result

    except Exception as exc:
        log.warning("judge_failed", stage="judge", error=str(exc), eval_ran=False)
        emit_judge_metric("judge_eval_failed", 1, "Count", {"environment": settings.environment})
        return EvalResult(eval_ran=False)

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models.eval import EvalResult
from app.models.incident import IncidentBrief
from app.pipeline.judge import run_judge


def _make_brief(**kwargs) -> IncidentBrief:
    defaults = dict(
        incident_id="INC-20260424-001",
        title="DB connection pool exhausted on payments-service",
        summary="Active connections reached pool max of 100 after worker thread count increase in v2.14.3.",
        severity="critical",
        affected_service="payments-service",
        failure_class="connection_exhaustion",
        recommended_actions=[
            "Restart payments-service to release stuck connections",
            "Roll back v2.14.3 to v2.14.2",
            "Increase connection pool max to 200 in config",
        ],
        runbook_references=["runbooks/database/connection-pool.md"],
        retrieval_context_available=True,
        created_at=datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return IncidentBrief(**defaults)


def _judge_response(
    groundedness: int = 5,
    completeness: int = 5,
    actionability: int = 4,
    confidence: str = "high",
    flags: list | None = None,
) -> str:
    return json.dumps(
        {
            "groundedness": groundedness,
            "completeness": completeness,
            "actionability": actionability,
            "confidence": confidence,
            "flags": flags or [],
        }
    )


_SAMPLE_CHUNKS = [
    "Connection pool exhaustion occurs when all DB connections are in use. "
    "Remediation: increase pool size or reduce connection hold time.",
    "After deploying thread count changes, monitor active_db_connections metric closely.",
]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_returns_eval_result_with_scores(mock_invoke):
    mock_invoke.return_value = _judge_response(
        groundedness=5,
        completeness=5,
        actionability=4,
        confidence="high",
        flags=[],
    )

    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)

    assert isinstance(result, EvalResult)
    assert result.eval_ran is True
    assert result.groundedness == 5
    assert result.completeness == 5
    assert result.actionability == 4
    assert result.confidence == "high"
    assert result.flags == []


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_populates_flags(mock_invoke):
    mock_invoke.return_value = _judge_response(
        groundedness=2,
        completeness=3,
        actionability=2,
        confidence="low",
        flags=["vague_actions", "missing_context"],
    )

    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)

    assert result.eval_ran is True
    assert "vague_actions" in result.flags
    assert "missing_context" in result.flags


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_uses_haiku_model(mock_invoke):
    mock_invoke.return_value = _judge_response()

    run_judge(_make_brief(), _SAMPLE_CHUNKS)

    model_id = mock_invoke.call_args.kwargs.get("model_id") or mock_invoke.call_args.args[0]
    assert "haiku" in model_id


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_includes_brief_fields_in_prompt(mock_invoke):
    mock_invoke.return_value = _judge_response()
    brief = _make_brief()

    run_judge(brief, _SAMPLE_CHUNKS)

    messages = mock_invoke.call_args.kwargs.get("messages") or mock_invoke.call_args.args[1]
    user_text = messages[0]["content"][0]["text"]
    assert brief.title in user_text
    assert brief.affected_service in user_text
    assert brief.failure_class in user_text


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_includes_chunks_in_prompt(mock_invoke):
    mock_invoke.return_value = _judge_response()

    run_judge(_make_brief(), _SAMPLE_CHUNKS)

    messages = mock_invoke.call_args.kwargs.get("messages") or mock_invoke.call_args.args[1]
    user_text = messages[0]["content"][0]["text"]
    assert _SAMPLE_CHUNKS[0][:40] in user_text


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_handles_empty_chunks(mock_invoke):
    mock_invoke.return_value = _judge_response()

    result = run_judge(_make_brief(), [])

    assert result.eval_ran is True
    messages = mock_invoke.call_args.kwargs.get("messages") or mock_invoke.call_args.args[1]
    user_text = messages[0]["content"][0]["text"]
    assert "no retrieved context" in user_text


# ---------------------------------------------------------------------------
# Bedrock failure — must return EvalResult(eval_ran=False), never raise
# ---------------------------------------------------------------------------


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_returns_eval_ran_false_on_bedrock_error(mock_invoke):
    mock_invoke.side_effect = RuntimeError("Bedrock throttled")

    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)

    assert isinstance(result, EvalResult)
    assert result.eval_ran is False
    assert result.groundedness is None
    assert result.completeness is None
    assert result.actionability is None
    assert result.confidence is None


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_does_not_raise_on_bedrock_error(mock_invoke):
    mock_invoke.side_effect = Exception("connection timeout")

    # Must not raise under any circumstances
    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)
    assert result.eval_ran is False


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_returns_eval_ran_false_on_json_parse_error(mock_invoke):
    mock_invoke.return_value = "this is not valid json {{{"

    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)

    assert result.eval_ran is False


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_returns_eval_ran_false_on_missing_fields(mock_invoke):
    # Response missing required score fields
    mock_invoke.return_value = json.dumps({"confidence": "high"})

    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)

    assert result.eval_ran is False


# ---------------------------------------------------------------------------
# Low groundedness when hypothesis contradicts retrieved chunks
# ---------------------------------------------------------------------------


@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_low_groundedness_when_hypothesis_contradicts_context(mock_invoke):
    """Judge should score groundedness=1 when the brief contradicts the retrieved context."""
    mock_invoke.return_value = _judge_response(
        groundedness=1,
        completeness=4,
        actionability=3,
        confidence="low",
        flags=["contradicts_runbook", "hallucination_risk"],
    )

    brief = _make_brief(
        failure_class="network_partition",
        summary="The service is experiencing a network partition between availability zones.",
    )
    contradicting_chunks = [
        "Connection pool exhaustion observed. DB connections at 98/100.",
        "No network issues detected. All AZ-to-AZ routes healthy.",
    ]

    result = run_judge(brief, contradicting_chunks)

    assert result.eval_ran is True
    assert result.groundedness == 1
    assert result.confidence == "low"
    assert "contradicts_runbook" in result.flags or "hallucination_risk" in result.flags


# ---------------------------------------------------------------------------
# Confidence variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("confidence", ["low", "medium", "high"])
@patch("app.pipeline.judge.bedrock.invoke_model")
def test_run_judge_accepts_all_confidence_values(mock_invoke, confidence):
    mock_invoke.return_value = _judge_response(confidence=confidence)

    result = run_judge(_make_brief(), _SAMPLE_CHUNKS)

    assert result.confidence == confidence

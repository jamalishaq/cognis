import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models.alert import NormalisedAlert
from app.models.triage import TriageResult
from app.pipeline import triage


def _make_alert(**kwargs) -> NormalisedAlert:
    defaults = dict(
        source="grafana",
        title="High error rate on payments-api",
        description="5xx rate exceeded 10% for 5 minutes",
        severity="high",
        service="payments-api",
        raw_payload={},
        received_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return NormalisedAlert(**defaults)


def _bedrock_response(service: str, severity: str, failure_class: str) -> str:
    return json.dumps(
        {"service": service, "severity": severity, "failure_class": failure_class}
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_returns_triage_result(mock_invoke, mock_sleep):
    mock_invoke.return_value = _bedrock_response("payments-api", "high", "connection_exhaustion")

    result = triage.run(_make_alert())

    assert isinstance(result, TriageResult)
    assert result.service == "payments-api"
    assert result.severity == "high"
    assert result.failure_class == "connection_exhaustion"
    mock_sleep.assert_not_called()


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_passes_alert_fields_to_bedrock(mock_invoke, mock_sleep):
    mock_invoke.return_value = _bedrock_response("auth-service", "critical", "memory_leak")
    alert = _make_alert(title="OOM on auth", description="heap exhausted", service="auth-service")

    triage.run(alert)

    _, kwargs = mock_invoke.call_args
    # The prompt should include the alert fields
    messages = kwargs.get("messages") or mock_invoke.call_args.args[1]
    user_text = messages[0]["content"][0]["text"]
    assert "OOM on auth" in user_text
    assert "heap exhausted" in user_text
    assert "auth-service" in user_text


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_uses_haiku_model(mock_invoke, mock_sleep):
    mock_invoke.return_value = _bedrock_response("svc", "low", "unknown")

    triage.run(_make_alert())

    model_id = mock_invoke.call_args.kwargs.get("model_id") or mock_invoke.call_args.args[0]
    assert "haiku" in model_id


# ---------------------------------------------------------------------------
# Severity / failure_class variants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low", "unknown"])
@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_accepts_all_severity_values(mock_invoke, mock_sleep, severity):
    mock_invoke.return_value = _bedrock_response("svc", severity, "timeout")

    result = triage.run(_make_alert())

    assert result.severity == severity


# ---------------------------------------------------------------------------
# Retry scenarios
# ---------------------------------------------------------------------------

@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_retries_on_bedrock_failure_then_succeeds(mock_invoke, mock_sleep):
    mock_invoke.side_effect = [
        RuntimeError("throttled"),
        RuntimeError("throttled"),
        _bedrock_response("db-service", "critical", "connection_exhaustion"),
    ]

    result = triage.run(_make_alert())

    assert result.service == "db-service"
    assert mock_invoke.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2**0 after attempt 0
    mock_sleep.assert_any_call(2)  # 2**1 after attempt 1


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_retries_on_json_parse_failure_then_succeeds(mock_invoke, mock_sleep):
    mock_invoke.side_effect = [
        "not valid json {{",
        _bedrock_response("api-gw", "medium", "timeout"),
    ]

    result = triage.run(_make_alert())

    assert result.service == "api-gw"
    assert mock_invoke.call_count == 2
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_once_with(1)  # 2**0


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_raises_after_three_failures(mock_invoke, mock_sleep):
    exc = RuntimeError("service unavailable")
    mock_invoke.side_effect = exc

    with pytest.raises(RuntimeError, match="service unavailable"):
        triage.run(_make_alert())

    assert mock_invoke.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_no_sleep_after_last_attempt(mock_invoke, mock_sleep):
    mock_invoke.side_effect = RuntimeError("err")

    with pytest.raises(RuntimeError):
        triage.run(_make_alert())

    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_args == [1, 2]  # after attempt 0 and 1, not after attempt 2


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_raises_last_exception_on_all_failures(mock_invoke, mock_sleep):
    mock_invoke.side_effect = [
        RuntimeError("first"),
        RuntimeError("second"),
        RuntimeError("third"),
    ]

    with pytest.raises(RuntimeError, match="third"):
        triage.run(_make_alert())


# ---------------------------------------------------------------------------
# Malformed model output
# ---------------------------------------------------------------------------

@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_raises_on_all_invalid_json(mock_invoke, mock_sleep):
    mock_invoke.return_value = "not json at all"

    with pytest.raises(Exception):
        triage.run(_make_alert())

    assert mock_invoke.call_count == 3


@patch("time.sleep")
@patch("app.pipeline.triage.bedrock.invoke_model")
def test_run_raises_on_missing_required_field(mock_invoke, mock_sleep):
    mock_invoke.return_value = json.dumps({"service": "svc", "severity": "high"})  # missing failure_class

    with pytest.raises(Exception):
        triage.run(_make_alert())

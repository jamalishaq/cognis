import json
from datetime import datetime, timezone
from unittest.mock import call, patch

import pytest

from app.models.alert import NormalisedAlert
from app.models.incident import IncidentBrief
from app.models.triage import TriageResult
from app.pipeline import agent
from app.pipeline.retrieval import RetrievalResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_alert(**kwargs) -> NormalisedAlert:
    defaults = dict(
        source="grafana",
        title="High error rate on payments-service",
        description="5xx rate exceeded 18% for 5 minutes",
        severity="critical",
        service="payments-service",
        raw_payload={},
        received_at=datetime(2026, 4, 23, 14, 35, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return NormalisedAlert(**defaults)


def _make_triage(**kwargs) -> TriageResult:
    defaults = dict(service="payments-service", severity="critical", failure_class="connection_exhaustion")
    defaults.update(kwargs)
    return TriageResult(**defaults)


def _make_retrieval(**kwargs) -> RetrievalResult:
    defaults = dict(chunks=["Runbook: increase APP_DB_POOL_MAX and redeploy"], retrieval_context_available=True)
    defaults.update(kwargs)
    return RetrievalResult(**defaults)


def _brief_json(**kwargs) -> str:
    defaults = dict(
        title="payments-service connection pool exhausted",
        summary="The payments-service is returning 18% 5xx errors due to DB connection pool exhaustion triggered by the v2.14.3 deploy.",
        severity="critical",
        affected_service="payments-service",
        failure_class="connection_exhaustion",
        recommended_actions=["Increase APP_DB_POOL_MAX and redeploy"],
        runbook_references=["runbooks/payments-service.md"],
    )
    defaults.update(kwargs)
    return json.dumps(defaults)


def _assistant_text(text: str) -> tuple[dict, str]:
    """Simulate a Bedrock response with no tool calls — just a final text reply."""
    return {"role": "assistant", "content": [{"text": text}]}, "end_turn"


def _assistant_tool_call(tool_name: str, tool_input: dict, tool_use_id: str = "tu-001") -> tuple[dict, str]:
    """Simulate a Bedrock response with a single tool call."""
    return (
        {
            "role": "assistant",
            "content": [{"toolUse": {"toolUseId": tool_use_id, "name": tool_name, "input": tool_input}}],
        },
        "tool_use",
    )


def _assistant_multi_tool(calls: list[tuple[str, dict, str]]) -> tuple[dict, str]:
    """Simulate a Bedrock response with multiple tool calls."""
    content = [
        {"toolUse": {"toolUseId": tid, "name": name, "input": inp}}
        for name, inp, tid in calls
    ]
    return {"role": "assistant", "content": content}, "tool_use"


# ---------------------------------------------------------------------------
# Zero tool calls — model returns brief directly
# ---------------------------------------------------------------------------

@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_zero_tool_calls_returns_brief(mock_converse, mock_sleep):
    mock_converse.return_value = _assistant_text(_brief_json())

    result = agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    assert isinstance(result, IncidentBrief)
    assert result.incident_id == "INC-20260423-001"
    assert result.title == "payments-service connection pool exhausted"
    assert result.severity == "critical"
    assert result.failure_class == "connection_exhaustion"
    assert result.retrieval_context_available is True
    mock_converse.assert_called_once()
    mock_sleep.assert_not_called()


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_zero_tool_calls_uses_sonnet_model(mock_converse, mock_sleep):
    mock_converse.return_value = _assistant_text(_brief_json())

    agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    model_id = mock_converse.call_args.kwargs.get("model_id") or mock_converse.call_args.args[0]
    assert "sonnet" in model_id.lower()


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_propagates_retrieval_context_flag(mock_converse, mock_sleep):
    mock_converse.return_value = _assistant_text(_brief_json())
    retrieval = _make_retrieval(chunks=[], retrieval_context_available=False)

    result = agent.run(_make_alert(), _make_triage(), retrieval, "INC-20260423-002")

    assert result.retrieval_context_available is False


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_includes_alert_fields_in_first_message(mock_converse, mock_sleep):
    mock_converse.return_value = _assistant_text(_brief_json())

    agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    messages = mock_converse.call_args.kwargs.get("messages") or mock_converse.call_args.args[1]
    user_text = messages[0]["content"][0]["text"]
    assert "payments-service" in user_text
    assert "connection_exhaustion" in user_text
    assert "critical" in user_text


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_includes_runbook_context_when_available(mock_converse, mock_sleep):
    mock_converse.return_value = _assistant_text(_brief_json())
    retrieval = _make_retrieval(chunks=["Runbook: increase APP_DB_POOL_MAX"], retrieval_context_available=True)

    agent.run(_make_alert(), _make_triage(), retrieval, "INC-20260423-001")

    messages = mock_converse.call_args.kwargs.get("messages") or mock_converse.call_args.args[1]
    user_text = messages[0]["content"][0]["text"]
    assert "APP_DB_POOL_MAX" in user_text


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_passes_tool_config_to_bedrock(mock_converse, mock_sleep):
    mock_converse.return_value = _assistant_text(_brief_json())

    agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    tool_config = mock_converse.call_args.kwargs.get("tool_config") or mock_converse.call_args.args[3]
    tool_names = [t["toolSpec"]["name"] for t in tool_config["tools"]]
    assert "get_metrics" in tool_names
    assert "get_deployment_history" in tool_names
    assert "search_incident_history" in tool_names
    assert "get_service_dependencies" in tool_names


# ---------------------------------------------------------------------------
# Single tool call
# ---------------------------------------------------------------------------

@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_single_tool_call_executes_and_continues(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        _assistant_tool_call("get_metrics", {"service": "payments-service"}, "tu-001"),
        _assistant_text(_brief_json()),
    ]

    result = agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    assert isinstance(result, IncidentBrief)
    assert mock_converse.call_count == 2
    mock_sleep.assert_not_called()


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_single_tool_call_passes_result_back(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        _assistant_tool_call("get_metrics", {"service": "payments-service"}, "tu-42"),
        _assistant_text(_brief_json()),
    ]

    agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    second_call_messages = (
        mock_converse.call_args_list[1].kwargs.get("messages")
        or mock_converse.call_args_list[1].args[1]
    )
    # messages[0]=user, messages[1]=assistant(tool_use), messages[2]=user(tool_result)
    tool_result_msg = second_call_messages[2]
    assert tool_result_msg["role"] == "user"
    tool_result_block = tool_result_msg["content"][0]["toolResult"]
    assert tool_result_block["toolUseId"] == "tu-42"
    # result content should contain metrics JSON
    result_text = tool_result_block["content"][0]["text"]
    metrics = json.loads(result_text)
    assert "error_rate_pct" in metrics


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_get_deployment_history_tool_call(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        _assistant_tool_call("get_deployment_history", {"service": "payments-service"}, "tu-10"),
        _assistant_text(_brief_json()),
    ]

    agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    second_call_messages = (
        mock_converse.call_args_list[1].kwargs.get("messages")
        or mock_converse.call_args_list[1].args[1]
    )
    result_text = second_call_messages[2]["content"][0]["toolResult"]["content"][0]["text"]
    deployments = json.loads(result_text)
    assert isinstance(deployments, list)
    assert deployments[0]["version"] == "v2.14.3"


# ---------------------------------------------------------------------------
# Multi-tool call
# ---------------------------------------------------------------------------

@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_multi_tool_call_executes_all_tools(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        _assistant_multi_tool([
            ("get_metrics", {"service": "payments-service"}, "tu-01"),
            ("get_deployment_history", {"service": "payments-service"}, "tu-02"),
        ]),
        _assistant_tool_call("search_incident_history", {"service": "payments-service"}, "tu-03"),
        _assistant_text(_brief_json()),
    ]

    with patch("app.pipeline.agent.dynamodb.scan", return_value=[]):
        result = agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    assert isinstance(result, IncidentBrief)
    assert mock_converse.call_count == 3
    mock_sleep.assert_not_called()


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_multi_tool_returns_both_results(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        _assistant_multi_tool([
            ("get_metrics", {"service": "payments-service"}, "tu-A"),
            ("get_deployment_history", {"service": "payments-service"}, "tu-B"),
        ]),
        _assistant_text(_brief_json()),
    ]

    agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    second_call_messages = (
        mock_converse.call_args_list[1].kwargs.get("messages")
        or mock_converse.call_args_list[1].args[1]
    )
    tool_result_msg = second_call_messages[2]
    assert len(tool_result_msg["content"]) == 2
    ids = {blk["toolResult"]["toolUseId"] for blk in tool_result_msg["content"]}
    assert ids == {"tu-A", "tu-B"}


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------

@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_retries_bedrock_on_failure_then_succeeds(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        RuntimeError("throttled"),
        RuntimeError("throttled"),
        _assistant_text(_brief_json()),
    ]

    result = agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    assert isinstance(result, IncidentBrief)
    assert mock_converse.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)   # 2**0 after attempt 0
    mock_sleep.assert_any_call(2)   # 2**1 after attempt 1


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_raises_after_three_bedrock_failures(mock_converse, mock_sleep):
    mock_converse.side_effect = RuntimeError("service unavailable")

    with pytest.raises(RuntimeError, match="service unavailable"):
        agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    assert mock_converse.call_count == 3
    assert mock_sleep.call_count == 2


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_raises_last_exception_on_all_failures(mock_converse, mock_sleep):
    mock_converse.side_effect = [
        RuntimeError("first"),
        RuntimeError("second"),
        RuntimeError("third"),
    ]

    with pytest.raises(RuntimeError, match="third"):
        agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_no_sleep_after_last_attempt(mock_converse, mock_sleep):
    mock_converse.side_effect = RuntimeError("err")

    with pytest.raises(RuntimeError):
        agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_args == [1, 2]


@patch("app.pipeline.agent.time.sleep")
@patch("app.pipeline.agent.bedrock.converse_with_tools")
def test_run_retries_reset_per_bedrock_call(mock_converse, mock_sleep):
    """Each call in the agent loop gets its own 3-attempt budget."""
    mock_converse.side_effect = [
        # First loop iteration: fail twice, then tool call
        RuntimeError("fail"),
        RuntimeError("fail"),
        _assistant_tool_call("get_metrics", {"service": "payments-service"}, "tu-001"),
        # Second loop iteration: succeed immediately
        _assistant_text(_brief_json()),
    ]

    result = agent.run(_make_alert(), _make_triage(), _make_retrieval(), "INC-20260423-001")

    assert isinstance(result, IncidentBrief)
    assert mock_converse.call_count == 4
    assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# Mock tool: get_metrics
# ---------------------------------------------------------------------------

def test_get_metrics_known_service_returns_consistent_data():
    metrics = agent._get_metrics("payments-service")
    assert metrics["error_rate_pct"] > 10
    assert metrics["active_db_connections"] >= metrics["db_connection_pool_max"] * 0.9
    assert "note" in metrics


def test_get_metrics_auth_service_shows_memory_pressure():
    metrics = agent._get_metrics("auth-service")
    assert metrics["heap_used_mb"] >= metrics["heap_max_mb"] * 0.8
    assert metrics["memory_utilisation_pct"] > 80


def test_get_metrics_unknown_service_returns_defaults():
    metrics = agent._get_metrics("some-unknown-service")
    assert "error_rate_pct" in metrics
    assert "cpu_utilisation_pct" in metrics
    assert "note" in metrics


def test_get_metrics_all_known_services_have_note():
    services = ["payments-service", "auth-service", "api-gateway", "checkout-service", "inventory-service"]
    for svc in services:
        metrics = agent._get_metrics(svc)
        assert "note" in metrics, f"missing note for {svc}"


# ---------------------------------------------------------------------------
# Mock tool: get_deployment_history
# ---------------------------------------------------------------------------

def test_get_deployment_history_payments_service():
    history = agent._get_deployment_history("payments-service")
    assert isinstance(history, list)
    assert len(history) >= 1
    latest = history[0]
    assert latest["version"] == "v2.14.3"
    assert "2026-04-23" in latest["deployed_at"]
    assert "change_summary" in latest


def test_get_deployment_history_auth_service():
    history = agent._get_deployment_history("auth-service")
    assert len(history) >= 1
    assert history[0]["version"] == "v3.5.0"


def test_get_deployment_history_unknown_service_returns_default():
    history = agent._get_deployment_history("unknown-service")
    assert isinstance(history, list)
    assert len(history) >= 1
    assert "version" in history[0]
    assert "change_summary" in history[0]


def test_get_deployment_history_all_entries_have_required_fields():
    for svc in ["payments-service", "auth-service", "api-gateway"]:
        for entry in agent._get_deployment_history(svc):
            assert "version" in entry
            assert "deployed_at" in entry
            assert "status" in entry
            assert "change_summary" in entry


# ---------------------------------------------------------------------------
# Real tool: search_incident_history
# ---------------------------------------------------------------------------

@patch("app.pipeline.agent.dynamodb.scan")
def test_search_incident_history_queries_incidents_table(mock_scan):
    mock_scan.return_value = []

    result = agent._search_incident_history("payments-service")

    assert result == []
    mock_scan.assert_called_once()
    call_args = mock_scan.call_args
    assert call_args.args[0] == "Incidents" or call_args.kwargs.get("table_name") == "Incidents"


@patch("app.pipeline.agent.dynamodb.scan")
def test_search_incident_history_maps_fields(mock_scan):
    mock_scan.return_value = [
        {
            "incident_id": "INC-20260423-001",
            "title": "DB pool exhaustion",
            "severity": "critical",
            "failure_class": "connection_exhaustion",
            "status": "resolved",
            "affected_service": "payments-service",
            "created_at": "2026-04-23T14:35:00+00:00",
        }
    ]

    result = agent._search_incident_history("payments-service")

    assert len(result) == 1
    assert result[0]["incident_id"] == "INC-20260423-001"
    assert result[0]["title"] == "DB pool exhaustion"
    assert result[0]["severity"] == "critical"
    assert result[0]["failure_class"] == "connection_exhaustion"
    assert result[0]["status"] == "resolved"


@patch("app.pipeline.agent.dynamodb.scan")
def test_search_incident_history_respects_limit(mock_scan):
    mock_scan.return_value = [
        {"incident_id": f"INC-2026042{i}-001", "title": f"inc{i}", "severity": "high",
         "failure_class": "timeout", "status": "resolved", "affected_service": "svc",
         "created_at": "2026-04-23"}
        for i in range(10)
    ]

    result = agent._search_incident_history("svc", limit=3)

    assert len(result) == 3


@patch("app.pipeline.agent.dynamodb.scan")
def test_search_incident_history_default_limit_five(mock_scan):
    mock_scan.return_value = [
        {"incident_id": f"INC-2026042{i}-001", "title": f"inc{i}", "severity": "high",
         "failure_class": "timeout", "status": "resolved", "affected_service": "svc",
         "created_at": "2026-04-23"}
        for i in range(8)
    ]

    result = agent._search_incident_history("svc")

    assert len(result) == 5


# ---------------------------------------------------------------------------
# Real tool: get_service_dependencies
# ---------------------------------------------------------------------------

@patch("app.pipeline.agent.dynamodb.scan")
def test_get_service_dependencies_queries_corpus_chunks(mock_scan):
    mock_scan.return_value = []

    result = agent._get_service_dependencies("payments-service")

    assert result == []
    call_args = mock_scan.call_args
    assert call_args.args[0] == "CorpusChunks" or call_args.kwargs.get("table_name") == "CorpusChunks"


@patch("app.pipeline.agent.dynamodb.scan")
def test_get_service_dependencies_reads_content_field(mock_scan):
    mock_scan.return_value = [
        {
            "chunk_id": "chunk-001",
            "source_file": "runbooks/payments-service.md",
            "content": "Runbook text for payments-service connection pool",
        }
    ]

    result = agent._get_service_dependencies("payments-service")

    assert len(result) == 1
    assert result[0]["chunk_id"] == "chunk-001"
    assert "payments-service" in result[0]["content"]


@patch("app.pipeline.agent.dynamodb.scan")
def test_get_service_dependencies_reads_text_field_as_fallback(mock_scan):
    mock_scan.return_value = [
        {
            "chunk_id": "chunk-002",
            "source_file": "runbooks/payments-service.md",
            "text": "Alternate field name text",
        }
    ]

    result = agent._get_service_dependencies("payments-service")

    assert len(result) == 1
    assert result[0]["content"] == "Alternate field name text"


@patch("app.pipeline.agent.dynamodb.scan")
def test_get_service_dependencies_skips_items_with_no_content(mock_scan):
    mock_scan.return_value = [
        {"chunk_id": "chunk-001", "source_file": "runbooks/payments-service.md"},
        {"chunk_id": "chunk-002", "source_file": "runbooks/payments-service.md", "content": "has content"},
    ]

    result = agent._get_service_dependencies("payments-service")

    assert len(result) == 1
    assert result[0]["chunk_id"] == "chunk-002"


@patch("app.pipeline.agent.dynamodb.scan")
def test_get_service_dependencies_truncates_content_at_500_chars(mock_scan):
    long_text = "x" * 1000
    mock_scan.return_value = [
        {"chunk_id": "chunk-001", "source_file": "runbooks/payments-service.md", "content": long_text}
    ]

    result = agent._get_service_dependencies("payments-service")

    assert len(result[0]["content"]) == 500


# ---------------------------------------------------------------------------
# Tool dispatch — unknown tool
# ---------------------------------------------------------------------------

def test_execute_tool_unknown_name_returns_error_json():
    result = agent._execute_tool("nonexistent_tool", {"service": "svc"})
    data = json.loads(result)
    assert "error" in data
    assert "nonexistent_tool" in data["error"]


def test_execute_tool_get_metrics_returns_json_string():
    result = agent._execute_tool("get_metrics", {"service": "payments-service"})
    data = json.loads(result)
    assert "error_rate_pct" in data

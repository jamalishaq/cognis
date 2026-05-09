from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from boto3.dynamodb.conditions import Attr

from app.config import settings
from app.metrics import emit_pipeline_metric
from app.models.alert import NormalisedAlert
from app.models.incident import IncidentBrief
from app.models.triage import TriageResult
from app.pipeline.retrieval import RetrievalResult
from app.services import bedrock, dynamodb
from app.utils.json_utils import extract_json

log = structlog.get_logger()

_SYSTEM_PROMPT = """\
You are an SRE incident response agent. Use the available tools to gather context \
about the incident, then produce a final structured incident brief.

Call tools as needed to understand the failure. When you have enough context, \
respond with ONLY a JSON object — no markdown, no explanation:

{
  "title": "<concise incident title>",
  "summary": "<2-4 sentence description of the incident, root cause, and impact>",
  "severity": "<critical|high|medium|low|unknown>",
  "affected_service": "<service name>",
  "failure_class": "<snake_case failure category>",
  "recommended_actions": ["<concrete remediation step>", ...],
  "runbook_references": ["<runbook path or document title>", ...]
}"""

_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "get_metrics",
                "description": (
                    "Get current operational metrics for a service, including error rates, "
                    "latency percentiles, and resource utilisation."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "service": {
                                "type": "string",
                                "description": "The name of the service to retrieve metrics for.",
                            }
                        },
                        "required": ["service"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_deployment_history",
                "description": (
                    "Get recent deployment history for a service, including deploy times, "
                    "versions, and change summaries."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "service": {
                                "type": "string",
                                "description": "The name of the service to retrieve deployment history for.",
                            }
                        },
                        "required": ["service"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "search_incident_history",
                "description": (
                    "Search previous incidents for a given service to identify recurring failure patterns."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "service": {
                                "type": "string",
                                "description": "The service name to search incident history for.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of past incidents to return. Defaults to 5.",
                                "default": 5,
                            },
                        },
                        "required": ["service"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_service_dependencies",
                "description": (
                    "Look up the service catalogue for a given service, including runbook context "
                    "and known upstream/downstream dependencies."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "service": {
                                "type": "string",
                                "description": "The service name to look up dependencies for.",
                            }
                        },
                        "required": ["service"],
                    }
                },
            }
        },
    ]
}

# Canned mock data keyed by service — tells a consistent story per failure class.
_METRICS: dict[str, dict[str, Any]] = {
    "payments-service": {
        "error_rate_pct": 18.4,
        "p99_latency_ms": 4200,
        "p50_latency_ms": 320,
        "requests_per_second": 142,
        "active_db_connections": 98,
        "db_connection_pool_max": 100,
        "cpu_utilisation_pct": 61,
        "memory_utilisation_pct": 72,
        "note": "DB connection pool near exhaustion — active_db_connections approaching pool max",
    },
    "auth-service": {
        "error_rate_pct": 2.1,
        "p99_latency_ms": 980,
        "p50_latency_ms": 45,
        "requests_per_second": 380,
        "heap_used_mb": 1820,
        "heap_max_mb": 2048,
        "gc_pause_ms_p99": 420,
        "cpu_utilisation_pct": 85,
        "memory_utilisation_pct": 89,
        "note": "High heap usage with frequent GC pauses — potential memory leak",
    },
    "api-gateway": {
        "error_rate_pct": 0.3,
        "p99_latency_ms": 210,
        "p50_latency_ms": 22,
        "requests_per_second": 1240,
        "timeout_rate_pct": 0.1,
        "cpu_utilisation_pct": 34,
        "memory_utilisation_pct": 48,
        "note": "Metrics within normal operating range",
    },
    "checkout-service": {
        "error_rate_pct": 12.7,
        "p99_latency_ms": 5800,
        "p50_latency_ms": 890,
        "requests_per_second": 78,
        "downstream_timeout_rate_pct": 11.2,
        "cpu_utilisation_pct": 42,
        "memory_utilisation_pct": 55,
        "note": "High error rate and latency — likely caused by dependency failure on payments-service",
    },
    "inventory-service": {
        "error_rate_pct": 0.8,
        "p99_latency_ms": 150,
        "p50_latency_ms": 18,
        "requests_per_second": 220,
        "cache_hit_rate_pct": 91,
        "cpu_utilisation_pct": 28,
        "memory_utilisation_pct": 44,
        "note": "Metrics within normal operating range",
    },
}

_DEFAULT_METRICS: dict[str, Any] = {
    "error_rate_pct": 5.0,
    "p99_latency_ms": 1200,
    "p50_latency_ms": 120,
    "requests_per_second": 100,
    "cpu_utilisation_pct": 55,
    "memory_utilisation_pct": 60,
    "note": "No specific metrics profile available for this service",
}

_DEPLOYMENT_HISTORY: dict[str, list[dict[str, Any]]] = {
    "payments-service": [
        {
            "version": "v2.14.3",
            "deployed_at": "2026-04-23T14:32:00Z",
            "deployed_by": "ci-bot",
            "duration_seconds": 94,
            "status": "success",
            "change_summary": "Increase worker thread count from 8 to 16; bump DB client lib to 3.2.1",
        },
        {
            "version": "v2.14.2",
            "deployed_at": "2026-04-22T10:15:00Z",
            "deployed_by": "alice@example.com",
            "duration_seconds": 87,
            "status": "success",
            "change_summary": "Fix input validation on /payments/create",
        },
        {
            "version": "v2.14.1",
            "deployed_at": "2026-04-20T16:48:00Z",
            "deployed_by": "ci-bot",
            "duration_seconds": 91,
            "status": "success",
            "change_summary": "Dependency updates; no functional changes",
        },
    ],
    "auth-service": [
        {
            "version": "v3.5.0",
            "deployed_at": "2026-04-23T11:05:00Z",
            "deployed_by": "bob@example.com",
            "duration_seconds": 112,
            "status": "success",
            "change_summary": "Add refresh token rotation; migrate session cache to Redis cluster",
        },
        {
            "version": "v3.4.9",
            "deployed_at": "2026-04-21T09:30:00Z",
            "deployed_by": "ci-bot",
            "duration_seconds": 98,
            "status": "success",
            "change_summary": "Patch CVE-2026-1234 in JWT library",
        },
    ],
    "api-gateway": [
        {
            "version": "v1.9.2",
            "deployed_at": "2026-04-19T08:00:00Z",
            "deployed_by": "ci-bot",
            "duration_seconds": 60,
            "status": "success",
            "change_summary": "Update rate limiting config",
        },
    ],
    "checkout-service": [
        {
            "version": "v4.2.1",
            "deployed_at": "2026-04-23T13:55:00Z",
            "deployed_by": "ci-bot",
            "duration_seconds": 88,
            "status": "success",
            "change_summary": "Minor copy changes; no backend changes",
        },
    ],
    "inventory-service": [
        {
            "version": "v2.3.7",
            "deployed_at": "2026-04-22T14:20:00Z",
            "deployed_by": "ci-bot",
            "duration_seconds": 75,
            "status": "success",
            "change_summary": "Add Redis cache layer for product catalogue",
        },
    ],
}

_DEFAULT_DEPLOYMENT: list[dict[str, Any]] = [
    {
        "version": "v1.0.0",
        "deployed_at": "2026-04-23T12:00:00Z",
        "deployed_by": "ci-bot",
        "duration_seconds": 90,
        "status": "success",
        "change_summary": "Routine deployment",
    }
]


def _get_metrics(service: str) -> dict[str, Any]:
    return _METRICS.get(service, {**_DEFAULT_METRICS, "service": service})


def _get_deployment_history(service: str) -> list[dict[str, Any]]:
    return _DEPLOYMENT_HISTORY.get(service, _DEFAULT_DEPLOYMENT)


def _search_incident_history(service: str, limit: int = 5) -> list[dict[str, Any]]:
    items = dynamodb.scan(
        "Incidents",
        filter_expression=Attr("affected_service").eq(service),
    )
    results = []
    for item in items[:limit]:
        results.append(
            {
                "incident_id": item.get("incident_id"),
                "title": item.get("title"),
                "severity": item.get("severity"),
                "failure_class": item.get("failure_class"),
                "status": item.get("status"),
                "created_at": str(item.get("created_at", "")),
            }
        )
    return results


def _get_service_dependencies(service: str) -> list[dict[str, Any]]:
    items = dynamodb.scan(
        "CorpusChunks",
        filter_expression=Attr("source_file").contains(service),
    )
    results = []
    for item in items[:10]:
        text = item.get("content") or item.get("text", "")
        if text:
            results.append(
                {
                    "chunk_id": item.get("chunk_id"),
                    "source_file": item.get("source_file", ""),
                    "content": text[:500],
                }
            )
    return results


def _execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    t0 = time.perf_counter()
    try:
        if name == "get_metrics":
            result: Any = _get_metrics(tool_input["service"])
        elif name == "get_deployment_history":
            result = _get_deployment_history(tool_input["service"])
        elif name == "search_incident_history":
            result = _search_incident_history(
                tool_input["service"],
                limit=tool_input.get("limit", 5),
            )
        elif name == "get_service_dependencies":
            result = _get_service_dependencies(tool_input["service"])
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        log.warning("tool_called", stage="agent", tool_name=name,
                    duration_ms=round((time.perf_counter() - t0) * 1000), error=str(exc))
        return json.dumps({"error": str(exc)})

    log.info("tool_called", stage="agent", tool_name=name,
             duration_ms=round((time.perf_counter() - t0) * 1000))
    return json.dumps(result)


def _parse_brief(
    text: str,
    incident_id: str,
    triage: TriageResult,
    retrieval: RetrievalResult,
) -> IncidentBrief:
    text = extract_json(text)
    if not text:
        text = "{}"
    data = json.loads(text)

    affected_service = data.get("affected_service", triage.service)
    if isinstance(affected_service, list):
        affected_service = affected_service[0] if affected_service else triage.service

    failure_class = data.get("failure_class", triage.failure_class)
    if isinstance(failure_class, list):
        failure_class = failure_class[0] if failure_class else triage.failure_class

    return IncidentBrief(
        incident_id=incident_id,
        title=data.get("title", f"Incident: {triage.service}"),
        summary=data.get("summary", ""),
        severity=data.get("severity", triage.severity),
        affected_service=affected_service,
        failure_class=failure_class,
        recommended_actions=data.get("recommended_actions", []),
        runbook_references=data.get("runbook_references", []),
        retrieval_context_available=retrieval.retrieval_context_available,
        created_at=datetime.now(timezone.utc),
    )


def _call_bedrock(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return bedrock.converse_with_tools(
                model_id=settings.reasoning_model_id,
                messages=messages,
                system=_SYSTEM_PROMPT,
                tool_config=_TOOL_CONFIG,
                trace_name="agent",
            )
        except Exception as exc:
            last_exc = exc
            log.warning("agent_bedrock_retry", stage="agent", attempt=attempt + 1, error=str(exc))
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise last_exc


def run(
    alert: NormalisedAlert,
    triage: TriageResult,
    retrieval: RetrievalResult,
    incident_id: str,
) -> IncidentBrief:
    t0 = time.perf_counter()
    tool_calls_count = 0

    context_section = ""
    if retrieval.retrieval_context_available and retrieval.chunks:
        context_section = "\n\nRelevant runbook context:\n" + "\n---\n".join(retrieval.chunks)

    user_prompt = (
        f"Incident alert:\n"
        f"  Title: {alert.title}\n"
        f"  Description: {alert.description}\n"
        f"  Source: {alert.source}\n"
        f"  Service: {triage.service}\n"
        f"  Severity: {triage.severity}\n"
        f"  Failure class: {triage.failure_class}"
        f"{context_section}"
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": user_prompt}]}
    ]

    while True:
        message, _stop_reason = _call_bedrock(messages)
        messages.append({"role": "assistant", "content": message["content"]})

        tool_use_blocks = [b for b in message["content"] if "toolUse" in b]

        if not tool_use_blocks:
            text_blocks = [b["text"] for b in message["content"] if "text" in b]
            text = next((t for t in text_blocks if t.strip()), "{}")
            duration_ms = round((time.perf_counter() - t0) * 1000)
            log.info("agent_completed", stage="agent", duration_ms=duration_ms,
                     tool_calls_count=tool_calls_count)
            dims = {"environment": settings.environment, "failure_class": triage.failure_class}
            emit_pipeline_metric("agent_duration_ms", duration_ms, "Milliseconds", dims)
            emit_pipeline_metric("agent_tool_calls", tool_calls_count, "Count", dims)
            return _parse_brief(text, incident_id, triage, retrieval)

        tool_calls_count += len(tool_use_blocks)
        tool_result_contents = []
        for block in tool_use_blocks:
            tool_use = block["toolUse"]
            result_text = _execute_tool(tool_use["name"], tool_use["input"])
            tool_result_contents.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"text": result_text}],
                    }
                }
            )

        messages.append({"role": "user", "content": tool_result_contents})

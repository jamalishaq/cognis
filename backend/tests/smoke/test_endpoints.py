"""Smoke tests for the full incident response user journey.

Requires a running dev environment. Set BASE_URL to point at the server:
    BASE_URL=https://api.dev.cognis.internal pytest tests/smoke/
    BASE_URL=http://localhost:8000 pytest tests/smoke/  (local fallback)

Tests run sequentially as a single journey to share the incident_id produced
by POST /analyse without complex fixture scoping.
"""
from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TIMEOUT = float(os.getenv("SMOKE_TIMEOUT", "30"))

# Eval fields that the architecture guarantees are internal-only and must
# never appear in any public API response.
_EVAL_FIELDS = {
    "eval_ran",
    "eval_groundedness",
    "eval_completeness",
    "eval_actionability",
    "eval_confidence",
    "eval_flags",
}

_GRAFANA_PAYLOAD = {
    "title": "High Error Rate — payment-service",
    "state": "alerting",
    "message": "5xx error rate exceeded 10% for 5 minutes",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighErrorRate",
                "severity": "critical",
                "service": "payment-service",
                "env": "prod",
            },
            "annotations": {
                "description": "HTTP 5xx error rate is 14% on payment-service",
                "summary": "Payment service is returning errors",
            },
            "startsAt": "2024-06-01T10:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://grafana.prod.internal/alert/1234",
            "fingerprint": "smoke-test-abc123",
        }
    ],
    "commonLabels": {"env": "prod"},
    "commonAnnotations": {},
    "externalURL": "http://grafana.prod.internal",
    "receiver": "ops-team",
    "status": "firing",
    "groupKey": '{}:{alertname="HighErrorRate"}',
    "orgId": 1,
}


def _assert_no_eval_fields(body: dict, context: str) -> None:
    leaked = _EVAL_FIELDS & body.keys()
    assert not leaked, f"{context}: eval fields must not appear in API response — got {leaked}"


@pytest.mark.smoke
def test_incident_journey() -> None:
    """Full user journey: analyse → inspect → chat → history → resolve → verify."""
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:

        # ── Step 1: POST /analyse with a Grafana alert payload ────────────────
        analyse_resp = client.post("/analyse", json=_GRAFANA_PAYLOAD)
        assert analyse_resp.status_code == 200, (
            f"POST /analyse failed ({analyse_resp.status_code}): {analyse_resp.text}"
        )
        analyse_body = analyse_resp.json()
        assert analyse_body["status"] == "received"
        incident_id: str = analyse_body["incident_id"]
        assert incident_id.startswith("INC-"), f"Unexpected incident_id format: {incident_id}"

        # ── Step 2: GET /incidents/{id} — brief stored, no eval fields ────────
        brief_resp = client.get(f"/incidents/{incident_id}")
        assert brief_resp.status_code == 200, (
            f"GET /incidents/{incident_id} failed ({brief_resp.status_code}): {brief_resp.text}"
        )
        brief = brief_resp.json()

        _assert_no_eval_fields(brief, "GET /incidents/{id}")

        assert brief["incident_id"] == incident_id
        assert brief["title"], "Brief title must not be empty"
        assert brief["summary"], "Brief summary must not be empty"
        assert brief["severity"] in {"critical", "high", "medium", "low", "unknown"}
        assert brief["affected_service"], "affected_service must not be empty"
        assert brief["failure_class"], "failure_class must not be empty"
        assert isinstance(brief["recommended_actions"], list)
        assert isinstance(brief["runbook_references"], list)
        assert "retrieval_context_available" in brief
        assert "created_at" in brief

        # ── Step 3: POST /chat with a follow-up question ──────────────────────
        chat_resp = client.post(
            "/chat",
            json={"incident_id": incident_id, "message": "What is the most likely root cause?"},
        )
        assert chat_resp.status_code == 200, (
            f"POST /chat failed ({chat_resp.status_code}): {chat_resp.text}"
        )
        chat_text = chat_resp.text
        assert chat_text.strip(), "Chat response body must not be empty"

        # ── Step 4: GET /incidents/{id}/history — messages were stored ────────
        history_resp = client.get(f"/incidents/{incident_id}/history")
        assert history_resp.status_code == 200, (
            f"GET /incidents/{incident_id}/history failed "
            f"({history_resp.status_code}): {history_resp.text}"
        )
        history = history_resp.json()
        assert history["incident_id"] == incident_id

        messages = history["messages"]
        assert len(messages) >= 2, (
            f"Expected at least 2 messages (user + assistant) but got {len(messages)}"
        )

        roles = [m["role"] for m in messages]
        assert "user" in roles, "Chat history must contain a user message"
        assert "assistant" in roles, "Chat history must contain an assistant message"

        for msg in messages:
            assert msg["message_id"].startswith("MSG-"), (
                f"Unexpected message_id format: {msg['message_id']}"
            )
            assert msg["incident_id"] == incident_id
            assert msg["content"].strip(), "Message content must not be empty"
            assert msg["role"] in {"user", "assistant"}
            assert "timestamp" in msg

        # ── Step 5: POST /incidents/{id}/resolve ──────────────────────────────
        resolve_resp = client.post(
            f"/incidents/{incident_id}/resolve",
            json={
                "incident_id": incident_id,
                "resolution_notes": "Root cause identified: misconfigured rate limiter. Rolled back deployment d4f9a1.",
                "resolved_by": "smoke-test-runner",
            },
        )
        assert resolve_resp.status_code == 200, (
            f"POST /incidents/{incident_id}/resolve failed "
            f"({resolve_resp.status_code}): {resolve_resp.text}"
        )
        resolve_body = resolve_resp.json()
        assert resolve_body["incident_id"] == incident_id
        assert resolve_body["status"] == "resolved"
        assert "resolved_at" in resolve_body
        assert resolve_body["message"], "Resolve response message must not be empty"

        # ── Step 6: GET /incidents/{id} — incident still accessible ──────────
        # IncidentBrief (the public response model) does not expose status —
        # resolution state is internal. We verify the incident is still
        # reachable (200) and continues to have no eval fields, then confirm
        # the DynamoDB status update persisted by asserting a re-resolve
        # attempt returns 409 Conflict.
        post_resolve_resp = client.get(f"/incidents/{incident_id}")
        assert post_resolve_resp.status_code == 200, (
            f"GET /incidents/{incident_id} after resolve failed "
            f"({post_resolve_resp.status_code}): {post_resolve_resp.text}"
        )
        post_resolve_brief = post_resolve_resp.json()
        _assert_no_eval_fields(post_resolve_brief, "GET /incidents/{id} after resolve")
        assert post_resolve_brief["incident_id"] == incident_id

        # A second resolve attempt must be rejected — proves status is "resolved"
        # in DynamoDB (409 Conflict).
        re_resolve_resp = client.post(
            f"/incidents/{incident_id}/resolve",
            json={
                "incident_id": incident_id,
                "resolution_notes": "Duplicate resolve attempt from smoke test",
                "resolved_by": "smoke-test-runner",
            },
        )
        assert re_resolve_resp.status_code == 409, (
            f"Re-resolving an already-resolved incident must return 409, "
            f"got {re_resolve_resp.status_code}: {re_resolve_resp.text}"
        )

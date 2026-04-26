from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.resolve import ResolveRequest, ResolveResponse

NOW = datetime(2024, 6, 1, 13, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ResolveRequest
# ---------------------------------------------------------------------------


def test_resolve_request_valid():
    req = ResolveRequest(
        incident_id="INC-20240601-001",
        resolution_notes="Scaled up the DB connection pool and restarted the service.",
    )
    assert req.incident_id == "INC-20240601-001"
    assert req.resolution_notes == "Scaled up the DB connection pool and restarted the service."
    assert req.resolved_by is None


def test_resolve_request_with_resolved_by():
    req = ResolveRequest(
        incident_id="INC-20240601-001",
        resolution_notes="Fixed the issue.",
        resolved_by="alice@example.com",
    )
    assert req.resolved_by == "alice@example.com"


def test_resolve_request_missing_incident_id_raises():
    with pytest.raises(ValidationError):
        ResolveRequest(resolution_notes="Fixed.")


def test_resolve_request_missing_resolution_notes_raises():
    with pytest.raises(ValidationError):
        ResolveRequest(incident_id="INC-20240601-001")


def test_resolve_request_resolved_by_optional():
    req = ResolveRequest(
        incident_id="INC-20240601-001",
        resolution_notes="Handled by automation.",
        resolved_by=None,
    )
    assert req.resolved_by is None


# ---------------------------------------------------------------------------
# ResolveResponse
# ---------------------------------------------------------------------------


def test_resolve_response_valid():
    resp = ResolveResponse(
        incident_id="INC-20240601-001",
        resolved_at=NOW,
        message="Incident INC-20240601-001 has been resolved.",
    )
    assert resp.incident_id == "INC-20240601-001"
    assert resp.status == "resolved"
    assert resp.resolved_at == NOW
    assert "INC-20240601-001" in resp.message


def test_resolve_response_status_default():
    resp = ResolveResponse(
        incident_id="INC-20240601-001",
        resolved_at=NOW,
        message="Done.",
    )
    assert resp.status == "resolved"


def test_resolve_response_status_must_be_resolved():
    with pytest.raises(ValidationError):
        ResolveResponse(
            incident_id="INC-20240601-001",
            status="open",  # only "resolved" is allowed
            resolved_at=NOW,
            message="Done.",
        )


def test_resolve_response_missing_required_raises():
    for missing in ("incident_id", "resolved_at", "message"):
        data = {
            "incident_id": "INC-20240601-001",
            "resolved_at": NOW,
            "message": "Done.",
        }
        del data[missing]
        with pytest.raises(ValidationError):
            ResolveResponse(**data)


def test_resolve_response_serialisation():
    resp = ResolveResponse(
        incident_id="INC-20240601-001",
        resolved_at=NOW,
        message="Resolved.",
    )
    data = resp.model_dump()
    assert data["status"] == "resolved"
    assert data["incident_id"] == "INC-20240601-001"

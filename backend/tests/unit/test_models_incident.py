from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.incident import IncidentBrief, IncidentRecord

NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

VALID_BRIEF = dict(
    incident_id="INC-20240601-001",
    title="Database connection pool exhausted",
    summary="The primary DB is rejecting new connections.",
    severity="critical",
    affected_service="payments",
    failure_class="resource_exhaustion",
    created_at=NOW,
)


# ---------------------------------------------------------------------------
# IncidentBrief
# ---------------------------------------------------------------------------


def test_incident_brief_minimal():
    brief = IncidentBrief(**VALID_BRIEF)
    assert brief.incident_id == "INC-20240601-001"
    assert brief.severity == "critical"
    assert brief.recommended_actions == []
    assert brief.runbook_references == []
    assert brief.retrieval_context_available is True


def test_incident_brief_full():
    brief = IncidentBrief(
        **VALID_BRIEF,
        recommended_actions=["Restart pool", "Check metrics"],
        runbook_references=["runbooks/db-exhaustion.md"],
        retrieval_context_available=False,
    )
    assert len(brief.recommended_actions) == 2
    assert brief.retrieval_context_available is False


def test_incident_brief_missing_required_raises():
    for field in ("incident_id", "title", "summary", "severity", "affected_service", "failure_class", "created_at"):
        data = {k: v for k, v in VALID_BRIEF.items() if k != field}
        with pytest.raises(ValidationError):
            IncidentBrief(**data)


def test_incident_brief_invalid_severity_raises():
    with pytest.raises(ValidationError):
        IncidentBrief(**{**VALID_BRIEF, "severity": "extreme"})


def test_incident_brief_all_severities():
    for severity in ("critical", "high", "medium", "low", "unknown"):
        brief = IncidentBrief(**{**VALID_BRIEF, "severity": severity})
        assert brief.severity == severity


# incident_id format validation
def test_incident_brief_valid_id_formats():
    valid_ids = [
        "INC-20240601-001",
        "INC-20240101-999",
        "INC-20991231-000",
    ]
    for iid in valid_ids:
        brief = IncidentBrief(**{**VALID_BRIEF, "incident_id": iid})
        assert brief.incident_id == iid


def test_incident_brief_invalid_id_raises():
    invalid_ids = [
        "INC-2024060-001",   # date too short
        "INC-20240601-01",   # sequence too short
        "INC-20240601-0001", # sequence too long
        "inc-20240601-001",  # lowercase
        "20240601-001",      # missing prefix
        "INC-20240601001",   # missing hyphen
        "",
        "INC-YYYYMMDD-NNN",
    ]
    for iid in invalid_ids:
        with pytest.raises(ValidationError):
            IncidentBrief(**{**VALID_BRIEF, "incident_id": iid})


# ---------------------------------------------------------------------------
# IncidentRecord
# ---------------------------------------------------------------------------


def test_incident_record_defaults():
    record = IncidentRecord(**VALID_BRIEF)
    assert record.status == "open"
    assert record.resolved_at is None
    assert record.resolution_notes is None
    assert record.resolved_by is None


def test_incident_record_resolved():
    resolve_time = datetime(2024, 6, 1, 13, 0, 0, tzinfo=timezone.utc)
    record = IncidentRecord(
        **VALID_BRIEF,
        status="resolved",
        resolved_at=resolve_time,
        resolution_notes="Increased pool size and restarted service.",
        resolved_by="ops-engineer",
    )
    assert record.status == "resolved"
    assert record.resolved_at == resolve_time
    assert record.resolution_notes == "Increased pool size and restarted service."
    assert record.resolved_by == "ops-engineer"


def test_incident_record_invalid_status_raises():
    with pytest.raises(ValidationError):
        IncidentRecord(**{**VALID_BRIEF, "status": "pending"})


def test_incident_record_inherits_id_validation():
    with pytest.raises(ValidationError):
        IncidentRecord(**{**VALID_BRIEF, "incident_id": "INVALID-ID"})


def test_incident_record_inherits_severity_validation():
    with pytest.raises(ValidationError):
        IncidentRecord(**{**VALID_BRIEF, "severity": "ultra"})


def test_incident_record_is_incident_brief_subtype():
    record = IncidentRecord(**VALID_BRIEF)
    assert isinstance(record, IncidentBrief)

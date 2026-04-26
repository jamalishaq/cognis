from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models.incident import IncidentBrief
from app.providers.notifications.ses import (
    SESNotificationProvider,
    _compose_html,
    _compose_subject,
    _compose_text,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def incident() -> IncidentBrief:
    return IncidentBrief(
        incident_id="INC-20240101-001",
        title="Database connection pool exhausted",
        summary="The primary database is rejecting new connections due to pool exhaustion.",
        severity="critical",
        affected_service="payments-api",
        failure_class="resource_exhaustion",
        recommended_actions=["Scale connection pool", "Restart affected pods"],
        runbook_references=["runbooks/database.md"],
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Subject composition
# ---------------------------------------------------------------------------

def test_subject_includes_severity_uppercased(incident):
    assert "CRITICAL" in _compose_subject(incident)


def test_subject_includes_incident_id(incident):
    assert "INC-20240101-001" in _compose_subject(incident)


def test_subject_includes_title(incident):
    assert "Database connection pool exhausted" in _compose_subject(incident)


def test_subject_has_cognis_prefix(incident):
    assert _compose_subject(incident).startswith("[Cognis]")


# ---------------------------------------------------------------------------
# Plain-text body composition
# ---------------------------------------------------------------------------

def test_text_body_includes_incident_id(incident):
    assert "INC-20240101-001" in _compose_text(incident)


def test_text_body_includes_severity(incident):
    assert "critical" in _compose_text(incident)


def test_text_body_includes_service(incident):
    assert "payments-api" in _compose_text(incident)


def test_text_body_includes_failure_class(incident):
    assert "resource_exhaustion" in _compose_text(incident)


def test_text_body_includes_summary(incident):
    assert "rejecting new connections" in _compose_text(incident)


def test_text_body_includes_recommended_actions(incident):
    text = _compose_text(incident)
    assert "Scale connection pool" in text
    assert "Restart affected pods" in text


def test_text_body_includes_runbook_references(incident):
    assert "runbooks/database.md" in _compose_text(incident)


def test_text_body_no_actions_shows_none(incident):
    incident.recommended_actions = []
    assert "None" in _compose_text(incident)


# ---------------------------------------------------------------------------
# HTML body composition
# ---------------------------------------------------------------------------

def test_html_body_includes_incident_id(incident):
    assert "INC-20240101-001" in _compose_html(incident)


def test_html_body_includes_summary(incident):
    assert "rejecting new connections" in _compose_html(incident)


def test_html_body_includes_recommended_actions(incident):
    html = _compose_html(incident)
    assert "Scale connection pool" in html
    assert "Restart affected pods" in html


def test_html_body_no_actions_shows_none(incident):
    incident.recommended_actions = []
    assert "<li>None</li>" in _compose_html(incident)


# ---------------------------------------------------------------------------
# SESNotificationProvider.send — log mode
# ---------------------------------------------------------------------------

@patch("app.providers.notifications.ses.settings")
def test_send_log_mode_does_not_call_ses(mock_settings, incident):
    mock_settings.ses_mode = "log"
    mock_settings.ses_to_emails = "ops@example.com"

    with patch("app.providers.notifications.ses.ses_service.send_email") as mock_send:
        asyncio.run(SESNotificationProvider().send(incident))
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# SESNotificationProvider.send — send mode
# ---------------------------------------------------------------------------

@patch("app.providers.notifications.ses.settings")
def test_send_mode_calls_ses_service(mock_settings, incident):
    mock_settings.ses_mode = "send"
    mock_settings.ses_to_emails = "ops@example.com,oncall@example.com"
    mock_settings.ses_from_email = "alerts@cognis.internal"

    with patch("app.providers.notifications.ses.ses_service.send_email", return_value="msg-001") as mock_send:
        asyncio.run(SESNotificationProvider().send(incident))
        mock_send.assert_called_once()


@patch("app.providers.notifications.ses.settings")
def test_send_mode_passes_correct_recipients(mock_settings, incident):
    mock_settings.ses_mode = "send"
    mock_settings.ses_to_emails = "ops@example.com, oncall@example.com"
    mock_settings.ses_from_email = "alerts@cognis.internal"

    with patch("app.providers.notifications.ses.ses_service.send_email", return_value="msg-001") as mock_send:
        asyncio.run(SESNotificationProvider().send(incident))
        to_addresses = mock_send.call_args[0][0]
        assert to_addresses == ["ops@example.com", "oncall@example.com"]


@patch("app.providers.notifications.ses.settings")
def test_send_mode_passes_subject(mock_settings, incident):
    mock_settings.ses_mode = "send"
    mock_settings.ses_to_emails = "ops@example.com"
    mock_settings.ses_from_email = "alerts@cognis.internal"

    with patch("app.providers.notifications.ses.ses_service.send_email", return_value="msg-001") as mock_send:
        asyncio.run(SESNotificationProvider().send(incident))
        subject = mock_send.call_args[0][1]
        assert "INC-20240101-001" in subject
        assert "CRITICAL" in subject


@patch("app.providers.notifications.ses.settings")
def test_send_mode_no_recipients_skips_send(mock_settings, incident):
    mock_settings.ses_mode = "send"
    mock_settings.ses_to_emails = ""

    with patch("app.providers.notifications.ses.ses_service.send_email") as mock_send:
        asyncio.run(SESNotificationProvider().send(incident))
        mock_send.assert_not_called()


@patch("app.providers.notifications.ses.settings")
def test_send_mode_whitespace_only_recipients_skips_send(mock_settings, incident):
    mock_settings.ses_mode = "send"
    mock_settings.ses_to_emails = "  ,  ,  "

    with patch("app.providers.notifications.ses.ses_service.send_email") as mock_send:
        asyncio.run(SESNotificationProvider().send(incident))
        mock_send.assert_not_called()

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.models.incident import IncidentBrief
from app.lambdas.notify import handler, _process_record, _send_all


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def incident() -> IncidentBrief:
    return IncidentBrief(
        incident_id="INC-20240101-001",
        title="Database connection pool exhausted",
        summary="Primary DB rejecting new connections.",
        severity="critical",
        affected_service="payments-api",
        failure_class="resource_exhaustion",
        recommended_actions=["Scale connection pool"],
        runbook_references=["runbooks/database.md"],
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture()
def sqs_record(incident: IncidentBrief) -> dict:
    return {"body": incident.model_dump_json()}


def _make_event(*records: dict) -> dict:
    return {"Records": list(records)}


# ---------------------------------------------------------------------------
# Happy path — single record, single provider
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_handler_calls_send_on_active_provider(mock_get_providers, sqs_record, incident):
    mock_provider = MagicMock()
    mock_provider.send = AsyncMock()
    mock_get_providers.return_value = [mock_provider]

    handler(_make_event(sqs_record), None)

    mock_provider.send.assert_awaited_once()
    called_incident = mock_provider.send.call_args[0][0]
    assert called_incident.incident_id == incident.incident_id


@patch("app.lambdas.notify.get_active_providers")
def test_handler_passes_correct_incident_fields(mock_get_providers, sqs_record, incident):
    mock_provider = MagicMock()
    mock_provider.send = AsyncMock()
    mock_get_providers.return_value = [mock_provider]

    handler(_make_event(sqs_record), None)

    called_incident = mock_provider.send.call_args[0][0]
    assert called_incident.severity == "critical"
    assert called_incident.affected_service == "payments-api"
    assert called_incident.title == incident.title


# ---------------------------------------------------------------------------
# Multiple providers — all called
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_handler_calls_all_active_providers(mock_get_providers, sqs_record):
    provider_a = MagicMock()
    provider_a.send = AsyncMock()
    provider_b = MagicMock()
    provider_b.send = AsyncMock()
    mock_get_providers.return_value = [provider_a, provider_b]

    handler(_make_event(sqs_record), None)

    provider_a.send.assert_awaited_once()
    provider_b.send.assert_awaited_once()


@patch("app.lambdas.notify.get_active_providers")
def test_handler_calls_providers_with_same_incident(mock_get_providers, sqs_record, incident):
    provider_a = MagicMock()
    provider_a.send = AsyncMock()
    provider_b = MagicMock()
    provider_b.send = AsyncMock()
    mock_get_providers.return_value = [provider_a, provider_b]

    handler(_make_event(sqs_record), None)

    assert provider_a.send.call_args[0][0].incident_id == incident.incident_id
    assert provider_b.send.call_args[0][0].incident_id == incident.incident_id


# ---------------------------------------------------------------------------
# Multiple SQS records in one batch
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_handler_processes_all_records_in_batch(mock_get_providers, incident):
    mock_provider = MagicMock()
    mock_provider.send = AsyncMock()
    mock_get_providers.return_value = [mock_provider]

    incident2 = incident.model_copy(update={"incident_id": "INC-20240101-002"})
    record1 = {"body": incident.model_dump_json()}
    record2 = {"body": incident2.model_dump_json()}

    handler(_make_event(record1, record2), None)

    assert mock_provider.send.await_count == 2


# ---------------------------------------------------------------------------
# Provider failure — logged, does not raise, other providers still called
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_provider_failure_does_not_raise(mock_get_providers, sqs_record):
    failing_provider = MagicMock()
    failing_provider.send = AsyncMock(side_effect=RuntimeError("SES quota exceeded"))
    mock_get_providers.return_value = [failing_provider]

    # Should not raise
    handler(_make_event(sqs_record), None)


@patch("app.lambdas.notify.get_active_providers")
def test_failing_provider_does_not_block_subsequent_provider(mock_get_providers, sqs_record):
    failing_provider = MagicMock()
    failing_provider.send = AsyncMock(side_effect=RuntimeError("SES quota exceeded"))
    good_provider = MagicMock()
    good_provider.send = AsyncMock()
    mock_get_providers.return_value = [failing_provider, good_provider]

    handler(_make_event(sqs_record), None)

    good_provider.send.assert_awaited_once()


@patch("app.lambdas.notify.get_active_providers")
def test_provider_failure_logs_error(mock_get_providers, sqs_record, caplog):
    import logging
    failing_provider = MagicMock()
    failing_provider.__class__.__name__ = "SESNotificationProvider"
    failing_provider.send = AsyncMock(side_effect=ConnectionError("endpoint unreachable"))
    mock_get_providers.return_value = [failing_provider]

    with caplog.at_level(logging.ERROR, logger="app.lambdas.notify"):
        handler(_make_event(sqs_record), None)

    assert any("SESNotificationProvider" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Malformed SQS record body — logged, does not raise
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_invalid_json_body_does_not_raise(mock_get_providers):
    mock_get_providers.return_value = []
    bad_record = {"body": "not valid json {{{"}

    handler(_make_event(bad_record), None)


@patch("app.lambdas.notify.get_active_providers")
def test_invalid_json_body_skips_send(mock_get_providers):
    mock_provider = MagicMock()
    mock_provider.send = AsyncMock()
    mock_get_providers.return_value = [mock_provider]
    bad_record = {"body": "not valid json {{{"}

    handler(_make_event(bad_record), None)

    mock_provider.send.assert_not_awaited()


@patch("app.lambdas.notify.get_active_providers")
def test_invalid_json_body_logs_error(mock_get_providers, caplog):
    import logging
    mock_get_providers.return_value = []
    bad_record = {"body": "not valid json {{{"}

    with caplog.at_level(logging.ERROR, logger="app.lambdas.notify"):
        handler(_make_event(bad_record), None)

    assert len(caplog.records) >= 1


@patch("app.lambdas.notify.get_active_providers")
def test_invalid_incident_schema_does_not_raise(mock_get_providers):
    mock_get_providers.return_value = []
    # Valid JSON but missing required fields
    bad_record = {"body": json.dumps({"incident_id": "not-a-valid-id"})}

    handler(_make_event(bad_record), None)


@patch("app.lambdas.notify.get_active_providers")
def test_invalid_incident_schema_skips_send(mock_get_providers):
    mock_provider = MagicMock()
    mock_provider.send = AsyncMock()
    mock_get_providers.return_value = [mock_provider]
    bad_record = {"body": json.dumps({"incident_id": "not-a-valid-id"})}

    handler(_make_event(bad_record), None)

    mock_provider.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Mixed batch — one bad record, one good record
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_bad_record_does_not_prevent_good_record_from_being_processed(mock_get_providers, incident):
    mock_provider = MagicMock()
    mock_provider.send = AsyncMock()
    mock_get_providers.return_value = [mock_provider]

    bad_record = {"body": "not json"}
    good_record = {"body": incident.model_dump_json()}

    handler(_make_event(bad_record, good_record), None)

    mock_provider.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Empty batch
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_empty_records_list_does_not_raise(mock_get_providers):
    mock_get_providers.return_value = []
    handler({"Records": []}, None)


@patch("app.lambdas.notify.get_active_providers")
def test_missing_records_key_does_not_raise(mock_get_providers):
    mock_get_providers.return_value = []
    handler({}, None)


# ---------------------------------------------------------------------------
# No active providers — send not called, no error
# ---------------------------------------------------------------------------

@patch("app.lambdas.notify.get_active_providers")
def test_no_active_providers_does_not_raise(mock_get_providers, sqs_record):
    mock_get_providers.return_value = []
    handler(_make_event(sqs_record), None)

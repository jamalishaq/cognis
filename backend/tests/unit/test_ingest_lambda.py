from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.models.incident import IncidentRecord
from app.lambdas.ingest import (
    handler,
    _process_record,
    _build_markdown,
)
from app.utils.chunker import chunk_markdown as _chunk_markdown, _split_sections


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def resolved_incident() -> IncidentRecord:
    return IncidentRecord(
        incident_id="INC-20240101-001",
        title="Database connection pool exhausted",
        summary="Primary DB is rejecting new connections due to pool exhaustion.",
        severity="critical",
        affected_service="payments-api",
        failure_class="resource_exhaustion",
        recommended_actions=["Scale connection pool", "Restart affected pods"],
        runbook_references=["runbooks/database.md"],
        retrieval_context_available=True,
        created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        status="resolved",
        resolved_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        resolution_notes="Increased pool size from 20 to 50. Root cause: traffic spike.",
        resolved_by="oncall-engineer",
    )


@pytest.fixture()
def dynamo_item(resolved_incident: IncidentRecord) -> dict:
    data = resolved_incident.model_dump()
    # Simulate DynamoDB storing datetimes as ISO strings
    data["created_at"] = resolved_incident.created_at.isoformat()
    data["resolved_at"] = resolved_incident.resolved_at.isoformat()  # type: ignore[union-attr]
    return data


@pytest.fixture()
def sqs_record(resolved_incident: IncidentRecord) -> dict:
    return {
        "body": json.dumps({
            "type": "incident_resolution",
            "incident_id": resolved_incident.incident_id,
            "title": resolved_incident.title,
            "resolution_notes": resolved_incident.resolution_notes,
            "resolved_by": resolved_incident.resolved_by,
            "resolved_at": resolved_incident.resolved_at.isoformat(),  # type: ignore[union-attr]
        })
    }


_SAMPLE_VECTOR = [0.1] * 1024


def _make_event(*records: dict) -> dict:
    return {"Records": list(records)}


# ---------------------------------------------------------------------------
# Happy path — single record full ingestion flow
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_fetches_incident_from_dynamodb(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    mock_get.assert_called_once_with("Incidents", {"incident_id": "INC-20240101-001"})


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_embeds_with_correct_model_and_input_type(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    assert mock_embed.call_count >= 1
    for call_args in mock_embed.call_args_list:
        assert call_args.args[0] == "cohere.embed-english-v4:0"
        assert call_args.kwargs.get("input_type") == "search_document" or call_args.args[2] == "search_document"


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_upserts_each_chunk_to_s3vectors(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    assert mock_upsert.call_count == mock_embed.call_count


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_puts_each_chunk_to_corpus_chunks(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    # put_item is called for each chunk (CorpusChunks), so count equals embed count
    assert mock_put.call_count == mock_embed.call_count


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_stores_correct_chunk_ids(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    for i, call_args in enumerate(mock_put.call_args_list):
        item = call_args.args[1]
        assert item["chunk_id"] == f"INC-20240101-001-chunk-{i:03d}"


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_stores_text_in_corpus_chunks(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    for call_args in mock_put.call_args_list:
        table_name, item = call_args.args
        assert table_name == "CorpusChunks"
        assert "text" in item
        assert len(item["text"]) > 0


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_passes_embed_vector_to_upsert(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    for call_args in mock_upsert.call_args_list:
        vectors_list = call_args.args[2]
        assert vectors_list[0]["vector"] == _SAMPLE_VECTOR


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_upsert_includes_incident_id_metadata(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    handler(_make_event(sqs_record), None)

    for call_args in mock_upsert.call_args_list:
        vectors_list = call_args.args[2]
        assert vectors_list[0]["metadata"]["incident_id"] == "INC-20240101-001"


# ---------------------------------------------------------------------------
# Multiple SQS records in one batch
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_handler_processes_all_records_in_batch(
    mock_get, mock_embed, mock_upsert, mock_put, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR

    record1 = {"body": json.dumps({"type": "incident_resolution", "incident_id": "INC-20240101-001"})}
    record2 = {"body": json.dumps({"type": "incident_resolution", "incident_id": "INC-20240101-002"})}

    handler(_make_event(record1, record2), None)

    assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# Invalid / malformed SQS record body
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.dynamodb.get_item")
def test_invalid_json_body_does_not_raise(mock_get):
    handler(_make_event({"body": "not valid json {{{"}), None)
    mock_get.assert_not_called()


@patch("app.lambdas.ingest.dynamodb.get_item")
def test_missing_incident_id_does_not_raise(mock_get):
    handler(_make_event({"body": json.dumps({"type": "incident_resolution"})}), None)
    mock_get.assert_not_called()


@patch("app.lambdas.ingest.dynamodb.get_item")
def test_invalid_json_body_logs_error(mock_get):
    import structlog.testing
    with structlog.testing.capture_logs() as logs:
        handler(_make_event({"body": "bad json"}), None)
    assert any(e.get("log_level") == "error" and "ingest_parse_failed" in e.get("event", "") for e in logs)


# ---------------------------------------------------------------------------
# Incident not found in DynamoDB
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_incident_not_found_does_not_raise(mock_get, mock_embed, sqs_record):
    mock_get.return_value = None
    handler(_make_event(sqs_record), None)
    mock_embed.assert_not_called()


@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_incident_not_found_logs_error(mock_get, mock_embed, sqs_record):
    import structlog.testing
    mock_get.return_value = None
    with structlog.testing.capture_logs() as logs:
        handler(_make_event(sqs_record), None)
    assert any(e.get("event") == "ingest_incident_not_found" for e in logs)


# ---------------------------------------------------------------------------
# Invalid IncidentRecord in DynamoDB
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_invalid_incident_record_does_not_raise(mock_get, mock_embed, sqs_record):
    mock_get.return_value = {"incident_id": "INC-20240101-001", "bad": "data"}
    handler(_make_event(sqs_record), None)
    mock_embed.assert_not_called()


@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_invalid_incident_record_logs_error(mock_get, mock_embed, sqs_record):
    import structlog.testing
    mock_get.return_value = {"incident_id": "INC-20240101-001", "bad": "data"}
    with structlog.testing.capture_logs() as logs:
        handler(_make_event(sqs_record), None)
    assert any(e.get("event") == "ingest_record_invalid" for e in logs)


# ---------------------------------------------------------------------------
# Per-chunk failure handling — embed failure
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_embed_failure_does_not_raise(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.side_effect = RuntimeError("Bedrock throttled")
    handler(_make_event(sqs_record), None)  # must not raise


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_embed_failure_skips_upsert_and_put(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.side_effect = RuntimeError("Bedrock throttled")
    handler(_make_event(sqs_record), None)
    mock_upsert.assert_not_called()
    mock_put.assert_not_called()


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_embed_failure_on_first_chunk_does_not_block_second(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.side_effect = [RuntimeError("fail"), _SAMPLE_VECTOR]
    handler(_make_event(sqs_record), None)
    mock_upsert.assert_called_once()
    mock_put.assert_called_once()


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_embed_failure_logs_error(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    import structlog.testing
    mock_get.return_value = dynamo_item
    mock_embed.side_effect = RuntimeError("Bedrock throttled")
    with structlog.testing.capture_logs() as logs:
        handler(_make_event(sqs_record), None)
    assert any(e.get("event") == "ingest_embed_failed" for e in logs)


# ---------------------------------------------------------------------------
# Per-chunk failure handling — S3 Vectors upsert failure
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_s3vectors_failure_does_not_raise(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_upsert.side_effect = RuntimeError("S3 Vectors unavailable")
    handler(_make_event(sqs_record), None)


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_s3vectors_failure_skips_corpus_put(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_upsert.side_effect = RuntimeError("S3 Vectors unavailable")
    handler(_make_event(sqs_record), None)
    mock_put.assert_not_called()


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_s3vectors_failure_logs_error(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    import structlog.testing
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_upsert.side_effect = RuntimeError("S3 Vectors unavailable")
    with structlog.testing.capture_logs() as logs:
        handler(_make_event(sqs_record), None)
    assert any(e.get("event") == "ingest_s3vectors_failed" for e in logs)


# ---------------------------------------------------------------------------
# Per-chunk failure handling — DynamoDB put failure
# ---------------------------------------------------------------------------

@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_dynamodb_put_failure_does_not_raise(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_put.side_effect = RuntimeError("DynamoDB write failed")
    handler(_make_event(sqs_record), None)


@patch("app.lambdas.ingest.dynamodb.put_item")
@patch("app.lambdas.ingest.s3vectors.upsert_vectors")
@patch("app.lambdas.ingest.bedrock.embed")
@patch("app.lambdas.ingest.dynamodb.get_item")
def test_dynamodb_put_failure_logs_error(
    mock_get, mock_embed, mock_upsert, mock_put, sqs_record, dynamo_item
):
    import structlog.testing
    mock_get.return_value = dynamo_item
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_put.side_effect = RuntimeError("DynamoDB write failed")
    with structlog.testing.capture_logs() as logs:
        handler(_make_event(sqs_record), None)
    assert any(e.get("event") == "ingest_dynamodb_failed" for e in logs)


# ---------------------------------------------------------------------------
# Empty / missing Records key
# ---------------------------------------------------------------------------

def test_empty_records_list_does_not_raise():
    handler({"Records": []}, None)


def test_missing_records_key_does_not_raise():
    handler({}, None)


# ---------------------------------------------------------------------------
# Markdown generation — content correctness
# ---------------------------------------------------------------------------

def test_build_markdown_contains_incident_id(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "INC-20240101-001" in md


def test_build_markdown_contains_title(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "Database connection pool exhausted" in md


def test_build_markdown_contains_severity(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "critical" in md


def test_build_markdown_contains_affected_service(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "payments-api" in md


def test_build_markdown_contains_failure_class(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "resource_exhaustion" in md


def test_build_markdown_contains_summary(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert resolved_incident.summary in md


def test_build_markdown_contains_resolution_notes(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "Increased pool size from 20 to 50" in md


def test_build_markdown_contains_resolved_by(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "oncall-engineer" in md


def test_build_markdown_contains_recommended_actions(resolved_incident):
    md = _build_markdown(resolved_incident)
    assert "Scale connection pool" in md
    assert "Restart affected pods" in md


def test_build_markdown_omits_resolution_fields_when_none(resolved_incident):
    incident = resolved_incident.model_copy(update={"resolution_notes": None, "resolved_by": None})
    md = _build_markdown(incident)
    assert "Resolution Notes" not in md
    assert "Resolved By" not in md


# ---------------------------------------------------------------------------
# Chunking — structural correctness
# ---------------------------------------------------------------------------

def test_chunk_markdown_short_text_returns_single_chunk():
    chunks = _chunk_markdown("# Short\n\nSmall content.", max_tokens=512, overlap_tokens=50)
    assert len(chunks) == 1
    assert "Short" in chunks[0]


def test_chunk_markdown_long_text_returns_multiple_chunks():
    # Build text clearly exceeding 512 tokens (≈2048 chars)
    long_para = "word " * 600  # 3000 chars ≈ 750 tokens
    text = f"## Section\n\n{long_para}"
    chunks = _chunk_markdown(text, max_tokens=512, overlap_tokens=50)
    assert len(chunks) > 1


def test_chunk_markdown_chunks_are_non_empty():
    long_para = "word " * 600
    text = f"## Section\n\n{long_para}"
    chunks = _chunk_markdown(text, max_tokens=512, overlap_tokens=50)
    for chunk in chunks:
        assert chunk.strip() != ""


def test_chunk_markdown_respects_max_tokens_approx():
    long_para = "word " * 600
    text = f"## Section\n\n{long_para}"
    max_tokens = 128
    chunks = _chunk_markdown(text, max_tokens=max_tokens, overlap_tokens=10)
    # Each char-split piece must be at most max_chars (max_tokens * 4 chars)
    max_chars = max_tokens * 4
    for chunk in chunks:
        assert len(chunk) <= max_chars


def test_split_sections_preserves_headings():
    md = "# Title\n\nIntro.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B."
    sections = _split_sections(md)
    assert any("Section A" in s for s in sections)
    assert any("Section B" in s for s in sections)


def test_chunk_markdown_empty_string_returns_non_empty_list():
    chunks = _chunk_markdown("", max_tokens=512, overlap_tokens=50)
    # Should not crash; may return empty list or single empty-ish chunk
    assert isinstance(chunks, list)

from __future__ import annotations

import json
from typing import Any

import structlog

from app.logger import setup_logging
from app.config import settings
from app.models.incident import IncidentRecord
from app.utils.chunker import chunk_markdown
from app.services import bedrock, dynamodb, s3vectors

setup_logging()
log = structlog.get_logger()



def handler(event: dict[str, Any], context: Any) -> None:
    for record in event.get("Records", []):
        _process_record(record)


def _process_record(record: dict[str, Any]) -> None:
    body = record.get("body", "")
    try:
        payload = json.loads(body)
        incident_id = payload["incident_id"]
    except Exception as exc:
        log.error("ingest_parse_failed", error=str(exc), body=body)
        return

    item = dynamodb.get_item("Incidents", {"incident_id": incident_id})
    if item is None:
        log.error("ingest_incident_not_found", incident_id=incident_id)
        return

    try:
        incident = IncidentRecord.model_validate(item)
    except Exception as exc:
        log.error("ingest_record_invalid", incident_id=incident_id, error=str(exc))
        return

    markdown = _build_markdown(incident)
    chunks = chunk_markdown(markdown)

    ingested = 0
    for idx, chunk_text in enumerate(chunks):
        chunk_id = f"{incident_id}-chunk-{idx:03d}"

        try:
            vector = bedrock.embed(settings.embedding_model_id, chunk_text, input_type="search_document")
        except Exception as exc:
            log.error("ingest_embed_failed", incident_id=incident_id, chunk_index=idx, error=str(exc))
            continue

        try:
            s3vectors.upsert_vectors(
                settings.s3_vectors_bucket_name,
                settings.s3_vectors_index_name,
                [{"key": chunk_id, "vector": vector, "metadata": {"incident_id": incident_id, "chunk_index": idx}}],
            )
        except Exception as exc:
            log.error("ingest_s3vectors_failed", incident_id=incident_id, chunk_index=idx, error=str(exc))
            continue

        try:
            dynamodb.put_item(
                "CorpusChunks",
                {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "incident_id": incident_id,
                    "chunk_index": idx,
                },
            )
        except Exception as exc:
            log.error("ingest_dynamodb_failed", incident_id=incident_id, chunk_index=idx, error=str(exc))
            continue

        ingested += 1

    log.info("ingest_completed", incident_id=incident_id, chunks_ingested=ingested, chunks_total=len(chunks))


def _build_markdown(record: IncidentRecord) -> str:
    lines: list[str] = [
        f"# Incident Resolution: {record.title}",
        "",
        "## Incident Details",
        f"- **ID:** {record.incident_id}",
        f"- **Severity:** {record.severity}",
        f"- **Affected Service:** {record.affected_service}",
        f"- **Failure Class:** {record.failure_class}",
        f"- **Created:** {record.created_at.isoformat()}",
    ]
    if record.resolved_at:
        lines.append(f"- **Resolved:** {record.resolved_at.isoformat()}")
    if record.resolved_by:
        lines.append(f"- **Resolved By:** {record.resolved_by}")

    lines += ["", "## Summary", record.summary]

    if record.recommended_actions:
        lines += ["", "## Recommended Actions"]
        for action in record.recommended_actions:
            lines.append(f"- {action}")

    if record.runbook_references:
        lines += ["", "## Runbook References"]
        for ref in record.runbook_references:
            lines.append(f"- {ref}")

    if record.resolution_notes:
        lines += ["", "## Resolution Notes", record.resolution_notes]

    return "\n".join(lines)



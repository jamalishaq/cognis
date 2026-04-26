from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.models.incident import IncidentRecord
from app.utils.chunker import chunk_markdown
from app.services import bedrock, dynamodb, s3vectors

logger = logging.getLogger(__name__)



def handler(event: dict[str, Any], context: Any) -> None:
    for record in event.get("Records", []):
        _process_record(record)


def _process_record(record: dict[str, Any]) -> None:
    body = record.get("body", "")
    try:
        payload = json.loads(body)
        incident_id = payload["incident_id"]
    except Exception as exc:
        logger.error(
            "ingest: failed to parse SQS record — skipping to avoid infinite requeue: %s body=%r",
            exc,
            body,
        )
        return

    item = dynamodb.get_item("Incidents", {"incident_id": incident_id})
    if item is None:
        logger.error("ingest: incident not found in DynamoDB: %s", incident_id)
        return

    try:
        incident = IncidentRecord.model_validate(item)
    except Exception as exc:
        logger.error("ingest: failed to parse IncidentRecord for %s: %s", incident_id, exc)
        return

    markdown = _build_markdown(incident)
    chunks = chunk_markdown(markdown)

    ingested = 0
    for idx, chunk_text in enumerate(chunks):
        chunk_id = f"{incident_id}-chunk-{idx:03d}"

        try:
            vector = bedrock.embed(settings.embedding_model_id, chunk_text, input_type="search_document")
        except Exception as exc:
            logger.error("ingest: embed failed for %s chunk %d: %s", incident_id, idx, exc)
            continue

        try:
            s3vectors.upsert_vectors(
                settings.s3_vectors_bucket_name,
                settings.s3_vectors_index_name,
                [{"key": chunk_id, "vector": vector, "metadata": {"incident_id": incident_id, "chunk_index": idx}}],
            )
        except Exception as exc:
            logger.error("ingest: S3 Vectors upsert failed for %s chunk %d: %s", incident_id, idx, exc)
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
            logger.error("ingest: DynamoDB put failed for %s chunk %d: %s", incident_id, idx, exc)
            continue

        ingested += 1

    logger.info("ingest: completed for %s — %d/%d chunks ingested", incident_id, ingested, len(chunks))


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



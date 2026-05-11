from __future__ import annotations

from typing import Any

import boto3
import structlog

from app.config import settings

log = structlog.get_logger()

_client = None

_MOCK_RESULTS: list[dict[str, Any]] = [
    {"chunk_id": "chunk-001", "score": 0.95},
    {"chunk_id": "chunk-002", "score": 0.87},
    {"chunk_id": "chunk-003", "score": 0.81},
]


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("s3vectors", region_name=settings.aws_region)
    return _client


def upsert_vectors(
    vector_bucket_name: str,
    index_name: str,
    vectors: list[dict[str, Any]],
) -> None:
    if settings.s3_vectors_mock:
        log.info("s3vectors_mock_upsert_skipped", vector_count=len(vectors))
        return
    client = _get_client()
    client.put_vectors(
        vectorBucketName=vector_bucket_name,
        indexName=index_name,
        vectors=[
            {
                "key": v["key"],
                "data": {"float32": v["vector"]},
                "metadata": v.get("metadata", {}),
            }
            for v in vectors
        ],
    )


def query_vectors(
    vector_bucket_name: str,
    index_name: str,
    query_vector: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if settings.s3_vectors_mock:
        log.info("s3vectors_mock_query")
        return _MOCK_RESULTS[:top_k]

    client = _get_client()
    response = client.query_vectors(
        vectorBucketName=vector_bucket_name,
        indexName=index_name,
        queryVector={"float32": query_vector},
        topK=top_k,
    )
    return [
        {"chunk_id": match["key"], "score": match["score"]}
        for match in response.get("vectors", [])
    ]

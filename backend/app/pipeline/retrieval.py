from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from app.config import settings
from app.metrics import emit_pipeline_metric
from app.models.triage import TriageResult
from app.services import bedrock, dynamodb, s3vectors

log = structlog.get_logger()

_TOP_CANDIDATES = 20
_TOP_RESULTS = 5


@dataclass
class RetrievalResult:
    chunks: list[str]
    retrieval_context_available: bool


def _build_query(triage: TriageResult) -> str:
    return f"service:{triage.service} failure:{triage.failure_class} severity:{triage.severity}"


def _fetch_chunk_texts(chunk_ids: list[str]) -> list[str]:
    texts: list[str] = []
    for chunk_id in chunk_ids:
        item = dynamodb.get_item("CorpusChunks", {"chunk_id": chunk_id})
        if item and "text" in item:
            texts.append(item["text"])
    return texts


def run(triage: TriageResult) -> RetrievalResult:
    query = _build_query(triage)
    t0 = time.perf_counter()

    # Embed + vector search with retry; failure → full degradation
    candidates: list[dict] | None = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            query_vector = bedrock.embed(settings.embedding_model_id, query, trace_name="embed")
            candidates = s3vectors.query_vectors(
                settings.s3_vectors_bucket_name,
                settings.s3_vectors_index_name,
                query_vector,
                top_k=_TOP_CANDIDATES,
            )
            break
        except Exception as exc:
            last_exc = exc
            log.warning("retrieval_retry", stage="retrieval", attempt=attempt + 1, error=str(exc))
            if attempt < 2:
                time.sleep(2 ** attempt)

    if candidates is None:
        log.warning("retrieval_degraded", stage="retrieval",
                    retrieval_context_available=False, reason=str(last_exc))
        emit_pipeline_metric("retrieval_degraded", 1, "Count", {"environment": settings.environment})
        return RetrievalResult(chunks=[], retrieval_context_available=False)

    chunk_ids = [c["chunk_id"] for c in candidates]
    chunk_texts = _fetch_chunk_texts(chunk_ids)

    if not chunk_texts:
        log.warning("retrieval_degraded", stage="retrieval",
                    retrieval_context_available=False, reason="no chunk texts found in DynamoDB")
        emit_pipeline_metric("retrieval_degraded", 1, "Count", {"environment": settings.environment})
        return RetrievalResult(chunks=[], retrieval_context_available=False)

    # Rerank with retry; failure → degrade to unreranked top-N
    top_n = min(_TOP_RESULTS, len(chunk_texts))
    reranked: list[str] | None = None
    for attempt in range(3):
        try:
            reranked = bedrock.rerank(settings.rerank_model_id, query, chunk_texts, top_n=top_n, trace_name="rerank")
            break
        except Exception as exc:
            log.warning("rerank_retry", stage="retrieval", attempt=attempt + 1, error=str(exc))
            if attempt < 2:
                time.sleep(2 ** attempt)

    if reranked is None:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        chunks = chunk_texts[:_TOP_RESULTS]
        log.info("retrieval_completed", stage="retrieval", duration_ms=duration_ms,
                 chunks_retrieved=len(chunks), reranked=False)
        emit_pipeline_metric("retrieval_duration_ms", duration_ms, "Milliseconds", {"environment": settings.environment})
        return RetrievalResult(chunks=chunks, retrieval_context_available=True)

    duration_ms = round((time.perf_counter() - t0) * 1000)
    log.info("retrieval_completed", stage="retrieval", duration_ms=duration_ms,
             chunks_retrieved=len(reranked), reranked=True)
    emit_pipeline_metric("retrieval_duration_ms", duration_ms, "Milliseconds", {"environment": settings.environment})
    return RetrievalResult(chunks=reranked, retrieval_context_available=True)

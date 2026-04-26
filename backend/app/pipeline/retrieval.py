from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.config import settings
from app.models.triage import TriageResult
from app.services import bedrock, dynamodb, s3vectors

logger = logging.getLogger(__name__)

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

    # Embed + vector search with retry; failure → full degradation
    candidates: list[dict] | None = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            query_vector = bedrock.embed(settings.embedding_model_id, query)
            candidates = s3vectors.query_vectors(
                settings.s3_vectors_bucket_name,
                settings.s3_vectors_index_name,
                query_vector,
                top_k=_TOP_CANDIDATES,
            )
            break
        except Exception as exc:
            last_exc = exc
            logger.warning("Retrieval vector search attempt %d/3 failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2**attempt)

    if candidates is None:
        logger.error("Vector search failed after 3 attempts, degrading: %s", last_exc)
        return RetrievalResult(chunks=[], retrieval_context_available=False)

    chunk_ids = [c["chunk_id"] for c in candidates]
    chunk_texts = _fetch_chunk_texts(chunk_ids)

    if not chunk_texts:
        logger.warning("No chunk texts found in DynamoDB for retrieved chunk_ids")
        return RetrievalResult(chunks=[], retrieval_context_available=False)

    # Rerank with retry; failure → degrade to unreranked top-N
    top_n = min(_TOP_RESULTS, len(chunk_texts))
    reranked: list[str] | None = None
    for attempt in range(3):
        try:
            reranked = bedrock.rerank(settings.rerank_model_id, query, chunk_texts, top_n=top_n)
            break
        except Exception as exc:
            logger.warning("Rerank attempt %d/3 failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2**attempt)

    if reranked is None:
        logger.warning("Rerank failed after 3 attempts, returning unreranked chunks")
        return RetrievalResult(chunks=chunk_texts[:_TOP_RESULTS], retrieval_context_available=True)

    return RetrievalResult(chunks=reranked, retrieval_context_available=True)

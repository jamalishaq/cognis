from unittest.mock import MagicMock, call, patch

import pytest

from app.models.triage import TriageResult
from app.pipeline import retrieval
from app.pipeline.retrieval import RetrievalResult


def _make_triage(**kwargs) -> TriageResult:
    defaults = dict(service="payments-api", severity="high", failure_class="connection_exhaustion")
    defaults.update(kwargs)
    return TriageResult(**defaults)


_SAMPLE_CANDIDATES = [
    {"chunk_id": f"chunk-{i:03d}", "score": 1.0 - i * 0.05}
    for i in range(20)
]

_SAMPLE_TEXTS = [f"Runbook text for chunk {i}" for i in range(20)]

_SAMPLE_VECTOR = [0.1] * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dynamo_side_effect(chunk_texts: list[str]):
    """Return a DynamoDB get_item mock that maps chunk_id -> text by position."""
    def _get_item(table: str, key: dict):
        idx = int(key["chunk_id"].split("-")[1])
        if idx < len(chunk_texts):
            return {"chunk_id": key["chunk_id"], "text": chunk_texts[idx]}
        return None
    return _get_item


# ---------------------------------------------------------------------------
# Happy path — successful retrieval with reranking
# ---------------------------------------------------------------------------

@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_returns_reranked_top5(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.return_value = ["reranked-1", "reranked-2", "reranked-3", "reranked-4", "reranked-5"]

    result = retrieval.run(_make_triage())

    assert isinstance(result, RetrievalResult)
    assert result.retrieval_context_available is True
    assert result.chunks == ["reranked-1", "reranked-2", "reranked-3", "reranked-4", "reranked-5"]
    mock_sleep.assert_not_called()


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_embeds_query_with_triage_fields(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.return_value = _SAMPLE_TEXTS[:5]

    triage = _make_triage(service="auth-service", failure_class="memory_leak", severity="critical")
    retrieval.run(triage)

    embed_text: str = mock_embed.call_args.args[1]
    assert "auth-service" in embed_text
    assert "memory_leak" in embed_text
    assert "critical" in embed_text


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_queries_s3vectors_top20(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.return_value = _SAMPLE_TEXTS[:5]

    retrieval.run(_make_triage())

    _, kwargs = mock_query.call_args
    assert kwargs.get("top_k") == 20 or mock_query.call_args.args[3] == 20


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_passes_embed_vector_to_s3vectors(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.return_value = _SAMPLE_TEXTS[:5]

    retrieval.run(_make_triage())

    call_args = mock_query.call_args
    passed_vector = call_args.args[2] if len(call_args.args) >= 3 else call_args.kwargs.get("query_vector")
    assert passed_vector == _SAMPLE_VECTOR


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_fetches_chunk_texts_from_dynamodb(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = [{"chunk_id": "chunk-001", "score": 0.9}]
    mock_dynamo.return_value = {"chunk_id": "chunk-001", "text": "db-text"}
    mock_rerank.return_value = ["db-text"]

    retrieval.run(_make_triage())

    mock_dynamo.assert_called_once_with("CorpusChunks", {"chunk_id": "chunk-001"})


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_passes_top5_to_rerank(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.return_value = _SAMPLE_TEXTS[:5]

    retrieval.run(_make_triage())

    kwargs = mock_rerank.call_args.kwargs
    assert kwargs.get("top_n") == 5 or mock_rerank.call_args.args[3] == 5


# ---------------------------------------------------------------------------
# Rerank failure degradation
# ---------------------------------------------------------------------------

@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_degrades_to_unreranked_when_rerank_fails(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.side_effect = RuntimeError("rerank unavailable")

    result = retrieval.run(_make_triage())

    assert result.retrieval_context_available is True
    assert len(result.chunks) == 5
    assert mock_rerank.call_count == 3


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_rerank_degradation_sleeps_with_backoff(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.side_effect = RuntimeError("throttled")

    retrieval.run(_make_triage())

    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2**0
    mock_sleep.assert_any_call(2)  # 2**1


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_rerank_succeeds_on_third_attempt(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.side_effect = [
        RuntimeError("fail 1"),
        RuntimeError("fail 2"),
        ["r1", "r2", "r3", "r4", "r5"],
    ]

    result = retrieval.run(_make_triage())

    assert result.retrieval_context_available is True
    assert result.chunks == ["r1", "r2", "r3", "r4", "r5"]
    assert mock_rerank.call_count == 3


# ---------------------------------------------------------------------------
# Full retrieval failure degradation (S3 Vectors / embed fails)
# ---------------------------------------------------------------------------

@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_returns_empty_when_vector_search_fails(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.side_effect = RuntimeError("S3 Vectors unavailable")

    result = retrieval.run(_make_triage())

    assert result.retrieval_context_available is False
    assert result.chunks == []
    assert mock_query.call_count == 3


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_returns_empty_when_embed_fails(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.side_effect = RuntimeError("Bedrock embed unavailable")

    result = retrieval.run(_make_triage())

    assert result.retrieval_context_available is False
    assert result.chunks == []
    assert mock_embed.call_count == 3
    mock_rerank.assert_not_called()


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_vector_search_failure_sleeps_with_backoff(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.side_effect = RuntimeError("throttled")

    retrieval.run(_make_triage())

    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_vector_search_succeeds_on_retry(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.side_effect = [
        RuntimeError("fail 1"),
        _SAMPLE_CANDIDATES,
    ]
    mock_dynamo.side_effect = _dynamo_side_effect(_SAMPLE_TEXTS)
    mock_rerank.return_value = _SAMPLE_TEXTS[:5]

    result = retrieval.run(_make_triage())

    assert result.retrieval_context_available is True
    assert mock_query.call_count == 2
    assert mock_sleep.call_count == 1


@patch("time.sleep")
@patch("app.pipeline.retrieval.dynamodb.get_item")
@patch("app.pipeline.retrieval.s3vectors.query_vectors")
@patch("app.pipeline.retrieval.bedrock.rerank")
@patch("app.pipeline.retrieval.bedrock.embed")
def test_run_returns_empty_when_dynamo_returns_no_texts(mock_embed, mock_rerank, mock_query, mock_dynamo, mock_sleep):
    mock_embed.return_value = _SAMPLE_VECTOR
    mock_query.return_value = _SAMPLE_CANDIDATES
    mock_dynamo.return_value = None

    result = retrieval.run(_make_triage())

    assert result.retrieval_context_available is False
    assert result.chunks == []
    mock_rerank.assert_not_called()

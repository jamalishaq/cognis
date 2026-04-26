from unittest.mock import MagicMock, patch

import pytest

import app.services.s3vectors as s3vectors_module
from app.services.s3vectors import query_vectors


@pytest.fixture(autouse=True)
def reset_client():
    s3vectors_module._client = None
    yield
    s3vectors_module._client = None


@patch("app.services.s3vectors.settings")
def test_mock_mode_returns_hardcoded_results(mock_settings):
    mock_settings.s3_vectors_mock = True

    results = query_vectors("my-bucket", "my-index", [0.1, 0.2, 0.3])

    assert len(results) > 0
    assert all("chunk_id" in r and "score" in r for r in results)


@patch("app.services.s3vectors.settings")
def test_mock_mode_respects_top_k(mock_settings):
    mock_settings.s3_vectors_mock = True

    results = query_vectors("my-bucket", "my-index", [0.1, 0.2], top_k=2)

    assert len(results) == 2


@patch("app.services.s3vectors.settings")
def test_mock_mode_chunk_ids_are_strings(mock_settings):
    mock_settings.s3_vectors_mock = True

    results = query_vectors("my-bucket", "my-index", [0.1])

    for r in results:
        assert isinstance(r["chunk_id"], str)
        assert isinstance(r["score"], float)


@patch("app.services.s3vectors._get_client")
@patch("app.services.s3vectors.settings")
def test_real_mode_calls_boto3_client(mock_settings, mock_get_client):
    mock_settings.s3_vectors_mock = False
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.query_vectors.return_value = {
        "vectors": [
            {"key": "chunk-abc", "score": 0.92},
            {"key": "chunk-def", "score": 0.78},
        ]
    }

    results = query_vectors("my-bucket", "my-index", [0.1, 0.2, 0.3], top_k=5)

    assert results == [
        {"chunk_id": "chunk-abc", "score": 0.92},
        {"chunk_id": "chunk-def", "score": 0.78},
    ]
    mock_client.query_vectors.assert_called_once_with(
        vectorBucketName="my-bucket",
        indexName="my-index",
        queryVector={"float32": [0.1, 0.2, 0.3]},
        topK=5,
    )


@patch("app.services.s3vectors._get_client")
@patch("app.services.s3vectors.settings")
def test_real_mode_returns_empty_on_no_vectors(mock_settings, mock_get_client):
    mock_settings.s3_vectors_mock = False
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.query_vectors.return_value = {}

    results = query_vectors("my-bucket", "my-index", [0.5])

    assert results == []


@patch("app.services.s3vectors._get_client")
@patch("app.services.s3vectors.settings")
def test_real_mode_passes_correct_top_k(mock_settings, mock_get_client):
    mock_settings.s3_vectors_mock = False
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.query_vectors.return_value = {"vectors": []}

    query_vectors("bucket", "index", [0.1], top_k=10)

    _, kwargs = mock_client.query_vectors.call_args
    assert kwargs["topK"] == 10

import json
import logging
import time
from collections.abc import Generator
from typing import Any

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

_client = None
_agent_runtime_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _client


def _get_agent_runtime_client():
    global _agent_runtime_client
    if _agent_runtime_client is None:
        _agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=settings.aws_region)
    return _agent_runtime_client


def invoke_model(
    model_id: str,
    messages: list[dict[str, Any]],
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    client = _get_client()
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.converse(**kwargs)
            return response["output"]["message"]["content"][0]["text"]
        except Exception as exc:
            last_exc = exc
            logger.warning("Bedrock invoke_model attempt %d/3 failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2**attempt)

    raise last_exc  # type: ignore[misc]


def embed(model_id: str, text: str, input_type: str = "search_query") -> list[float]:
    client = _get_client()
    body = json.dumps({"texts": [text], "input_type": input_type, "embedding_types": ["float"]})
    response = client.invoke_model(modelId=model_id, body=body, contentType="application/json", accept="application/json")
    data = json.loads(response["body"].read())
    return data["embeddings"]["float"][0]


def converse_with_tools(
    model_id: str,
    messages: list[dict[str, Any]],
    system: str | None = None,
    tool_config: dict[str, Any] | None = None,
    max_tokens: int = 4096,
) -> tuple[dict[str, Any], str]:
    """Call Bedrock converse API with optional tool support.

    Returns (message_dict, stop_reason). message_dict has the shape
    {"role": "assistant", "content": [...]}, where content items may be
    {"text": "..."} or {"toolUse": {"toolUseId": ..., "name": ..., "input": ...}}.
    No retry — callers are responsible for retry logic.
    """
    client = _get_client()
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if tool_config:
        kwargs["toolConfig"] = tool_config
    response = client.converse(**kwargs)
    return response["output"]["message"], response["stopReason"]


def rerank(model_id: str, query: str, documents: list[str], top_n: int) -> list[str]:
    client = _get_agent_runtime_client()
    response = client.rerank(
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "numberOfResults": top_n,
                "modelConfiguration": {"modelArn": model_id},
            },
        },
        sources=[
            {
                "type": "INLINE",
                "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": doc}},
            }
            for doc in documents
        ],
        queries=[{"type": "TEXT", "textQuery": {"text": query}}],
    )
    results = sorted(response["rerankingResults"], key=lambda r: r["relevanceScore"], reverse=True)
    return [documents[r["index"]] for r in results[:top_n]]


def stream_text(
    model_id: str,
    messages: list[dict[str, Any]],
    system: str | None = None,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """Stream text tokens from Bedrock converse_stream. Yields text chunks as they arrive."""
    client = _get_client()
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    response = client.converse_stream(**kwargs)
    for event in response.get("stream", []):
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                yield delta["text"]

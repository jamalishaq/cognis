import json
import time
from collections.abc import Generator
from typing import Any

import boto3
import structlog
from structlog.contextvars import get_contextvars

from app.config import settings
from app.metrics import emit_bedrock_metric

log = structlog.get_logger()

_client = None
_agent_runtime_client = None
_langfuse = None


def _get_langfuse():
    global _langfuse
    if _langfuse is None:
        try:
            from langfuse import Langfuse
            _langfuse = Langfuse()
        except Exception:
            pass
    return _langfuse


def _emit_langfuse(
    trace_name: str | None,
    model_id: str,
    input_data: Any,
    output: Any,
    usage: dict,
) -> None:
    if not trace_name:
        return
    lf = _get_langfuse()
    if lf is None:
        return
    try:
        incident_id = get_contextvars().get("incident_id")
        trace = lf.trace(name=trace_name, metadata={"incident_id": incident_id})
        trace.generation(
            name=trace_name,
            model=model_id,
            input=input_data,
            output=output,
            usage={
                "input": usage.get("inputTokens", 0),
                "output": usage.get("outputTokens", 0),
            },
        )
    except Exception:
        pass


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
    trace_name: str | None = None,
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
            text = response["output"]["message"]["content"][0]["text"]
            usage = response.get("usage", {})
            _emit_langfuse(trace_name, model_id, messages, text, usage)
            dims = {"environment": settings.environment, "model_id": model_id}
            emit_bedrock_metric("bedrock_input_tokens", usage.get("inputTokens", 0), "Count", dims)
            emit_bedrock_metric("bedrock_output_tokens", usage.get("outputTokens", 0), "Count", dims)
            return text
        except Exception as exc:
            last_exc = exc
            log.warning("bedrock_invoke_retry", attempt=attempt + 1, error=str(exc))
            if attempt < 2:
                time.sleep(2**attempt)

    raise last_exc


def embed(
    model_id: str,
    text: str,
    input_type: str = "search_query",
    trace_name: str | None = None,
) -> list[float]:
    client = _get_client()
    body = json.dumps({"texts": [text], "input_type": input_type, "embedding_types": ["float"]})
    response = client.invoke_model(modelId=model_id, body=body, contentType="application/json", accept="application/json")
    data = json.loads(response["body"].read())
    vector = data["embeddings"]["float"][0]
    _emit_langfuse(trace_name, model_id, {"text": text, "input_type": input_type}, f"vector[{len(vector)}]", {})
    return vector


def converse_with_tools(
    model_id: str,
    messages: list[dict[str, Any]],
    system: str | None = None,
    tool_config: dict[str, Any] | None = None,
    max_tokens: int = 4096,
    trace_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    # No internal retry — callers handle retry logic.
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
    message = response["output"]["message"]
    usage = response.get("usage", {})
    _emit_langfuse(trace_name, model_id, messages, message.get("content"), usage)
    dims = {"environment": settings.environment, "model_id": model_id}
    emit_bedrock_metric("bedrock_input_tokens", usage.get("inputTokens", 0), "Count", dims)
    emit_bedrock_metric("bedrock_output_tokens", usage.get("outputTokens", 0), "Count", dims)
    return message, response["stopReason"]


def rerank(
    model_id: str,
    query: str,
    documents: list[str],
    top_n: int,
    trace_name: str | None = None,
) -> list[str]:
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
    reranked = [documents[r["index"]] for r in results[:top_n]]
    _emit_langfuse(trace_name, model_id, {"query": query, "documents_count": len(documents)}, f"reranked[{len(reranked)}]", {})
    return reranked


def stream_text(
    model_id: str,
    messages: list[dict[str, Any]],
    system: str | None = None,
    max_tokens: int = 4096,
    trace_name: str | None = None,
) -> Generator[str, None, None]:
    client = _get_client()
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    # Emit Langfuse trace at stream start; output unavailable until stream completes.
    _emit_langfuse(trace_name, model_id, messages, None, {})
    response = client.converse_stream(**kwargs)
    for event in response.get("stream", []):
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                yield delta["text"]

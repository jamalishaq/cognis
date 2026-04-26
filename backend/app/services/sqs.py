from __future__ import annotations

import json
import logging
from typing import Any

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.sqs_endpoint:
            kwargs["endpoint_url"] = settings.sqs_endpoint
        _client = boto3.client("sqs", **kwargs)
    return _client


def send_message(queue_url: str, body: dict[str, Any]) -> str:
    client = _get_client()
    response = client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(body),
    )
    return response["MessageId"]

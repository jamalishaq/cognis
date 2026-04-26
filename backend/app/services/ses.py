from __future__ import annotations

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
        _client = boto3.client("ses", **kwargs)
    return _client


def send_email(
    to_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: str,
) -> str:
    client = _get_client()
    response = client.send_email(
        Source=settings.ses_from_email,
        Destination={"ToAddresses": to_addresses},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
                "Html": {"Data": body_html, "Charset": "UTF-8"},
            },
        },
    )
    return response["MessageId"]

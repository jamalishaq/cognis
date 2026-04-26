from __future__ import annotations

import logging
from typing import Any

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

_resource = None


def _get_resource():
    global _resource
    if _resource is None:
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
        _resource = boto3.resource("dynamodb", **kwargs)
    return _resource


def get_item(table_name: str, key: dict[str, Any]) -> dict[str, Any] | None:
    table = _get_resource().Table(table_name)
    response = table.get_item(Key=key)
    return response.get("Item")


def put_item(table_name: str, item: dict[str, Any]) -> None:
    table = _get_resource().Table(table_name)
    table.put_item(Item=item)


def update_item(
    table_name: str,
    key: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    table = _get_resource().Table(table_name)
    expr_parts: list[str] = []
    attr_names: dict[str, str] = {}
    attr_values: dict[str, Any] = {}
    for i, (field, value) in enumerate(updates.items()):
        name_ph = f"#f{i}"
        val_ph = f":v{i}"
        expr_parts.append(f"{name_ph} = {val_ph}")
        attr_names[name_ph] = field
        attr_values[val_ph] = value

    response = table.update_item(
        Key=key,
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def scan(
    table_name: str,
    filter_expression: Any = None,
    expression_attribute_names: dict[str, str] | None = None,
    expression_attribute_values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    table = _get_resource().Table(table_name)
    kwargs: dict[str, Any] = {}
    if filter_expression is not None:
        kwargs["FilterExpression"] = filter_expression
    if expression_attribute_names:
        kwargs["ExpressionAttributeNames"] = expression_attribute_names
    if expression_attribute_values:
        kwargs["ExpressionAttributeValues"] = expression_attribute_values
    response = table.scan(**kwargs)
    return response.get("Items", [])


def increment_counter(counter_id: str) -> int:
    table = _get_resource().Table("Counters")
    response = table.update_item(
        Key={"counter_id": counter_id},
        UpdateExpression="ADD #val :inc",
        ExpressionAttributeNames={"#val": "value"},
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(response["Attributes"]["value"])


def query(
    table_name: str,
    key_condition: Any,
    index_name: str | None = None,
    scan_index_forward: bool = True,
) -> list[dict[str, Any]]:
    table = _get_resource().Table(table_name)
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
    }
    if index_name:
        kwargs["IndexName"] = index_name
    response = table.query(**kwargs)
    return response.get("Items", [])

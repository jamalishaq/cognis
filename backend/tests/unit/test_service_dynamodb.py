from unittest.mock import MagicMock, patch

import pytest
from boto3.dynamodb.conditions import Key

import app.services.dynamodb as dynamodb_module
from app.services.dynamodb import get_item, put_item, query, update_item


@pytest.fixture(autouse=True)
def reset_resource():
    dynamodb_module._resource = None
    yield
    dynamodb_module._resource = None


def _make_mock_resource():
    mock_resource = MagicMock()
    mock_table = MagicMock()
    mock_resource.Table.return_value = mock_table
    return mock_resource, mock_table


@patch("app.services.dynamodb._get_resource")
def test_get_item_returns_item(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    item = {"incident_id": "INC-20240101-001", "title": "DB down"}
    mock_table.get_item.return_value = {"Item": item}

    result = get_item("Incidents", {"incident_id": "INC-20240101-001"})

    assert result == item
    mock_resource.Table.assert_called_once_with("Incidents")
    mock_table.get_item.assert_called_once_with(Key={"incident_id": "INC-20240101-001"})


@patch("app.services.dynamodb._get_resource")
def test_get_item_returns_none_when_missing(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.get_item.return_value = {}

    result = get_item("Incidents", {"incident_id": "INC-20240101-001"})

    assert result is None


@patch("app.services.dynamodb._get_resource")
def test_put_item_calls_table(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    item = {"incident_id": "INC-20240101-001", "title": "Outage"}

    put_item("Incidents", item)

    mock_resource.Table.assert_called_once_with("Incidents")
    mock_table.put_item.assert_called_once_with(Item=item)


@patch("app.services.dynamodb._get_resource")
def test_put_item_returns_none(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.put_item.return_value = {}

    result = put_item("Incidents", {"incident_id": "INC-20240101-001"})

    assert result is None


@patch("app.services.dynamodb._get_resource")
def test_update_item_builds_set_expression(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    updated = {"incident_id": "INC-20240101-001", "status": "resolved"}
    mock_table.update_item.return_value = {"Attributes": updated}

    result = update_item(
        "Incidents",
        {"incident_id": "INC-20240101-001"},
        {"status": "resolved"},
    )

    assert result == updated
    _, kwargs = mock_table.update_item.call_args
    assert kwargs["UpdateExpression"] == "SET #f0 = :v0"
    assert kwargs["ExpressionAttributeNames"] == {"#f0": "status"}
    assert kwargs["ExpressionAttributeValues"] == {":v0": "resolved"}
    assert kwargs["ReturnValues"] == "ALL_NEW"


@patch("app.services.dynamodb._get_resource")
def test_update_item_multiple_fields(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.update_item.return_value = {"Attributes": {}}

    update_item(
        "Incidents",
        {"incident_id": "INC-20240101-001"},
        {"status": "resolved", "resolved_at": "2024-01-01T00:00:00"},
    )

    _, kwargs = mock_table.update_item.call_args
    assert "#f0" in kwargs["ExpressionAttributeNames"]
    assert "#f1" in kwargs["ExpressionAttributeNames"]
    assert "SET" in kwargs["UpdateExpression"]


@patch("app.services.dynamodb._get_resource")
def test_update_item_returns_empty_dict_when_no_attributes(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.update_item.return_value = {}

    result = update_item("Incidents", {"incident_id": "INC-20240101-001"}, {"status": "resolved"})

    assert result == {}


@patch("app.services.dynamodb._get_resource")
def test_query_returns_items(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    items = [
        {"incident_id": "INC-20240101-001", "message_id": "MSG-001"},
        {"incident_id": "INC-20240101-001", "message_id": "MSG-002"},
    ]
    mock_table.query.return_value = {"Items": items}

    condition = Key("incident_id").eq("INC-20240101-001")
    result = query("ChatMessages", condition)

    assert result == items
    mock_resource.Table.assert_called_once_with("ChatMessages")


@patch("app.services.dynamodb._get_resource")
def test_query_returns_empty_list_when_no_items(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.query.return_value = {}

    result = query("ChatMessages", Key("incident_id").eq("INC-20240101-001"))

    assert result == []


@patch("app.services.dynamodb._get_resource")
def test_query_passes_index_name(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.query.return_value = {"Items": []}

    query("Incidents", Key("status").eq("open"), index_name="status-index")

    _, kwargs = mock_table.query.call_args
    assert kwargs["IndexName"] == "status-index"


@patch("app.services.dynamodb._get_resource")
def test_query_scan_index_forward_default_true(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.query.return_value = {"Items": []}

    query("ChatMessages", Key("incident_id").eq("INC-20240101-001"))

    _, kwargs = mock_table.query.call_args
    assert kwargs["ScanIndexForward"] is True


@patch("app.services.dynamodb._get_resource")
def test_query_scan_index_forward_false(mock_get_resource):
    mock_resource, mock_table = _make_mock_resource()
    mock_get_resource.return_value = mock_resource
    mock_table.query.return_value = {"Items": []}

    query("ChatMessages", Key("incident_id").eq("INC-20240101-001"), scan_index_forward=False)

    _, kwargs = mock_table.query.call_args
    assert kwargs["ScanIndexForward"] is False

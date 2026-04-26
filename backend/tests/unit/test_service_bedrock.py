from unittest.mock import MagicMock, call, patch

import pytest

import app.services.bedrock as bedrock_module
from app.services.bedrock import invoke_model


@pytest.fixture(autouse=True)
def reset_client():
    bedrock_module._client = None
    yield
    bedrock_module._client = None


def _make_converse_response(text: str) -> dict:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 20},
    }


@patch("app.services.bedrock._get_client")
def test_invoke_model_returns_text(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.converse.return_value = _make_converse_response("Hello!")

    result = invoke_model("anthropic.claude-sonnet-4-6", [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}])

    assert result == "Hello!"
    mock_client.converse.assert_called_once()


@patch("app.services.bedrock._get_client")
def test_invoke_model_passes_system_prompt(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.converse.return_value = _make_converse_response("response")

    invoke_model(
        "anthropic.claude-sonnet-4-6",
        [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}],
        system="You are an assistant.",
    )

    _, kwargs = mock_client.converse.call_args
    assert kwargs.get("system") == [{"text": "You are an assistant."}]


@patch("app.services.bedrock._get_client")
def test_invoke_model_omits_system_when_none(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.converse.return_value = _make_converse_response("response")

    invoke_model("anthropic.claude-sonnet-4-6", [])

    _, kwargs = mock_client.converse.call_args
    assert "system" not in kwargs


@patch("app.services.bedrock._get_client")
def test_invoke_model_passes_max_tokens(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.converse.return_value = _make_converse_response("ok")

    invoke_model("anthropic.claude-sonnet-4-6", [], max_tokens=1024)

    _, kwargs = mock_client.converse.call_args
    assert kwargs["inferenceConfig"]["maxTokens"] == 1024


@patch("time.sleep")
@patch("app.services.bedrock._get_client")
def test_invoke_model_retries_on_failure(mock_get_client, mock_sleep):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.converse.side_effect = [
        RuntimeError("throttled"),
        RuntimeError("throttled"),
        _make_converse_response("success"),
    ]

    result = invoke_model("anthropic.claude-sonnet-4-6", [])

    assert result == "success"
    assert mock_client.converse.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2**1
    mock_sleep.assert_any_call(2)  # 2**... wait: attempt 0 sleeps 2**0=1, attempt 1 sleeps 2**1=2


@patch("time.sleep")
@patch("app.services.bedrock._get_client")
def test_invoke_model_raises_after_three_failures(mock_get_client, mock_sleep):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    exc = RuntimeError("service unavailable")
    mock_client.converse.side_effect = exc

    with pytest.raises(RuntimeError, match="service unavailable"):
        invoke_model("anthropic.claude-sonnet-4-6", [])

    assert mock_client.converse.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep")
@patch("app.services.bedrock._get_client")
def test_invoke_model_no_sleep_on_last_attempt(mock_get_client, mock_sleep):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.converse.side_effect = RuntimeError("err")

    with pytest.raises(RuntimeError):
        invoke_model("anthropic.claude-sonnet-4-6", [])

    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_args == [1, 2]  # sleeps after attempt 0 and 1, not after attempt 2

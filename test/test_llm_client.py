import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cfmb.llm_client import LLMClient


@pytest.fixture
def mock_async_client():
    mock_client = AsyncMock()
    with patch("cfmb.llm_client.ollama.AsyncClient", return_value=mock_client):
        yield mock_client


def test_llm_client_initialization():
    model_name = "my_model"
    client = LLMClient(model_name)
    assert client.model_name == model_name


@pytest.mark.asyncio
async def test_get_completion_success(mock_async_client):
    model_name = "test_model"
    messages = [{"role": "user", "content": "Hello"}]
    expected_response = "Hi there!"

    mock_async_client.chat.return_value = {
        "message": {"content": expected_response, "role": "assistant"}
    }

    client = LLMClient(model_name)
    actual_response = await client.get_completion(messages)

    assert actual_response == expected_response
    mock_async_client.chat.assert_called_once_with(model=model_name, messages=messages)


@pytest.mark.asyncio
async def test_get_completion_exception(mock_async_client):
    model_name = "error_model"
    messages = [{"role": "user", "content": "Cause an error"}]

    mock_async_client.chat.side_effect = Exception("Something went wrong")

    client = LLMClient(model_name)
    with patch("builtins.print") as mock_print:
        response = await client.get_completion(messages)
    assert response is None
    mock_async_client.chat.assert_called_once_with(model=model_name, messages=messages)
    mock_print.assert_called_once_with("LLM error: Something went wrong")


@pytest.mark.asyncio
async def test_get_completion_empty_message(mock_async_client):
    model_name = "test_model"
    messages = []
    expected_response = "Response to empty message"

    mock_async_client.chat.return_value = {
        "message": {"content": expected_response, "role": "assistant"}
    }

    client = LLMClient(model_name)
    actual_response = await client.get_completion(messages)
    assert actual_response == expected_response
    mock_async_client.chat.assert_called_once_with(model=model_name, messages=messages)


@pytest.mark.asyncio
async def test_get_completion_different_message_types(mock_async_client):
    model_name = "test_model"
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ]
    expected_response = "I'm doing well, thank you!"

    mock_async_client.chat.return_value = {
        "message": {"content": expected_response, "role": "assistant"}
    }

    client = LLMClient(model_name)
    actual_response = await client.get_completion(messages)

    assert actual_response == expected_response
    mock_async_client.chat.assert_called_once_with(model=model_name, messages=messages)


@pytest.mark.asyncio
async def test_get_completion_with_ollama_returning_none(mock_async_client):
    model_name = "test_model"
    messages = [{"role": "user", "content": "Hello"}]
    mock_async_client.chat.return_value = None

    client = LLMClient(model_name)
    with patch("builtins.print") as mock_print:
        response = await client.get_completion(messages)

    assert response is None
    mock_async_client.chat.assert_called_once_with(model=model_name, messages=messages)
    mock_print.assert_called_once()
    assert "LLM error" in mock_print.call_args[0][0]


@pytest.mark.asyncio
async def test_get_completion_with_unexpected_response_structure(mock_async_client):
    model_name = "test_model"
    messages = [{"role": "user", "content": "Hello"}]
    mock_async_client.chat.return_value = {"unexpected_key": "unexpected_value"}

    client = LLMClient(model_name)
    with patch("builtins.print") as mock_print:
        response = await client.get_completion(messages)

    assert response is None
    mock_async_client.chat.assert_called_once_with(model=model_name, messages=messages)
    assert mock_print.call_count == 1
    assert "LLM error" in mock_print.call_args[0][0]

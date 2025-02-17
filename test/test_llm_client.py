import pytest
from unittest.mock import patch
from cfmb.llm_client import LLMClient


@pytest.fixture
def mock_ollama_chat():
    with patch("cfmb.llm_client.ollama.chat") as mock_chat:
        yield mock_chat


def test_llm_client_initialization():
    model_name = "my_model"
    client = LLMClient(model_name)
    assert client.model_name == model_name


def test_get_completion_success(mock_ollama_chat):
    model_name = "test_model"
    messages = [{"role": "user", "content": "Hello"}]
    expected_response = "Hi there!"

    mock_ollama_chat.return_value = {
        "message": {"content": expected_response, "role": "assistant"}
    }

    client = LLMClient(model_name)
    actual_response = client.get_completion(messages)

    assert actual_response == expected_response
    mock_ollama_chat.assert_called_once_with(model=model_name, messages=messages)


def test_get_completion_exception(mock_ollama_chat):
    model_name = "error_model"
    messages = [{"role": "user", "content": "Cause an error"}]

    mock_ollama_chat.side_effect = Exception("Something went wrong")

    client = LLMClient(model_name)
    with patch("builtins.print") as mock_print:
        response = client.get_completion(messages)
    assert response is None  # Expecting None return on exception
    mock_ollama_chat.assert_called_once_with(model=model_name, messages=messages)
    mock_print.assert_called_once_with("LLM error: Something went wrong")


def test_get_completion_empty_message():
    model_name = "test_model"
    messages = []
    expected_response = "Response to empty message"

    client = LLMClient(model_name)

    with patch("cfmb.llm_client.ollama.chat") as mock_chat:
        mock_chat.return_value = {
            "message": {"content": expected_response, "role": "assistant"}
        }
        actual_response = client.get_completion(messages)
        assert actual_response == expected_response
        mock_chat.assert_called_once_with(model=model_name, messages=messages)


def test_get_completion_different_message_types(mock_ollama_chat):
    model_name = "test_model"
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ]
    expected_response = "I'm doing well, thank you!"

    mock_ollama_chat.return_value = {
        "message": {"content": expected_response, "role": "assistant"}
    }

    client = LLMClient(model_name)
    actual_response = client.get_completion(messages)

    assert actual_response == expected_response
    mock_ollama_chat.assert_called_once_with(model=model_name, messages=messages)


def test_get_completion_with_ollama_returning_none(mock_ollama_chat):
    model_name = "test_model"
    messages = [{"role": "user", "content": "Hello"}]
    mock_ollama_chat.return_value = None

    client = LLMClient(model_name)
    with patch("builtins.print") as mock_print:
        response = client.get_completion(messages)

    assert response is None
    mock_ollama_chat.assert_called_once_with(model=model_name, messages=messages)
    mock_print.assert_called_once()
    assert "LLM error" in mock_print.call_args[0][0]


def test_get_completion_with_unexpected_response_structure(mock_ollama_chat):
    model_name = "test_model"
    messages = [{"role": "user", "content": "Hello"}]
    mock_ollama_chat.return_value = {"unexpected_key": "unexpected_value"}

    client = LLMClient(model_name)
    with patch("builtins.print") as mock_print:
        response = client.get_completion(messages)

    assert response is None
    mock_ollama_chat.assert_called_once_with(model=model_name, messages=messages)
    assert mock_print.call_count == 1
    assert "LLM error" in mock_print.call_args[0][0]

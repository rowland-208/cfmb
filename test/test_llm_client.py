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

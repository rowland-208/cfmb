import pytest

from cfmb.llm_client import LLMClient


@pytest.fixture
def llm():
    return LLMClient(
        openrouter_model="test/model",
        openrouter_api_key="sk-or-test",
        ollama_model="test-ollama",
    )


@pytest.mark.asyncio
async def test_openrouter_success_skips_ollama(llm, mocker):
    or_call = mocker.patch.object(llm, "_openrouter", return_value="from openrouter")
    ol_call = mocker.patch.object(llm, "_ollama", return_value="from ollama")
    result = await llm.get_completion([{"role": "user", "content": "hi"}])
    assert result == "from openrouter"
    or_call.assert_awaited_once()
    ol_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_openrouter_failure_falls_back_to_ollama(llm, mocker):
    mocker.patch.object(llm, "_openrouter", side_effect=RuntimeError("401 unauth"))
    ol_call = mocker.patch.object(llm, "_ollama", return_value="from ollama")
    result = await llm.get_completion([{"role": "user", "content": "hi"}])
    assert result == "from ollama"
    ol_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_both_backends_fail_returns_none(llm, mocker):
    mocker.patch.object(llm, "_openrouter", side_effect=RuntimeError("openrouter dead"))
    mocker.patch.object(llm, "_ollama", side_effect=RuntimeError("ollama dead too"))
    result = await llm.get_completion([{"role": "user", "content": "hi"}])
    assert result is None

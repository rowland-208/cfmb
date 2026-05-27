import sys
import traceback

import httpx
import ollama

from cfmb.config import config as _config


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _ollama_options() -> dict:
    return {
        "temperature": _config.LLM_TEMPERATURE,
        "top_p": _config.LLM_TOP_P,
        "top_k": _config.LLM_TOP_K,
        "min_p": _config.LLM_MIN_P,
        "presence_penalty": _config.LLM_PRESENCE_PENALTY,
        "repeat_penalty": _config.LLM_REPEAT_PENALTY,
        "num_ctx": _config.LLM_NUM_CTX,
    }


class LLMClient:
    """Calls OpenRouter first; falls back to local Ollama on any error.

    Both backends use the OpenAI-compatible chat-messages format, so the
    `messages` list is portable. No tools, no streaming, no embeddings — one
    completion per call.
    """

    def __init__(self, openrouter_model: str, openrouter_api_key: str, ollama_model: str):
        self.openrouter_model = openrouter_model
        self.openrouter_api_key = openrouter_api_key
        self.ollama_model = ollama_model
        self.async_ollama = ollama.AsyncClient()

    async def get_completion(self, messages: list[dict]) -> str | None:
        try:
            return await self._openrouter(messages)
        except Exception as e:
            print(f"OpenRouter failed ({e}); falling back to Ollama", file=sys.stderr)
        try:
            return await self._ollama(messages)
        except Exception as e:
            print(f"Ollama also failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return None

    async def _openrouter(self, messages: list[dict]) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            resp = await client.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.openrouter_model, "messages": messages},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _ollama(self, messages: list[dict]) -> str:
        response = await self.async_ollama.chat(
            model=self.ollama_model,
            messages=messages,
            options=_ollama_options(),
        )
        return response["message"]["content"]

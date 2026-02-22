import asyncio
import base64

import ollama
import requests


class LLMClient:
    def __init__(self, model_name):
        self.model_name = model_name
        self.async_client = ollama.AsyncClient()

    async def generate_image(self, prompt: str, image_model: str) -> bytes | None:
        """Generates an image via Ollama's image generation API and returns raw PNG bytes."""
        def _sync_generate():
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": image_model, "prompt": prompt, "stream": False},
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("image")

        try:
            loop = asyncio.get_event_loop()
            b64_image = await loop.run_in_executor(None, _sync_generate)
            if b64_image:
                return base64.b64decode(b64_image)
            return None
        except Exception as e:
            print(f"Image generation error: {e}")
            return None

    async def get_completion(self, messages):
        """Sends messages to the LLM and returns the response."""
        try:
            response = await self.async_client.chat(
                model=self.model_name,
                messages=messages,
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"LLM error: {e}")
            return None

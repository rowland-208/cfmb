import ollama


class LLMClient:
    def __init__(self, model_name):
        self.model_name = model_name

    def get_completion(self, messages):
        """Sends messages to the LLM and returns the response."""
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"LLM error: {e}")
            return None

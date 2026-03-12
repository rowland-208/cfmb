from abc import ABC, abstractmethod


class Tool(ABC):
    """Base class for all LLM-callable tools."""

    name: str
    description: str
    parameters: dict

    def enabled(self) -> bool:
        """Override to conditionally disable a tool based on config, etc."""
        return True

    @abstractmethod
    async def run(self, args: dict, context: dict) -> str:
        """Execute the tool and return a string result.

        context contains runtime state: server_id, id_to_name, etc.
        """
        ...

    def schema(self) -> dict:
        """Returns the Ollama function-calling schema dict."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

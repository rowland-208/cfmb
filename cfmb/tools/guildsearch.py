import re

from cfmb.tools.base import Tool
from cfmb.config import config


def _resolve_mentions(text, id_to_name):
    """Replaces <@USER_ID> and <@!USER_ID> patterns with @username where known."""
    def replace(match):
        uid = match.group(1)
        return f"@{id_to_name[uid]}" if uid in id_to_name else match.group(0)
    return re.sub(r"<@!?(\d+)>", replace, text)


class GuildSearchTool(Tool):
    name = "guildsearch"
    description = "Search CFMG discord server messages from the past month."
    parameters = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query text",
            },
        },
    }

    def enabled(self) -> bool:
        return bool(config.OLLAMA_EMBEDDING_MODEL)

    async def run(self, args: dict, context: dict) -> str:
        query = args.get("query", "")
        server_id = context["server_id"]
        id_to_name = context["id_to_name"]
        llm_client = context["llm_client"]
        db_manager = context["db_manager"]

        embedding = await llm_client.get_embedding(query, config.OLLAMA_EMBEDDING_MODEL)
        if not embedding:
            return "Failed to generate embedding for search query."
        excluded = set(config.DEV_EXCLUDED_CHANNELS.split(",")) if config.DEV_EXCLUDED_CHANNELS else None
        chunks = db_manager.search_rag_chunks(server_id, embedding, limit=3, hours=720, exclude_channels=excluded)
        if not chunks:
            return "No matching conversations found."
        results = []
        for r in chunks:
            content = _resolve_mentions(r['content'], id_to_name)
            results.append(f"[#{r['channel_name'] or 'unknown'}]\n{content}")
        return "\n---\n".join(results)

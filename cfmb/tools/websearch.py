import aiohttp

from cfmb.tools.base import Tool
from cfmb.config import config


class WebSearchTool(Tool):
    name = "websearch"
    description = "Search the web."
    parameters = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "The web search query",
            },
        },
    }

    async def run(self, args: dict, context: dict) -> str:
        query = args.get("query", "")
        if not query:
            return "No query provided."

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
        }
        params = {"q": query, "count": 5}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return f"Search failed (HTTP {resp.status})."
                data = await resp.json()

        results = data.get("web", {}).get("results", [])
        if not results:
            return "No results found."

        formatted = []
        for r in results:
            title = r.get("title", "")
            link = r.get("url", "")
            desc = r.get("description", "")
            formatted.append(f"**{title}**\n{link}\n{desc}")
        return "\n---\n".join(formatted)

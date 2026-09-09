"""Web search tools (SPEC §4)."""

from __future__ import annotations

from typing import Any

from ..environments.web_search import SearchIndex


def search_web(index: SearchIndex, query: str) -> list[dict[str, Any]]:
    """Search the web; returns url/title/snippet per hit. Logged in `queries_log`."""
    return [
        {"url": page.url, "title": page.title, "snippet": page.snippet()}
        for page in index.search(query)
    ]


def fetch_page(index: SearchIndex, url: str) -> str:
    """Fetch the full text of a page by url."""
    page = index.fetch(url)
    if page is None:
        return f"Error: could not fetch {url!r}. No such page."
    return f"{page.title}\n\n{page.content}"


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web and return the top matching pages with a short "
                "snippet of each. Use fetch_page to read a result in full."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch the full text content of a web page by its url.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full url of the page to fetch.",
                    }
                },
                "required": ["url"],
            },
        },
    },
]

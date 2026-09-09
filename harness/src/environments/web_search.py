"""Web search environment state (SPEC §3.3).

State and mutation only. Ranking is a deterministic token-overlap count with
fixture order as the tie-break -- no randomness, no live network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# How much of a page `search_web` shows. Long enough that a payload placed at
# the head of a page is visible in results (that is what makes the `easy`
# web-search variant easy), short enough that reaching the rest of the page
# still requires a `fetch_page` call.
SNIPPET_CHARS = 320

MAX_RESULTS = 5


@dataclass
class Page:
    """One indexed page."""

    url: str
    title: str
    content: str

    def snippet(self, limit: int = SNIPPET_CHARS) -> str:
        """Leading extract of the page content, as search results show it."""
        text = self.content.strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."


@dataclass
class Query:
    """One `search_web` call."""

    query: str
    n_results: int


@dataclass
class SearchIndex:
    """Mutable search state."""

    pages: list[Page] = field(default_factory=list)
    queries_log: list[Query] = field(default_factory=list)

    @classmethod
    def from_fixture(cls, path: str | Path) -> "SearchIndex":
        """Build a fresh index from a seed file (SPEC §3, determinism).

        Fixture order is the deterministic relevance order and is preserved
        exactly; `search` only ever reorders by score, never arbitrarily.
        """
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        pages = [
            Page(url=rec["url"], title=rec["title"], content=rec["content"])
            for rec in data["pages"]
        ]
        return cls(pages=pages)

    def add_page(self, page: Page, position: int | None = None) -> None:
        """Insert a page, optionally at a fixed rank position."""
        if position is None:
            self.pages.append(page)
        else:
            self.pages.insert(position, page)

    def get_page(self, url: str) -> Page | None:
        """The page at this url, or None."""
        for page in self.pages:
            if page.url == url:
                return page
        return None

    def search(self, query: str, max_results: int = MAX_RESULTS) -> list[Page]:
        """Pages matching `query`, best first. Logs the call.

        Score is the number of distinct query tokens present in the page's title
        plus content, with a title match counted twice. Ties keep fixture order.
        Pages scoring zero are excluded; if nothing matches, the result is empty
        rather than a silent fallback to unrelated pages.
        """
        tokens = _tokens(query)
        scored: list[tuple[int, int, Page]] = []
        for index, page in enumerate(self.pages):
            if not tokens:
                break
            title_tokens = _tokens(page.title)
            body_tokens = _tokens(page.content)
            score = 2 * len(tokens & title_tokens) + len(tokens & body_tokens)
            if score > 0:
                scored.append((-score, index, page))
        scored.sort()
        hits = [page for _, _, page in scored[:max_results]]
        self.queries_log.append(Query(query=query, n_results=len(hits)))
        return hits

    def fetch(self, url: str) -> Page | None:
        """The full page at this url, or None."""
        return self.get_page(url)


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens of 3+ chars, used for scoring only."""
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 3}

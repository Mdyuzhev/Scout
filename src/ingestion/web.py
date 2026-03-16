"""Web data collector — httpx + BeautifulSoup4 + DuckDuckGo HTML search."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.config import DepthLevel, Document, ResearchConfig, SourceType

from .base import BaseCollector

_DEPTH_PAGES: dict[DepthLevel, int] = {
    DepthLevel.QUICK: 15,
    DepthLevel.NORMAL: 40,
    DepthLevel.DEEP: 100,
}

_REMOVE_TAGS = {"nav", "footer", "header", "script", "style", "aside", "noscript"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

_REQUEST_TIMEOUT = 10.0


class WebCollector(BaseCollector):
    """Collect documents from web: DuckDuckGo search or specific URLs."""

    async def collect(self, config: ResearchConfig) -> list[Document]:
        if config.source_type == SourceType.SPECIFIC_URLS:
            urls = list(config.source_urls)
        else:
            urls = await self._search_urls(config)

        documents: list[Document] = []
        seen_hashes: set[str] = set()

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            for url in urls:
                doc = await self._fetch_page(client, url)
                if doc is None:
                    continue
                if doc.content_hash in seen_hashes:
                    logger.debug("Duplicate skipped: {}", url)
                    continue
                seen_hashes.add(doc.content_hash)
                documents.append(doc)

        logger.info("Collected {} documents for topic '{}'", len(documents), config.topic)
        return documents

    # ------------------------------------------------------------------
    # DuckDuckGo HTML search
    # ------------------------------------------------------------------

    async def _search_urls(self, config: ResearchConfig) -> list[str]:
        max_pages = _DEPTH_PAGES[config.depth]

        queries = list(config.queries) if config.queries else []
        if not queries:
            queries.append(config.topic)

        urls: list[str] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            for query in queries:
                if len(urls) >= max_pages:
                    break
                found = await self._ddg_search(client, query, config.language)
                for u in found:
                    if u not in seen and len(urls) < max_pages:
                        seen.add(u)
                        urls.append(u)

        logger.info("Search yielded {} URLs from {} queries", len(urls), len(queries))
        return urls

    async def _ddg_search(
        self, client: httpx.AsyncClient, query: str, language: str
    ) -> list[str]:
        """Fetch search result URLs from DuckDuckGo HTML interface."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl={language}-{language}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("DuckDuckGo search failed for '{}': {}", query, exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[str] = []
        for link in soup.select("a.result__a"):
            href = str(link.get("href", ""))
            real = self._extract_ddg_url(href)
            if real:
                results.append(real)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for r in results:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique

    @staticmethod
    def _extract_ddg_url(href: str) -> str | None:
        """Extract real URL from DuckDuckGo redirect wrapper."""
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        # DDG wraps results as /l/?uddg=<encoded_url>
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return uddg[0]
        if href.startswith("http") and "duckduckgo.com" not in href:
            return href
        return None

    # ------------------------------------------------------------------
    # Page fetching & cleaning
    # ------------------------------------------------------------------

    async def _fetch_page(
        self, client: httpx.AsyncClient, url: str
    ) -> Document | None:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch {}: {}", url, exc)
            return None

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            logger.debug("Skipping non-HTML content at {}", url)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else url

        # Remove noise tags
        for tag in soup.find_all(_REMOVE_TAGS):
            tag.decompose()

        # Extract main content
        main = soup.find("main") or soup.find("article") or soup.body
        if main is None:
            return None

        text = main.get_text(separator="\n", strip=True)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if len(text) < 50:
            logger.debug("Too little content at {}, skipping", url)
            return None

        content_hash = hashlib.sha256(text[:1000].encode()).hexdigest()

        return Document(
            url=url,
            title=title,
            content=text,
            content_hash=content_hash,
        )

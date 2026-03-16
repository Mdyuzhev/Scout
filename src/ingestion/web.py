"""Web data collector — httpx + BeautifulSoup4 + DuckDuckGo HTML search."""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import re
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.config import DepthLevel, Document, ResearchConfig, SourceType

from .base import BaseCollector
from .playwright_fetcher import PlaywrightFetcher

_DEPTH_PAGES: dict[DepthLevel, int] = {
    DepthLevel.QUICK: 15,
    DepthLevel.NORMAL: 40,
    DepthLevel.DEEP: 100,
}

_REMOVE_TAGS = {"nav", "footer", "header", "script", "style", "aside", "noscript"}

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# Домены с агрессивной bot-protection — пропускать без попытки
_BLOCKED_DOMAINS: frozenset[str] = frozenset([
    "g2.com",
    "capterra.com",
    "softwareadvice.com",
    "getapp.com",
    "trustradius.com",
    "gartner.com",
    "github.com",
    "medium.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "stackoverflow.com",
    "reddit.com",
    "quora.com",
    "ycombinator.com",
    "slashdot.org",
    "peerspot.com",
    "stackshare.io",
])

_REQUEST_TIMEOUT = 10.0
_MAX_CONCURRENT = 10

_PLAYWRIGHT_ENABLED = os.getenv("PLAYWRIGHT_ENABLED", "true").lower() == "true"

# Признаки Cloudflare JS-challenge в ответе httpx
_CF_INDICATORS = [
    "cf-browser-verification",
    "challenge-platform",
    "cf_clearance",
    "Just a moment",
    "Enable JavaScript",
    "Checking your browser",
]


def _needs_playwright(status_code: int, text: str) -> bool:
    """Определить нужен ли Playwright fallback по ответу httpx."""
    if status_code == 403:
        return True
    if status_code == 200 and len(text) < 500:
        return True
    if any(indicator in text for indicator in _CF_INDICATORS):
        return True
    return False


def _random_headers() -> dict:
    """Возвращает заголовки случайного браузера."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }


def _is_blocked_domain(url: str) -> bool:
    """Проверить URL против стоп-листа."""
    try:
        host = urlparse(url).hostname or ""
        return any(
            host == domain or host.endswith(f".{domain}")
            for domain in _BLOCKED_DOMAINS
        )
    except Exception:
        return False


class WebCollector(BaseCollector):
    """Collect documents from web: DuckDuckGo search or specific URLs."""

    async def collect(self, config: ResearchConfig) -> tuple[list[Document], list[str], int]:
        if config.source_type == SourceType.SPECIFIC_URLS:
            urls = list(config.source_urls)
        else:
            urls = await self._search_urls(config)

        # Фильтрация стоп-листа
        blocked = [u for u in urls if _is_blocked_domain(u)]
        urls = [u for u in urls if not _is_blocked_domain(u)]
        if blocked:
            logger.info("Пропущено {} URL из стоп-листа: {}", len(blocked), blocked[:5])

        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            docs, failed = await self._fetch_all(client, urls)

        logger.info(
            "Collected {} documents ({} failed, {} blocked) for topic '{}'",
            len(docs), len(failed), len(blocked), config.topic,
        )
        return docs, failed, len(blocked)

    # ------------------------------------------------------------------
    # Concurrent fetching
    # ------------------------------------------------------------------

    async def _fetch_all(
        self,
        client: httpx.AsyncClient,
        urls: list[str],
    ) -> tuple[list[Document], list[str]]:
        """Fetch URLs concurrently. Returns (documents, failed_urls)."""
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def fetch_with_sem(url: str) -> Document | None:
            async with semaphore:
                await asyncio.sleep(random.uniform(0.5, 2.5))
                return await self._fetch_page(client, url)

        results = await asyncio.gather(
            *[fetch_with_sem(url) for url in urls],
            return_exceptions=True,
        )

        docs: list[Document] = []
        failed: list[str] = []
        seen_hashes: set[str] = set()

        for url, result in zip(urls, results):
            if isinstance(result, BaseException):
                logger.warning("Exception fetching {}: {}", url, result)
                failed.append(url)
            elif result is None:
                failed.append(url)
            else:
                doc: Document = result
                if doc.content_hash in seen_hashes:
                    logger.debug("Duplicate skipped: {}", url)
                else:
                    seen_hashes.add(doc.content_hash)
                    docs.append(doc)

        return docs, failed

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
            timeout=_REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            for i, query in enumerate(queries):
                if len(urls) >= max_pages:
                    break
                if i > 0:
                    await asyncio.sleep(3)
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
            resp = await client.get(url, headers=_random_headers())
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
        raw_text: str | None = None

        for attempt in range(2):
            try:
                resp = await client.get(url, headers=_random_headers())
                if resp.status_code == 429:
                    if attempt == 0:
                        wait = float(resp.headers.get("Retry-After", "5"))
                        logger.debug("429 на {}, жду {:.0f}с", url, wait)
                        await asyncio.sleep(min(wait, 10))
                        continue
                    logger.warning("429 повторно на {}, пропускаем", url)
                    return None
                if resp.status_code == 503 and attempt == 0:
                    await asyncio.sleep(random.uniform(2, 5))
                    continue

                # 403 — не вызываем raise_for_status, пробуем Playwright
                if resp.status_code == 403:
                    if _PLAYWRIGHT_ENABLED:
                        raw_text = ""  # пустой текст → _needs_playwright вернёт True
                    else:
                        resp.raise_for_status()
                else:
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        logger.debug("Skipping non-HTML content at {}", url)
                        return None
                    raw_text = resp.text

            except httpx.HTTPError as exc:
                if attempt == 0:
                    logger.debug("Retry {} после ошибки: {}", url, exc)
                    await asyncio.sleep(random.uniform(1, 3))
                    continue
                logger.warning("Failed to fetch {}: {}", url, exc)
                return None

            # Playwright fallback
            if _PLAYWRIGHT_ENABLED and raw_text is not None and _needs_playwright(resp.status_code, raw_text):
                logger.debug("Playwright fallback для {}", url)
                html = await PlaywrightFetcher.fetch(url)
                if html is None:
                    return None
                raw_text = html

            soup = BeautifulSoup(raw_text or "", "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else url

            for tag in soup.find_all(_REMOVE_TAGS):
                tag.decompose()

            main = soup.find("main") or soup.find("article") or soup.body
            if main is None:
                return None

            text = main.get_text(separator="\n", strip=True)
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

        return None

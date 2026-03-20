"""URL collector via Haiku + web_search tool."""
from __future__ import annotations

import asyncio
import os
import re

import httpx
from loguru import logger

_SYSTEM = (
    "Ты помощник для продуктового исследования. "
    "Твоя задача — найти максимум реальных URL по заданной теме. "
    "Используй инструмент web_search столько раз, сколько нужно, с разными запросами "
    "чтобы покрыть разные аспекты темы. "
    "Предпочитай источники с открытым доступом (без paywall): "
    "официальные сайты госорганов и статагентств, открытые аналитические отчёты, "
    "отраслевые порталы и профильные СМИ с бесплатным контентом, "
    "корпоративные блоги и пресс-релизы компаний, экспертные статьи и исследования. "
    "Избегай: Википедию, форумы, агрегаторы без собственного контента, "
    "поисковые страницы, социальные сети. "
    "Приоритизируй материалы за последние 12-18 месяцев. "
    "Возвращай только URL, по одному на строку, без пояснений."
)

_ASPECTS_A = (
    "— статистика и данные с конкретными цифрами\n"
    "— аналитические обзоры и отраслевые отчёты\n"
    "— официальные источники и регуляторные данные\n"
    "— академические статьи и исследования"
)

_ASPECTS_B = (
    "— новости 2024-2025 с конкретными событиями\n"
    "— прогнозы и оценки экспертов\n"
    "— корпоративные блоги и кейсы компаний\n"
    "— сравнительные обзоры и бенчмарки"
)


def _build_prompt(topic: str, language: str, n_urls: int, aspects: str) -> str:
    lang_hint = "на русском языке" if language == "ru" else "in English"
    return (
        f"Найди {n_urls} реальных URL по теме: «{topic}» ({lang_hint}). "
        f"Сделай 8 поисковых запросов по следующим аспектам:\n"
        f"{aspects}\n"
        f"Для каждого аспекта используй 2 разных поисковых запроса.\n"
        f"Перечисли все найденные URL — по одному на строку, без нумерации и пояснений."
    )


def _extract_urls(text: str) -> list[str]:
    """Extract URLs from model text response."""
    pattern = r'https?://[^\s\)\]\,\"\'<>]+'
    found = re.findall(pattern, text)
    bad = (
        "google.com/search", "yandex.ru/search", "bing.com/search",
        "vk.com", "t.me", "instagram.com", "facebook.com", "twitter.com",
        # paywall / требуют авторизации
        "rbc.ru", "kommersant.ru", "vedomosti.ru", "fontanka.ru",
    )
    return [u for u in found if not any(b in u for b in bad)]


async def _search_batch(
    client,
    topic: str,
    language: str,
    n_urls: int,
    aspects: str,
    batch_label: str,
) -> list[str]:
    """Single Haiku call with max_uses=8."""
    import anthropic

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
        messages=[{
            "role": "user",
            "content": _build_prompt(topic, language, n_urls, aspects),
        }],
    )

    all_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            all_text += block.text + "\n"
        if hasattr(block, "content"):
            for inner in (block.content if isinstance(block.content, list) else []):
                if hasattr(inner, "text"):
                    all_text += inner.text + "\n"

    urls = _extract_urls(all_text)
    logger.info("Batch {}: {} URLs found", batch_label, len(urls))
    return urls


async def collect_urls(
    topic: str,
    language: str = "ru",
    n_urls: int = 150,
) -> list[str]:
    """Collect URLs for a topic via two parallel Haiku web_search calls (8 searches each).

    Returns deduplicated list of real URLs.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic SDK not installed")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        http_client=httpx.AsyncClient(),  # без системных proxy переменных
    )

    logger.info("Collecting URLs for '{}' via Haiku web_search (2 parallel batches)...", topic)

    half = n_urls // 2
    results = await asyncio.gather(
        _search_batch(client, topic, language, half, _ASPECTS_A, "A"),
        _search_batch(client, topic, language, half, _ASPECTS_B, "B"),
        return_exceptions=True,
    )

    all_urls: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Batch failed: {}", r)
        else:
            all_urls.extend(r)

    urls = list(dict.fromkeys(all_urls))  # deduplicate preserving order
    logger.info("Collected {} unique URLs for '{}'", len(urls), topic)
    return urls

"""URL collector via Haiku + web_search tool."""
from __future__ import annotations

import os
import re

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


def _build_search_prompt(topic: str, language: str, n_urls: int) -> str:
    lang_hint = "на русском языке" if language == "ru" else "in English"
    n_searches = max(10, min(20, n_urls // 10))
    return (
        f"Найди {n_urls} реальных URL по теме: «{topic}» ({lang_hint}). "
        f"Сделай {n_searches} поисковых запросов охватывающих разные аспекты:\n"
        f"— статистика и данные с конкретными цифрами (объёмы рынка, доли, динамика)\n"
        f"— аналитические обзоры и отраслевые отчёты\n"
        f"— официальные источники и регуляторные данные\n"
        f"— новости 2024-2025 с конкретными событиями\n"
        f"— прогнозы и оценки экспертов\n"
        f"— региональная специфика и сегментация.\n"
        f"Для каждого аспекта используй минимум 2 разных поисковых запроса.\n"
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


async def collect_urls(
    topic: str,
    language: str = "ru",
    n_urls: int = 150,
) -> list[str]:
    """Collect URLs for a topic via Haiku + web_search.

    Returns deduplicated list of real URLs.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic SDK not installed")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    logger.info("Collecting URLs for '{}' via Haiku web_search...", topic)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 20}],
        messages=[{
            "role": "user",
            "content": _build_search_prompt(topic, language, n_urls),
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
    urls = list(dict.fromkeys(urls))  # deduplicate preserving order

    logger.info("Collected {} unique URLs for '{}'", len(urls), topic)
    return urls

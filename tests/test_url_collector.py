"""Tests for URL collector module."""
import os

import pytest


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key")
async def test_collect_urls_basic():
    from src.ingestion.url_collector import collect_urls

    urls = await collect_urls("инфляция ЦБ России 2024", language="ru", n_urls=20)
    assert len(urls) > 5
    assert all(u.startswith("http") for u in urls)
    assert not any("google.com/search" in u for u in urls)


def test_extract_urls():
    from src.ingestion.url_collector import _extract_urls

    text = """
    https://cbr.ru/statistics/macro_itm/
    https://www.rbc.ru/economics/123
    https://google.com/search?q=test
    https://t.me/channel/123
    http://example.com/page
    """
    urls = _extract_urls(text)
    assert "https://cbr.ru/statistics/macro_itm/" in urls
    assert "https://www.rbc.ru/economics/123" in urls
    assert "http://example.com/page" in urls
    # Filtered out:
    assert not any("google.com/search" in u for u in urls)
    assert not any("t.me" in u for u in urls)


def test_extract_urls_empty():
    from src.ingestion.url_collector import _extract_urls

    assert _extract_urls("no urls here") == []
    assert _extract_urls("") == []

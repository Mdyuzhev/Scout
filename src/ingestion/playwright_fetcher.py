"""Playwright-based fetcher for JS-rendered pages."""
from __future__ import annotations

import asyncio

from loguru import logger


class PlaywrightFetcher:
    """Fetches pages that require JS execution."""

    # Singleton браузер — создаётся один раз, живёт весь прогон
    _browser = None
    _playwright = None
    _lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def ensure_started(cls) -> None:
        """Ленивая инициализация браузера (thread-safe)."""
        if cls._browser is not None:
            return
        async with cls._get_lock():
            if cls._browser is not None:
                return
            from playwright.async_api import async_playwright

            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                ],
            )
            logger.info("Playwright Chromium запущен")

    @classmethod
    async def close(cls) -> None:
        """Idempotent cleanup — safe to call multiple times."""
        async with cls._get_lock():
            if cls._browser is not None:
                try:
                    await cls._browser.close()
                except Exception:
                    pass
                cls._browser = None
            if cls._playwright is not None:
                try:
                    await cls._playwright.stop()
                except Exception:
                    pass
                cls._playwright = None

    @classmethod
    async def fetch(cls, url: str, timeout_ms: int = 15_000) -> str | None:
        """
        Загрузить страницу через реальный браузер.
        Возвращает HTML или None при ошибке.
        """
        await cls.ensure_started()
        context = None
        try:
            context = await cls._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )
            page = await context.new_page()

            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,ico}",
                lambda route: route.abort(),
            )

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await asyncio.sleep(2)
            html = await page.content()
            return html

        except Exception as exc:
            logger.warning("Playwright failed for {}: {}", url, exc)
            return None

        finally:
            # SC-M5: всегда закрываем context, даже при exception
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

"""Anthropic-based briefer using Claude Haiku."""

from __future__ import annotations

import asyncio

import anthropic
import httpx
from loguru import logger

from .base import BaseBriefer

_RETRY_DELAYS = [15, 30, 60]  # секунд ожидания перед 2-й, 3-й и 4-й попыткой

# Ошибки при которых имеет смысл повторить запрос
_RETRYABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    ConnectionError,
)

_SYSTEM_PROMPT = (
    "Ты — аналитик-исследователь. Пишешь для product manager или руководителя, "
    "принимающего решения. "
    "Тебе предоставлен контекст из нескольких источников по заданной теме. "
    "Твоя задача — синтезировать ключевые выводы в структурированный brief "
    "на том же языке, что и тема исследования. "
    "Используй ТОЛЬКО информацию из предоставленного контекста. "
    "Не выдумывай факты. Если данных недостаточно по разделу — укажи это явно.\n\n"
    "Структура брифа (строго соблюдай):\n"
    "## 1. Ключевые цифры (5-7 метрик с годом данных рядом с каждой)\n"
    "## 2. Основные тренды (3-5 трендов, каждый — 2-4 предложения с данными)\n"
    "## 3. Участники рынка (ключевые игроки, доли, позиционирование)\n"
    "## 4. Риски и ограничения (2-4 пункта)\n"
    "## 5. Выводы для принятия решений (2-3 actionable вывода)\n\n"
    "Каждая метрика должна содержать: значение, единицу измерения, год/период, "
    "источник (если указан в контексте). "
    "Пример: 'Объём рынка: 1,2 трлн руб. (2024, Росстат)'."
)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class AnthropicBriefer(BaseBriefer):
    """Generate research briefs using Anthropic Claude Haiku."""

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate_brief(self, context: str, topic: str, *, model: str | None = None) -> dict:
        """Generate brief. Returns dict with brief, model, tokens_used."""
        prompt = (
            f"Тема исследования: {topic}\n\n"
            f"Контекст из источников:\n\n{context}\n\n"
            "Составь brief строго по заданной структуре (5 разделов). "
            "Для раздела «Ключевые цифры» выпиши все метрики с годом данных. "
            "Не добавляй разделы, которых нет в структуре."
        )

        effective_model = model or self._model
        last_error: str | None = None

        for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
            if delay:
                logger.warning(
                    "AnthropicBriefer: rate limit, retry {}/{} after {}s",
                    attempt, len(_RETRY_DELAYS) + 1, delay,
                )
                await asyncio.sleep(delay)
            try:
                response = await self._client.messages.create(
                    model=effective_model,
                    max_tokens=4096,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
                tokens = response.usage.input_tokens + response.usage.output_tokens
                logger.info(
                    "Brief generated: {} chars, {} tokens ({}, attempt {})",
                    len(text), tokens, effective_model, attempt,
                )
                return {"brief": text, "model": effective_model,
                        "tokens_used": tokens, "error": None}

            except _RETRYABLE_ERRORS as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "AnthropicBriefer: retryable error attempt {}/{}: {}",
                    attempt, len(_RETRY_DELAYS) + 1, exc,
                )
                # продолжаем retry

            except Exception as exc:
                last_error = str(exc)
                logger.error("AnthropicBriefer failed (no retry): {}", exc)
                break  # не ретраить на другие ошибки

        logger.error("AnthropicBriefer: exhausted retries. last_error={}", last_error)
        return {"brief": None, "model": effective_model,
                "tokens_used": None, "error": last_error}

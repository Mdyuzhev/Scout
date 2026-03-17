"""Unit tests for AnthropicBriefer retry logic on 429 RateLimitError."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest


@pytest.mark.asyncio
async def test_retry_on_rate_limit():
    """Briefer должен сделать 3 попытки при 429 и вернуть error."""
    from src.llm.anthropic_briefer import AnthropicBriefer

    briefer = AnthropicBriefer(api_key="test")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        # Имитируем минимальный response для RateLimitError
        mock_response = MagicMock()
        mock_response.status_code = 429
        raise anthropic.RateLimitError(
            message="rate limit",
            response=mock_response,
            body={"error": {"type": "rate_limit_error"}},
        )

    with patch.object(briefer._client.messages, "create", side_effect=fake_create):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await briefer.generate_brief("ctx", "topic")

    assert call_count == 3, f"Ожидали 3 попытки, получили {call_count}"
    assert result["brief"] is None
    assert result["error"] is not None
    assert "rate_limit" in result["error"]


@pytest.mark.asyncio
async def test_no_retry_on_generic_error():
    """Briefer НЕ должен делать retry на обычную ошибку — только 1 попытка."""
    from src.llm.anthropic_briefer import AnthropicBriefer

    briefer = AnthropicBriefer(api_key="test")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        raise ValueError("some unexpected error")

    with patch.object(briefer._client.messages, "create", side_effect=fake_create):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await briefer.generate_brief("ctx", "topic")

    assert call_count == 1, f"Ожидали 1 попытку, получили {call_count}"
    mock_sleep.assert_not_called()
    assert result["brief"] is None
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    """Успешный ответ — возвращает brief и error=None."""
    from src.llm.anthropic_briefer import AnthropicBriefer

    briefer = AnthropicBriefer(api_key="test")

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Test brief text")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    async def fake_create(**kwargs):
        return mock_response

    with patch.object(briefer._client.messages, "create", side_effect=fake_create):
        result = await briefer.generate_brief("ctx", "topic")

    assert result["brief"] == "Test brief text"
    assert result["error"] is None
    assert result["tokens_used"] == 150


@pytest.mark.asyncio
async def test_retry_success_on_second_attempt():
    """Briefer должен вернуть успех если 2-я попытка удалась."""
    from src.llm.anthropic_briefer import AnthropicBriefer

    briefer = AnthropicBriefer(api_key="test")
    call_count = 0

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Brief after retry")]
    mock_response.usage.input_tokens = 50
    mock_response.usage.output_tokens = 25

    mock_http_response = MagicMock()
    mock_http_response.status_code = 429

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise anthropic.RateLimitError(
                message="rate limit",
                response=mock_http_response,
                body={"error": {"type": "rate_limit_error"}},
            )
        return mock_response

    with patch.object(briefer._client.messages, "create", side_effect=fake_create):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await briefer.generate_brief("ctx", "topic")

    assert call_count == 2
    assert result["brief"] == "Brief after retry"
    assert result["error"] is None

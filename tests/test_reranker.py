"""Tests for Reranker — only fast scenarios, no real model loading."""

import importlib

import pytest

from src.config import SearchResult


def _make_result(text: str, idx: int = 0) -> SearchResult:
    return SearchResult(
        chunk_id=f"id_{idx}",
        text=text,
        source_url=f"https://example.com/{idx}",
        source_title=f"Doc {idx}",
        similarity=0.7,
    )


@pytest.mark.asyncio
async def test_reranker_disabled(monkeypatch):
    """При RERANKER_ENABLED=false возвращает results[:top_k] без загрузки модели."""
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    import src.retrieval.reranker as mod
    importlib.reload(mod)  # подхватить новый env
    reranker = mod.Reranker()
    results = [_make_result(f"text {i}", i) for i in range(10)]
    reranked = await reranker.rerank("query", results, top_k=3)
    assert len(reranked) == 3
    assert reranker._model is None  # модель не загружалась


@pytest.mark.asyncio
async def test_reranker_empty_input():
    """Пустой список возвращается как есть."""
    from src.retrieval.reranker import Reranker
    reranker = Reranker()
    assert await reranker.rerank("query", [], top_k=5) == []


@pytest.mark.asyncio
async def test_reranker_fewer_than_top_k(monkeypatch):
    """Если кандидатов меньше top_k — возвращает все."""
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    import src.retrieval.reranker as mod
    importlib.reload(mod)
    reranker = mod.Reranker()
    results = [_make_result("text", 0)]
    reranked = await reranker.rerank("query", results, top_k=10)
    assert len(reranked) == 1

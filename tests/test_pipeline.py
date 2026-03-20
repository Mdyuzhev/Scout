"""Tests for ScoutPipeline and AnthropicBriefer."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.config import (
    Chunk,
    Document,
    ResearchConfig,
    ResearchPackage,
    ResearchSession,
    SearchResult,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# ScoutPipeline tests — mock heavy deps before import
# ---------------------------------------------------------------------------


def _make_pipeline():
    """Import ScoutPipeline with all heavy deps mocked."""
    for mod in ("chromadb", "chromadb.utils", "chromadb.utils.embedding_functions"):
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    from src.pipeline import ScoutPipeline

    p = ScoutPipeline.__new__(ScoutPipeline)
    p._web_collector = MagicMock()
    p._local_collector = MagicMock()
    p._chunker = MagicMock()
    p._indexer = MagicMock()
    p._searcher = MagicMock()
    p._reranker = MagicMock()
    p._reranker.rerank = MagicMock(side_effect=lambda query, results, top_k: results[:top_k])
    p._context_builder = MagicMock()
    p._briefer = None
    p._initialized = True

    # Mock SessionStore
    p._session_store = AsyncMock()
    p._session_store.find_similar = AsyncMock(return_value=None)
    p._session_store.save = AsyncMock()
    p._session_store.get = AsyncMock(return_value=None)
    p._session_store.list_recent = AsyncMock(return_value=[])
    return p


class TestScoutPipeline:

    @pytest.fixture()
    def pipeline(self):
        return _make_pipeline()

    @pytest.mark.asyncio
    async def test_index_success(self, pipeline):
        docs = [
            Document(url="https://a.com", title="A", content="word " * 100),
            Document(url="https://b.com", title="B", content="text " * 100),
        ]
        chunks = [Chunk(text="chunk1", source_url="https://a.com", source_title="A")]

        pipeline._web_collector.collect = AsyncMock(return_value=(docs, [], 0))
        pipeline._chunker.chunk = MagicMock(return_value=chunks)
        pipeline._indexer.index = MagicMock(return_value=1)

        config = ResearchConfig(topic="test topic")
        session, failed, blocked = await pipeline.index(config)

        assert session.status == SessionStatus.READY
        assert session.documents_count == 2
        assert session.chunks_count == 1
        assert failed == []
        assert blocked == 0
        assert pipeline._session_store.save.await_count >= 1

    @pytest.mark.asyncio
    async def test_index_with_failed_urls(self, pipeline):
        """index() returns failed_urls from collector."""
        docs = [Document(url="https://a.com", title="A", content="word " * 100)]
        chunks = [Chunk(text="chunk1", source_url="https://a.com", source_title="A")]

        pipeline._web_collector.collect = AsyncMock(
            return_value=(docs, ["https://bad1.com", "https://bad2.com"], 1)
        )
        pipeline._chunker.chunk = MagicMock(return_value=chunks)
        pipeline._indexer.index = MagicMock(return_value=1)

        from src.config import SourceType
        config = ResearchConfig(
            topic="test urls",
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=["https://a.com", "https://bad1.com", "https://bad2.com"],
        )
        session, failed, blocked = await pipeline.index(config)

        assert session.status == SessionStatus.READY
        assert session.documents_count == 1
        assert len(failed) == 2
        assert "https://bad1.com" in failed
        assert blocked == 1

    @pytest.mark.asyncio
    async def test_index_failure(self, pipeline):
        pipeline._web_collector.collect = AsyncMock(side_effect=RuntimeError("fail"))

        config = ResearchConfig(topic="failing")
        session, failed, blocked = await pipeline.index(config)

        assert session.status == SessionStatus.FAILED
        assert "fail" in session.error

    @pytest.mark.asyncio
    async def test_index_returns_cached(self, pipeline):
        cached = ResearchSession(
            config=ResearchConfig(topic="cached topic"),
            status=SessionStatus.READY,
            documents_count=3,
            chunks_count=10,
        )
        pipeline._session_store.find_similar = AsyncMock(return_value=cached)

        config = ResearchConfig(topic="cached topic")
        session, failed, blocked = await pipeline.index(config)

        assert session.id == cached.id
        assert session.status == SessionStatus.READY
        assert failed == []
        assert blocked == 0
        # collector should NOT be called
        pipeline._web_collector.collect = AsyncMock()
        assert pipeline._web_collector.collect.await_count == 0

    @pytest.mark.asyncio
    async def test_search_returns_package(self, pipeline):
        sid = uuid4()
        config = ResearchConfig(topic="test")
        session = ResearchSession(id=sid, config=config, status=SessionStatus.READY, chunks_count=5)
        pipeline._session_store.get = AsyncMock(return_value=session)

        results = [
            SearchResult(chunk_id="c1", text="t1", source_url="u1", source_title="s1", similarity=0.9),
        ]
        pipeline._searcher.search = MagicMock(return_value=results)
        pipeline._context_builder.build = MagicMock(
            return_value=ResearchPackage(
                session_id=sid, topic="test", query="q", results=results, total_chunks_in_index=5
            )
        )

        package = await pipeline.search(sid, "q")
        assert package.topic == "test"
        assert len(package.results) == 1

    @pytest.mark.asyncio
    async def test_search_session_not_found(self, pipeline):
        pipeline._session_store.get = AsyncMock(return_value=None)
        with pytest.raises(KeyError):
            await pipeline.search(uuid4(), "q")

    @pytest.mark.asyncio
    async def test_brief_no_api_key(self, pipeline):
        sid = uuid4()
        config = ResearchConfig(topic="test")
        session = ResearchSession(id=sid, config=config, status=SessionStatus.READY, chunks_count=5)
        pipeline._session_store.get = AsyncMock(return_value=session)

        results = [
            SearchResult(chunk_id="c1", text="t1", source_url="u1", source_title="s1", similarity=0.9),
        ]
        pipeline._searcher.search = MagicMock(return_value=results)
        pipeline._context_builder.build = MagicMock(
            return_value=ResearchPackage(
                session_id=sid, topic="test", query="q", results=results, total_chunks_in_index=5
            )
        )

        result = await pipeline.brief(sid, "q")
        assert result["brief"] is None
        assert result["error"] == "No API key configured"

    @pytest.mark.asyncio
    async def test_list_sessions(self, pipeline):
        sessions = [
            ResearchSession(config=ResearchConfig(topic="t1"), status=SessionStatus.READY, chunks_count=5),
            ResearchSession(config=ResearchConfig(topic="t2"), status=SessionStatus.FAILED),
        ]
        pipeline._session_store.list_recent = AsyncMock(return_value=sessions)

        result = await pipeline.list_sessions(10)
        assert len(result) == 2
        assert result[0]["topic"] == "t1"
        assert result[1]["status"] == "failed"


# ---------------------------------------------------------------------------
# AnthropicBriefer tests
# ---------------------------------------------------------------------------


class TestAnthropicBriefer:

    @pytest.mark.asyncio
    async def test_generate_brief_success(self):
        with patch("src.llm.anthropic_briefer.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            mock_block = MagicMock()
            mock_block.text = "This is a brief"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 50
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            from src.llm.anthropic_briefer import AnthropicBriefer

            briefer = AnthropicBriefer(api_key="test-key")
            briefer._client = mock_client

            result = await briefer.generate_brief("context text", "topic")
            assert result["brief"] == "This is a brief"
            assert result["tokens_used"] == 150

    @pytest.mark.asyncio
    async def test_generate_brief_error(self):
        with patch("src.llm.anthropic_briefer.anthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API error"))

            from src.llm.anthropic_briefer import AnthropicBriefer

            briefer = AnthropicBriefer(api_key="test-key")
            briefer._client = mock_client

            result = await briefer.generate_brief("context", "topic")
            assert result["brief"] is None

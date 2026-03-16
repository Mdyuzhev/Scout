"""Smoke-тесты SC-004 — retrieval pipeline."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.config import ResearchConfig, ResearchSession, SearchResult

# Stub chromadb for environments where it's not installed
if "chromadb" not in sys.modules:
    _chromadb = ModuleType("chromadb")
    _chromadb.PersistentClient = MagicMock  # type: ignore[attr-defined]
    sys.modules["chromadb"] = _chromadb
    _ef_mod = ModuleType("chromadb.utils")
    sys.modules["chromadb.utils"] = _ef_mod
    _ef_mod2 = ModuleType("chromadb.utils.embedding_functions")
    _ef_mod2.SentenceTransformerEmbeddingFunction = MagicMock  # type: ignore[attr-defined]
    sys.modules["chromadb.utils.embedding_functions"] = _ef_mod2

from src.retrieval.context_builder import ContextBuilder
from src.retrieval.searcher import Searcher, SessionNotFoundError


# ---------------------------------------------------------------------------
# Searcher tests
# ---------------------------------------------------------------------------


class TestSearcher:
    def _make_searcher(self, mock_chroma, mock_ef):
        """Create a Searcher with mocked ChromaDB."""
        mock_client = MagicMock()
        mock_chroma.PersistentClient.return_value = mock_client
        searcher = Searcher(chroma_path="/tmp/test", model_name="test-model")
        return searcher, mock_client

    def test_search_returns_results(self):
        """Search returns SearchResult list sorted by similarity."""
        with patch("src.retrieval.searcher.chromadb") as mock_chroma, \
             patch("src.retrieval.searcher.SentenceTransformerEmbeddingFunction"):
            searcher, mock_client = self._make_searcher(mock_chroma, None)

            mock_collection = MagicMock()
            mock_collection.query.return_value = {
                "ids": [["c1", "c2", "c3"]],
                "documents": [["text1", "text2", "text3"]],
                "distances": [[0.1, 0.3, 0.5]],
                "metadatas": [[
                    {"source_url": "http://a.com", "source_title": "A"},
                    {"source_url": "http://b.com", "source_title": "B"},
                    {"source_url": "http://c.com", "source_title": "C"},
                ]],
            }
            mock_client.get_collection.return_value = mock_collection

            session_id = uuid4()
            results = searcher.search("test query", session_id, top_k=10, min_similarity=0.5)

            assert len(results) == 3
            assert all(isinstance(r, SearchResult) for r in results)
            # Sorted descending by similarity
            assert results[0].similarity >= results[1].similarity >= results[2].similarity

    def test_search_filters_by_min_similarity(self):
        """Results below min_similarity are excluded."""
        with patch("src.retrieval.searcher.chromadb") as mock_chroma, \
             patch("src.retrieval.searcher.SentenceTransformerEmbeddingFunction"):
            searcher, mock_client = self._make_searcher(mock_chroma, None)

            mock_collection = MagicMock()
            # distance=10 → similarity=1/(1+10)≈0.09 — below threshold
            mock_collection.query.return_value = {
                "ids": [["c1", "c2"]],
                "documents": [["close", "far"]],
                "distances": [[0.1, 10.0]],
                "metadatas": [[
                    {"source_url": "http://a.com", "source_title": "A"},
                    {"source_url": "http://b.com", "source_title": "B"},
                ]],
            }
            mock_client.get_collection.return_value = mock_collection

            results = searcher.search("q", uuid4(), min_similarity=0.5)

            assert len(results) == 1
            assert results[0].chunk_id == "c1"

    def test_search_session_not_found(self):
        """Missing collection raises SessionNotFoundError."""
        with patch("src.retrieval.searcher.chromadb") as mock_chroma, \
             patch("src.retrieval.searcher.SentenceTransformerEmbeddingFunction"):
            searcher, mock_client = self._make_searcher(mock_chroma, None)
            mock_client.get_collection.side_effect = Exception("not found")

            with pytest.raises(SessionNotFoundError):
                searcher.search("q", uuid4())

    def test_search_empty_results(self):
        """Empty collection returns empty list."""
        with patch("src.retrieval.searcher.chromadb") as mock_chroma, \
             patch("src.retrieval.searcher.SentenceTransformerEmbeddingFunction"):
            searcher, mock_client = self._make_searcher(mock_chroma, None)

            mock_collection = MagicMock()
            mock_collection.query.return_value = {
                "ids": [[]],
                "documents": [[]],
                "distances": [[]],
                "metadatas": [[]],
            }
            mock_client.get_collection.return_value = mock_collection

            results = searcher.search("q", uuid4())
            assert results == []


# ---------------------------------------------------------------------------
# ContextBuilder tests
# ---------------------------------------------------------------------------


class TestContextBuilder:
    def _make_session(self) -> ResearchSession:
        return ResearchSession(config=ResearchConfig(topic="test topic"))

    def test_build_returns_research_package(self):
        """Build returns a valid ResearchPackage."""
        session = self._make_session()
        results = [
            SearchResult(chunk_id="c1", text="t1", source_url="http://a.com",
                         source_title="A", similarity=0.9),
            SearchResult(chunk_id="c2", text="t2", source_url="http://b.com",
                         source_title="B", similarity=0.8),
        ]
        builder = ContextBuilder()
        pkg = builder.build(session, "my query", results, total_in_index=50)

        assert pkg.session_id == session.id
        assert pkg.topic == "test topic"
        assert pkg.query == "my query"
        assert len(pkg.results) == 2
        assert pkg.total_chunks_in_index == 50

    def test_build_deduplicates_by_source(self):
        """No more than 2 chunks from the same source_url."""
        session = self._make_session()
        results = [
            SearchResult(chunk_id=f"c{i}", text=f"t{i}", source_url="http://same.com",
                         source_title="Same", similarity=0.9 - i * 0.01)
            for i in range(6)
        ]
        builder = ContextBuilder()
        pkg = builder.build(session, "q", results, total_in_index=100)

        assert len(pkg.results) == 2  # capped at 2 per source

    def test_build_sorts_by_similarity(self):
        """Results are sorted descending by similarity."""
        session = self._make_session()
        results = [
            SearchResult(chunk_id="c1", text="t1", source_url="http://a.com",
                         source_title="A", similarity=0.7),
            SearchResult(chunk_id="c2", text="t2", source_url="http://b.com",
                         source_title="B", similarity=0.9),
            SearchResult(chunk_id="c3", text="t3", source_url="http://c.com",
                         source_title="C", similarity=0.8),
        ]
        builder = ContextBuilder()
        pkg = builder.build(session, "q", results, total_in_index=10)

        sims = [r.similarity for r in pkg.results]
        assert sims == sorted(sims, reverse=True)

    def test_build_mixed_sources_dedup(self):
        """Mixed sources: keeps diversity while respecting per-source limit."""
        session = self._make_session()
        results = [
            SearchResult(chunk_id="a1", text="t", source_url="http://a.com",
                         source_title="A", similarity=0.95),
            SearchResult(chunk_id="a2", text="t", source_url="http://a.com",
                         source_title="A", similarity=0.93),
            SearchResult(chunk_id="a3", text="t", source_url="http://a.com",
                         source_title="A", similarity=0.91),
            SearchResult(chunk_id="a4", text="t", source_url="http://a.com",
                         source_title="A", similarity=0.89),
            SearchResult(chunk_id="b1", text="t", source_url="http://b.com",
                         source_title="B", similarity=0.88),
        ]
        builder = ContextBuilder()
        pkg = builder.build(session, "q", results, total_in_index=50)

        # 2 from a.com + 1 from b.com = 3
        assert len(pkg.results) == 3
        a_count = sum(1 for r in pkg.results if r.source_url == "http://a.com")
        assert a_count == 2

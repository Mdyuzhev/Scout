"""Smoke-тесты SC-003 — ingestion pipeline."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.config import Chunk, Document, ResearchConfig, SourceType

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
from src.chunking.sliding_window import SlidingWindowChunker
from src.ingestion.web import WebCollector


# ---------------------------------------------------------------------------
# WebCollector tests
# ---------------------------------------------------------------------------


def _make_html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body><main>{body}</main></body></html>"


@pytest.fixture
def mock_httpx_client():
    """Patch httpx.AsyncClient so no real HTTP calls are made."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestWebCollector:
    def test_collect_specific_urls(self, mock_httpx_client):
        """SPECIFIC_URLS mode: fetches listed URLs, returns Documents."""
        page_html = _make_html("Test Page", "A" * 100)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = page_html
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.raise_for_status = MagicMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_resp)

        config = ResearchConfig(
            topic="test",
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=["http://example.com/page1"],
        )

        with patch("src.ingestion.web.httpx.AsyncClient", return_value=mock_httpx_client):
            collector = WebCollector()
            docs, failed, blocked = asyncio.run(collector.collect(config))

        assert len(docs) >= 1
        assert all(isinstance(d, Document) for d in docs)
        assert docs[0].title == "Test Page"
        assert failed == []

    def test_collect_deduplicates(self, mock_httpx_client):
        """Duplicate pages (same content_hash) are skipped."""
        page_html = _make_html("Page", "Same content here. " * 10)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = page_html
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.raise_for_status = MagicMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_resp)

        config = ResearchConfig(
            topic="test",
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=["http://a.com/1", "http://b.com/2"],
        )

        with patch("src.ingestion.web.httpx.AsyncClient", return_value=mock_httpx_client):
            collector = WebCollector()
            docs, failed, blocked = asyncio.run(collector.collect(config))

        assert len(docs) == 1  # second page deduplicated

    def test_collect_skips_errors(self, mock_httpx_client):
        """HTTP errors go to failed_urls, not raised."""
        mock_httpx_client.get = AsyncMock(side_effect=httpx.ConnectError("fail"))

        config = ResearchConfig(
            topic="test",
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=["http://broken.com"],
        )

        with patch("src.ingestion.web.httpx.AsyncClient", return_value=mock_httpx_client):
            collector = WebCollector()
            docs, failed, blocked = asyncio.run(collector.collect(config))

        assert docs == []
        assert "http://broken.com" in failed

    def test_fetch_all_partial_failures(self, mock_httpx_client):
        """_fetch_all: 5 URLs, 2 raise exceptions → 3 docs, 2 failed."""
        good_html = _make_html("Good", "content " * 20)
        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.text = good_html
        good_resp.headers = {"content-type": "text/html; charset=utf-8"}
        good_resp.raise_for_status = MagicMock()

        call_count = 0

        async def get_side_effect(url, **kwargs):
            nonlocal call_count
            if "bad" in url:
                raise httpx.ConnectError("fail")
            call_count += 1
            r = MagicMock()
            r.status_code = 200
            r.text = _make_html(f"Page{call_count}", f"unique content {call_count} " * 20)
            r.headers = {"content-type": "text/html; charset=utf-8"}
            r.raise_for_status = MagicMock()
            return r

        mock_httpx_client.get = get_side_effect

        urls = [
            "http://good1.com",
            "http://bad1.com",
            "http://good2.com",
            "http://bad2.com",
            "http://good3.com",
        ]

        with patch("src.ingestion.web.httpx.AsyncClient", return_value=mock_httpx_client):
            collector = WebCollector()
            docs, failed = asyncio.run(
                collector._fetch_all(mock_httpx_client, urls)
            )

        assert len(docs) == 3
        assert len(failed) == 2
        assert "http://bad1.com" in failed
        assert "http://bad2.com" in failed

    def test_blocked_domains_filtered(self, mock_httpx_client):
        """URLs from _BLOCKED_DOMAINS are skipped without fetching."""
        mock_httpx_client.get = AsyncMock()

        config = ResearchConfig(
            topic="test",
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=["http://g2.com/products", "http://www.capterra.com/reviews"],
        )

        with patch("src.ingestion.web.httpx.AsyncClient", return_value=mock_httpx_client):
            collector = WebCollector()
            docs, failed, blocked = asyncio.run(collector.collect(config))

        assert docs == []
        assert failed == []
        assert blocked == 2
        mock_httpx_client.get.assert_not_called()

    def test_is_blocked_domain(self):
        """_is_blocked_domain correctly matches domains and subdomains."""
        from src.ingestion.web import _is_blocked_domain

        assert _is_blocked_domain("https://g2.com/page") is True
        assert _is_blocked_domain("https://www.g2.com/page") is True
        assert _is_blocked_domain("https://capterra.com") is True
        assert _is_blocked_domain("https://reddit.com/r/python") is True
        assert _is_blocked_domain("https://example.com") is False
        assert _is_blocked_domain("https://mysite.com/g2.com") is False

    def test_random_headers_keys(self):
        """_random_headers returns all required browser headers."""
        from src.ingestion.web import _random_headers

        headers = _random_headers()
        required = {"User-Agent", "Accept", "Accept-Language", "Accept-Encoding",
                    "Sec-Fetch-Dest", "Sec-Fetch-Mode", "Sec-Fetch-Site"}
        assert required.issubset(headers.keys())
        assert "Mozilla" in headers["User-Agent"]


# ---------------------------------------------------------------------------
# SlidingWindowChunker tests
# ---------------------------------------------------------------------------


class TestSlidingWindowChunker:
    def test_chunk_basic(self):
        """2000-word document → ~5 chunks with default params (500w, 100 overlap)."""
        doc = Document(
            url="http://example.com",
            title="Test Doc",
            content=" ".join(f"word{i}" for i in range(2000)),
        )
        chunker = SlidingWindowChunker(window_size=500, overlap=100)
        chunks = chunker.chunk(doc)

        assert len(chunks) == 5
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_no_empty(self):
        """No empty chunks produced."""
        doc = Document(
            url="http://example.com",
            title="Test",
            content="short text here",
        )
        chunker = SlidingWindowChunker(window_size=500, overlap=100)
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        assert all(len(c.text.strip()) > 0 for c in chunks)

    def test_chunk_preserves_source(self):
        """Chunks carry source_url and source_title from Document."""
        doc = Document(
            url="http://example.com/page",
            title="My Title",
            content=" ".join(["word"] * 1000),
        )
        chunker = SlidingWindowChunker()
        chunks = chunker.chunk(doc)

        for c in chunks:
            assert c.source_url == "http://example.com/page"
            assert c.source_title == "My Title"

    def test_chunk_empty_document(self):
        """Empty content → no chunks."""
        doc = Document(url="http://x.com", title="Empty", content="")
        chunker = SlidingWindowChunker()
        assert chunker.chunk(doc) == []

    def test_chunk_overlap_works(self):
        """Adjacent chunks share overlapping words."""
        words = [f"w{i}" for i in range(100)]
        doc = Document(
            url="http://x.com",
            title="T",
            content=" ".join(words),
        )
        chunker = SlidingWindowChunker(window_size=60, overlap=20)
        chunks = chunker.chunk(doc)

        assert len(chunks) >= 2
        words_0 = set(chunks[0].text.split())
        words_1 = set(chunks[1].text.split())
        overlap = words_0 & words_1
        assert len(overlap) > 0


# ---------------------------------------------------------------------------
# Indexer tests (mocked ChromaDB)
# ---------------------------------------------------------------------------


class TestIndexer:
    def test_index_creates_collection(self):
        """Indexer creates collection and adds chunks."""
        with patch("src.ingestion.indexer.chromadb") as mock_chroma, \
             patch("src.ingestion.indexer.SentenceTransformerEmbeddingFunction"):
            mock_collection = MagicMock()
            mock_collection.count.return_value = 5
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chroma.PersistentClient.return_value = mock_client

            from src.ingestion.indexer import Indexer

            indexer = Indexer(chroma_path="/tmp/test_chroma", model_name="test-model")
            chunks = [
                Chunk(text=f"chunk {i}", source_url="http://x.com", source_title="X")
                for i in range(5)
            ]
            session_id = uuid4()
            count = indexer.index(chunks, session_id)

            assert count == 5
            mock_client.get_or_create_collection.assert_called_once()
            mock_collection.add.assert_called_once()

    def test_index_batches_large_input(self):
        """Chunks > 100 are split into batches."""
        with patch("src.ingestion.indexer.chromadb") as mock_chroma, \
             patch("src.ingestion.indexer.SentenceTransformerEmbeddingFunction"):
            mock_collection = MagicMock()
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chroma.PersistentClient.return_value = mock_client

            from src.ingestion.indexer import Indexer

            indexer = Indexer(chroma_path="/tmp/test", model_name="m")
            chunks = [
                Chunk(text=f"c{i}", source_url="http://x.com", source_title="X")
                for i in range(250)
            ]
            count = indexer.index(chunks, uuid4())

            assert count == 250
            assert mock_collection.add.call_count == 3  # 100+100+50

"""ScoutPipeline — orchestrator connecting all components."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from loguru import logger

from src.chunking.sliding_window import SlidingWindowChunker
from src.config import (
    ResearchConfig,
    ResearchPackage,
    ResearchSession,
    SessionStatus,
    settings,
)
from src.ingestion.indexer import Indexer
from src.ingestion.playwright_fetcher import PlaywrightFetcher
from src.ingestion.web import WebCollector
from src.llm.anthropic_briefer import AnthropicBriefer
from src.retrieval.context_builder import ContextBuilder
from src.retrieval.reranker import Reranker
from src.retrieval.searcher import Searcher
from src.storage.session_store import SessionStore


class ScoutPipeline:
    """Main pipeline: index → search → brief."""

    def __init__(self) -> None:
        chroma = str(settings.chroma_path)
        model = settings.embedding_model

        self._collector = WebCollector()
        self._chunker = SlidingWindowChunker()
        self._indexer = Indexer(chroma_path=chroma, model_name=model)
        self._searcher = Searcher(chroma_path=chroma, model_name=model)
        self._reranker = Reranker()
        self._context_builder = ContextBuilder()
        self._briefer = (
            AnthropicBriefer(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )
        self._session_store = SessionStore(dsn=settings.postgres_dsn)
        self._initialized = False

    async def _ensure_init(self) -> None:
        if not self._initialized:
            await self._session_store.init()
            self._initialized = True

    # ------------------------------------------------------------------
    # scout_index
    # ------------------------------------------------------------------

    async def index(self, config: ResearchConfig) -> tuple[ResearchSession, list[str], int]:
        """Collect, chunk, and index documents. Returns (session, failed_urls, blocked_count)."""
        await self._ensure_init()

        # 1. Check cache first
        existing = await self._session_store.find_similar(
            topic=config.topic,
            max_age_hours=config.cache_ttl_hours,
        )
        if existing:
            logger.info(
                "Найдена кэшированная сессия {} для темы '{}'",
                existing.id, config.topic,
            )
            return existing, [], 0

        # 2. Full pipeline
        session = ResearchSession(config=config, status=SessionStatus.INDEXING)
        await self._session_store.save(session)
        failed_urls: list[str] = []
        blocked_count: int = 0

        try:
            docs, failed_urls, blocked_count = await self._collector.collect(config)
            session.documents_count = len(docs)

            chunks = []
            for doc in docs:
                chunks.extend(self._chunker.chunk(doc))

            indexed = self._indexer.index(chunks, session.id)
            session.chunks_count = indexed
            session.status = SessionStatus.READY
            session.completed_at = datetime.utcnow()

            logger.info(
                "Session {} ready: {} docs, {} chunks, {} failed, {} blocked",
                session.id, session.documents_count, session.chunks_count,
                len(failed_urls), blocked_count,
            )
        except Exception as exc:
            session.status = SessionStatus.FAILED
            session.error = str(exc)
            logger.error("Index failed for session {}: {}", session.id, exc)
        finally:
            await PlaywrightFetcher.close()
            await self._session_store.save(session)

        return session, failed_urls, blocked_count

    # ------------------------------------------------------------------
    # scout_search
    # ------------------------------------------------------------------

    async def search(
        self,
        session_id: UUID,
        query: str,
        top_k: int = 10,
    ) -> ResearchPackage:
        """Search indexed chunks and build ResearchPackage."""
        await self._ensure_init()

        session = await self._session_store.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")

        # Расширенный захват: берём top-50 кандидатов вместо top_k
        # Реранкер отберёт лучшие top_k из них
        candidates_k = max(top_k * 5, 50)

        candidates = self._searcher.search(
            query=query,
            session_id=session_id,
            top_k=candidates_k,
            min_similarity=session.config.min_similarity,
        )

        # Реранкинг: CrossEncoder переоценивает кандидатов, возвращает top_k
        results = self._reranker.rerank(query=query, results=candidates, top_k=top_k)

        return self._context_builder.build(
            session=session,
            query=query,
            results=results,
            total_in_index=session.chunks_count,
        )

    # ------------------------------------------------------------------
    # scout_brief
    # ------------------------------------------------------------------

    async def brief(
        self,
        session_id: UUID,
        query: str,
        top_k: int = 10,
    ) -> dict:
        """Search + generate LLM brief."""
        package = await self.search(session_id, query, top_k)

        if not self._briefer:
            return {
                "brief": None,
                "sources_used": len(package.results),
                "model": "none",
                "tokens_used": None,
                "error": "No API key configured",
            }

        context = "\n\n---\n\n".join(
            f"[{r.source_title}] ({r.source_url})\n{r.text}"
            for r in package.results
        )

        result = await self._briefer.generate_brief(context, package.topic)
        result["sources_used"] = len(package.results)
        return result

    # ------------------------------------------------------------------
    # scout_list_sessions
    # ------------------------------------------------------------------

    async def list_sessions(self, limit: int = 10) -> list[dict]:
        """List recent research sessions."""
        await self._ensure_init()
        sessions = await self._session_store.list_recent(limit)
        return [
            {
                "id": str(s.id),
                "topic": s.config.topic,
                "status": s.status.value,
                "documents_count": s.documents_count,
                "chunks_count": s.chunks_count,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ]

    async def get_session(self, session_id: UUID) -> ResearchSession | None:
        await self._ensure_init()
        return await self._session_store.get(session_id)

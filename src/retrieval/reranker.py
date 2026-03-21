"""CrossEncoder reranker — second-stage ranking over ChromaDB candidates."""

from __future__ import annotations

import asyncio
import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from loguru import logger

from src.config import SearchResult

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"


class Reranker:
    """Rerank search results using a CrossEncoder model."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None
        self._lock = asyncio.Lock()   # SC-M4: защита от race при lazy load

    async def _ensure_loaded(self) -> None:
        """Thread-safe lazy load — загружаем модель только один раз."""
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:  # double-check после захвата lock
                return
            logger.info("Загружаю CrossEncoder: {}", self._model_name)
            # run_in_executor чтобы не блокировать event loop (~1-2 сек загрузки)
            loop = asyncio.get_event_loop()
            model_name = self._model_name
            self._model = await loop.run_in_executor(
                None,
                lambda: __import__(
                    "sentence_transformers", fromlist=["CrossEncoder"]
                ).CrossEncoder(model_name, local_files_only=True),
            )
            logger.info("CrossEncoder готов")

    async def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 15,
    ) -> list[SearchResult]:
        """Rerank results and return top_k. Now async for safe concurrent use."""
        if not results:
            return results

        if not _ENABLED:
            logger.debug("Реранкер отключён, возвращаю top-{}", top_k)
            return results[:top_k]

        await self._ensure_loaded()

        pairs = [(query, r.text) for r in results]

        # predict в executor — блокирующий CPU-bound вызов
        loop = asyncio.get_event_loop()
        model = self._model
        scores: list[float] = await loop.run_in_executor(
            None,
            lambda: model.predict(pairs).tolist(),
        )

        reranked = [
            SearchResult(
                chunk_id=r.chunk_id,
                text=r.text,
                source_url=r.source_url,
                source_title=r.source_title,
                similarity=round(float(score), 4),
            )
            for r, score in zip(results, scores)
        ]
        reranked.sort(key=lambda r: r.similarity, reverse=True)

        logger.info(
            "Reranker: {} кандидатов → top-{}, score range: {:.3f}..{:.3f}",
            len(results), top_k,
            reranked[0].similarity if reranked else 0,
            reranked[min(top_k, len(reranked)) - 1].similarity if reranked else 0,
        )
        return reranked[:top_k]

"""CrossEncoder reranker — second-stage ranking over ChromaDB candidates."""

from __future__ import annotations

import os

from loguru import logger

from src.config import SearchResult

# Модель: лёгкая, ~80MB, хорошо работает на английском и неплохо на русском
_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ENV-флаг: выключить для быстрых тестов (RERANKER_ENABLED=false)
_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"


class Reranker:
    """Rerank search results using a CrossEncoder model.

    CrossEncoder scores query-document pairs directly — more accurate than
    cosine similarity, but slower (O(n) inference calls vs O(1) for bi-encoder).
    Use as a second stage over a small candidate set (top-50), not the full index.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # ленивая загрузка при первом вызове

    def _ensure_loaded(self) -> None:
        """Загрузить модель при первом обращении."""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info("Загружаю CrossEncoder модель: {}", self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("CrossEncoder готов")

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 15,
    ) -> list[SearchResult]:
        """Rerank results and return top_k with updated similarity scores.

        If RERANKER_ENABLED=false or results list is empty — returns results as-is
        (trimmed to top_k). This allows graceful degradation without reranking.

        Note: after reranking, the similarity field contains CrossEncoder logits
        (not cosine similarity). Values can be negative and are not bounded to [0,1].
        Only the relative ordering matters for ContextBuilder.
        """
        if not results:
            return results

        if not _ENABLED:
            logger.debug("Реранкер отключён (RERANKER_ENABLED=false), возвращаю top-{}", top_k)
            return results[:top_k]

        self._ensure_loaded()

        # CrossEncoder принимает список пар (query, document_text)
        # Проверить имя поля текста в SearchResult — должно быть .text
        pairs = [(query, r.text) for r in results]

        # predict() возвращает ndarray[float] — raw logits, не нормализованы
        scores: list[float] = self._model.predict(pairs).tolist()

        # Обновляем similarity в SearchResult и сортируем по новому score
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

"""Semantic search over ChromaDB vector store."""

from __future__ import annotations

from uuid import UUID

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from loguru import logger

from src.config import SearchResult


class SessionNotFoundError(Exception):
    """Raised when a ChromaDB collection for a session does not exist."""


class Searcher:
    """Search indexed chunks by semantic similarity."""

    def __init__(self, chroma_path: str, model_name: str):
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=model_name)

    def search(
        self,
        query: str,
        session_id: UUID,
        top_k: int = 10,
        min_similarity: float = 0.60,
    ) -> list[SearchResult]:
        collection_name = f"session_{session_id.hex}"

        try:
            collection = self._client.get_collection(
                name=collection_name,
                embedding_function=self._ef,
            )
        except Exception:
            raise SessionNotFoundError(
                f"Collection '{collection_name}' not found for session {session_id}"
            )

        raw = collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        results: list[SearchResult] = []
        if not raw["ids"] or not raw["ids"][0]:
            return results

        ids = raw["ids"][0]
        documents = raw["documents"][0] if raw["documents"] else [""] * len(ids)
        distances = raw["distances"][0] if raw["distances"] else [0.0] * len(ids)
        metadatas = raw["metadatas"][0] if raw["metadatas"] else [{}] * len(ids)

        for chunk_id, text, distance, meta in zip(ids, documents, distances, metadatas):
            similarity = 1.0 / (1.0 + distance)
            if similarity < min_similarity:
                continue
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    text=text,
                    source_url=meta.get("source_url", ""),
                    source_title=meta.get("source_title", ""),
                    similarity=round(similarity, 4),
                )
            )

        results.sort(key=lambda r: r.similarity, reverse=True)
        logger.info(
            "Search '{}' in '{}': {} results (min_sim={})",
            query, collection_name, len(results), min_similarity,
        )
        return results

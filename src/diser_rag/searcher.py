"""Diser RAG — semantic search over ChromaDB index."""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from loguru import logger

from . import config


@dataclass
class SearchResult:
    text: str
    brief_id: str
    topic: str
    swarm: str
    domain: str
    section: str
    source: str
    score: float

    @property
    def similarity(self) -> float:
        return 1 / (1 + self.score)


class Searcher:
    def __init__(self):
        path = config.CHROMA_PATH
        if not Path(path).exists():
            Path(path).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=config.EMBEDDING_MODEL)
        self._collection = self._client.get_or_create_collection(
            name=config.COLLECTION,
            embedding_function=self._ef,
            metadata={"embedding_model": config.EMBEDDING_MODEL},
        )
        logger.info(f"Searcher ready: {self._collection.count()} chunks in '{config.COLLECTION}'")

    def reload(self):
        """Reload collection (after indexing)."""
        self._collection = self._client.get_or_create_collection(
            name=config.COLLECTION,
            embedding_function=self._ef,
        )

    def search(
        self,
        query: str,
        top_k: int | None = None,
        domain: str | None = None,
        swarm: str | None = None,
    ) -> list[SearchResult]:
        top_k = top_k or config.TOP_K
        count = self._collection.count()
        if count == 0:
            return []

        where: dict | None = None
        if domain and swarm:
            where = {"$and": [{"domain": domain}, {"swarm": swarm}]}
        elif domain:
            where = {"domain": domain}
        elif swarm:
            where = {"swarm": swarm}

        kwargs: dict = {
            "query_texts": [query],
            "n_results": min(top_k, count),
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        documents = raw["documents"][0] if raw["documents"] else []
        metadatas = raw["metadatas"][0] if raw["metadatas"] else []
        distances = raw["distances"][0] if raw["distances"] else []

        results = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            results.append(SearchResult(
                text=doc,
                brief_id=meta.get("brief_id", ""),
                topic=meta.get("topic", ""),
                swarm=meta.get("swarm", ""),
                domain=meta.get("domain", ""),
                section=meta.get("section", ""),
                source=meta.get("source", ""),
                score=dist,
            ))

        return results

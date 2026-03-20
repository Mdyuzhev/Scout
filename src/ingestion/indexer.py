"""Indexer — batch-index chunks into ChromaDB."""

from __future__ import annotations

from uuid import UUID

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from loguru import logger

from src.config import Chunk

_BATCH_SIZE = 100


def _make_chroma_client(
    chroma_path: str,
    mode: str = "local",
    host: str = "localhost",
    port: int = 8000,
) -> chromadb.ClientAPI:
    """Create ChromaDB client: PersistentClient (local) or HttpClient (server).

    For server mode, retries connection up to 5 times (ChromaDB may still be starting).
    """
    if mode == "server":
        import time
        for attempt in range(5):
            try:
                return chromadb.HttpClient(host=host, port=port)
            except Exception as e:
                if attempt < 4:
                    logger.warning("ChromaDB connect attempt {}/5 failed: {}, retrying in 3s...", attempt + 1, e)
                    time.sleep(3)
                else:
                    raise
    return chromadb.PersistentClient(path=chroma_path)


class Indexer:
    """Create and populate ChromaDB collections from chunks."""

    def __init__(
        self,
        chroma_path: str,
        model_name: str,
        chroma_mode: str = "local",
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
    ):
        self._client = _make_chroma_client(chroma_path, chroma_mode, chroma_host, chroma_port)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=model_name)

    def index(self, chunks: list[Chunk], session_id: UUID) -> int:
        """Index chunks into a session-scoped collection. Returns count indexed."""
        collection_name = f"session_{session_id.hex}"
        collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
        )

        total = 0
        for i in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[i : i + _BATCH_SIZE]
            collection.add(
                ids=[c.id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[
                    {
                        "source_url": c.source_url,
                        "source_title": c.source_title,
                        **c.metadata,
                    }
                    for c in batch
                ],
            )
            total += len(batch)

        logger.info(
            "Indexed {} chunks into collection '{}'", total, collection_name
        )
        return total

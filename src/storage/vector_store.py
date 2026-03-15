"""ChromaDB vector store wrapper."""

from __future__ import annotations


class VectorStore:
    """Manage ChromaDB collections for document chunks."""

    async def add_chunks(self, chunks: list[dict]) -> int:
        # TODO: implement in SC-003
        raise NotImplementedError("VectorStore not yet implemented")

    async def query(self, embedding: list[float], top_k: int = 10) -> list[dict]:
        # TODO: implement in SC-004
        raise NotImplementedError("VectorStore.query not yet implemented")

"""Semantic search over ChromaDB vector store."""

from __future__ import annotations


class Searcher:
    """Search indexed chunks by semantic similarity."""

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        # TODO: implement in SC-004
        raise NotImplementedError("Searcher not yet implemented")

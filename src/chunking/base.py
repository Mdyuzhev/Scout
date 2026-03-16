"""Base interface for text chunking."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.config import Chunk, Document


class BaseChunker(ABC):
    """Abstract base for text chunkers."""

    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]:
        """Split document into chunks."""
        ...

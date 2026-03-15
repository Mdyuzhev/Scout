"""Base interface for text chunking."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class Chunk(BaseModel):
    """A single text chunk with metadata."""

    text: str
    source: str
    chunk_index: int
    metadata: dict = {}


class BaseChunker(ABC):
    """Abstract base for text chunkers."""

    @abstractmethod
    def chunk(self, text: str, source: str) -> list[Chunk]:
        """Split text into chunks."""
        ...

"""Base interface for data ingestion sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from pydantic import BaseModel


class Document(BaseModel):
    """Raw document collected from a source."""

    source: str
    url: str | None = None
    title: str = ""
    content: str = ""
    metadata: dict = {}


class BaseCollector(ABC):
    """Abstract base for all data collectors."""

    @abstractmethod
    async def collect(self, source: str) -> AsyncIterator[Document]:
        """Yield documents from the given source."""
        ...

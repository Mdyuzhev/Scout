"""Base interface for data ingestion sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.config import Document, ResearchConfig


class BaseCollector(ABC):
    """Abstract base for all data collectors."""

    @abstractmethod
    async def collect(self, config: ResearchConfig) -> tuple[list[Document], list[str], int]:
        """Собрать документы согласно конфигу.

        Returns:
            (documents, failed_urls, blocked_count) — документы, упавшие URL и кол-во заблокированных.
        """
        ...

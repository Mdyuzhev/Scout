"""Base interface for LLM briefers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseBriefer(ABC):
    """Abstract base for LLM-based brief generation."""

    @abstractmethod
    async def generate_brief(self, context: str, topic: str) -> str:
        """Generate a research brief from context."""
        ...

"""Build research_package from search results."""

from __future__ import annotations


class ContextBuilder:
    """Assemble top-N chunks into a research package."""

    def build(self, chunks: list[dict], topic: str) -> dict:
        # TODO: implement in SC-004
        raise NotImplementedError("ContextBuilder not yet implemented")

"""Web data collector — httpx + BeautifulSoup4."""

from __future__ import annotations

from typing import AsyncIterator

from .base import BaseCollector, Document


class WebCollector(BaseCollector):
    """Collect documents from web URLs."""

    async def collect(self, source: str) -> AsyncIterator[Document]:
        # TODO: implement in SC-003
        raise NotImplementedError("WebCollector not yet implemented")
        yield  # noqa: make this a generator

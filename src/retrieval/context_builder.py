"""Build ResearchPackage from search results."""

from __future__ import annotations

from collections import defaultdict

from src.config import ResearchPackage, ResearchSession, SearchResult

_MAX_PER_SOURCE = 3


class ContextBuilder:
    """Assemble search results into a deduplicated ResearchPackage."""

    def build(
        self,
        session: ResearchSession,
        query: str,
        results: list[SearchResult],
        total_in_index: int,
    ) -> ResearchPackage:
        # Sort by similarity descending
        sorted_results = sorted(results, key=lambda r: r.similarity, reverse=True)

        # Deduplicate: max _MAX_PER_SOURCE chunks per source_url
        source_counts: dict[str, int] = defaultdict(int)
        deduplicated: list[SearchResult] = []
        for r in sorted_results:
            if source_counts[r.source_url] < _MAX_PER_SOURCE:
                deduplicated.append(r)
                source_counts[r.source_url] += 1

        return ResearchPackage(
            session_id=session.id,
            topic=session.config.topic,
            query=query,
            results=deduplicated,
            total_chunks_in_index=total_in_index,
        )

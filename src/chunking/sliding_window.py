"""Sliding window chunker — splits documents into overlapping word-based chunks."""

from __future__ import annotations

from src.config import Chunk, Document

from .base import BaseChunker


class SlidingWindowChunker(BaseChunker):
    """Split text using sliding window with word-level overlap.

    Default parameters tuned for paraphrase-multilingual-MiniLM-L12-v2
    which works well with 200-600 word fragments.
    """

    def __init__(self, window_size: int = 500, overlap: int = 100):
        self.window_size = window_size
        self.overlap = overlap

    def chunk(self, doc: Document) -> list[Chunk]:
        words = doc.content.split()
        if not words:
            return []

        step = self.window_size - self.overlap
        if step <= 0:
            step = 1

        chunks: list[Chunk] = []
        idx = 0
        chunk_index = 0

        while idx < len(words):
            window = words[idx : idx + self.window_size]
            text = " ".join(window)

            chunks.append(
                Chunk(
                    text=text,
                    source_url=doc.url,
                    source_title=doc.title,
                    metadata={"chunk_index": chunk_index},
                )
            )
            chunk_index += 1
            idx += step

        return chunks

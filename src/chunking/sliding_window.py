"""Sliding window chunker."""

from __future__ import annotations

from .base import BaseChunker, Chunk


class SlidingWindowChunker(BaseChunker):
    """Split text using sliding window with overlap."""

    def __init__(self, window_size: int = 512, overlap: int = 64):
        self.window_size = window_size
        self.overlap = overlap

    def chunk(self, text: str, source: str) -> list[Chunk]:
        # TODO: implement in SC-003
        raise NotImplementedError("SlidingWindowChunker not yet implemented")

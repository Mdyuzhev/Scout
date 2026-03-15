"""Anthropic-based briefer using Claude Haiku."""

from __future__ import annotations

from .base import BaseBriefer


class AnthropicBriefer(BaseBriefer):
    """Generate research briefs using Anthropic Claude."""

    async def generate_brief(self, context: str, topic: str) -> str:
        # TODO: implement in SC-005
        raise NotImplementedError("AnthropicBriefer not yet implemented")

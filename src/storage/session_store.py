"""PostgreSQL session store for research sessions."""

from __future__ import annotations


class SessionStore:
    """Persist research sessions and their metadata."""

    async def create_session(self, config: dict) -> str:
        # TODO: implement in SC-006
        raise NotImplementedError("SessionStore not yet implemented")

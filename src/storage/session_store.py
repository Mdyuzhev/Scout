"""PostgreSQL session store for research sessions."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import asyncpg
from loguru import logger

from src.config import ResearchConfig, ResearchSession, SessionStatus

_MIGRATION_FILE = Path(__file__).resolve().parent.parent.parent / "migrations" / "001_initial.sql"


class SessionStore:
    """Persist research sessions in PostgreSQL."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        """Create connection pool and run migration."""
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=2,
            max_size=20,
            command_timeout=30.0,   # таймаут на отдельный SQL-запрос
        )
        if _MIGRATION_FILE.exists():
            sql = _MIGRATION_FILE.read_text(encoding="utf-8")
            async with self._pool.acquire() as conn:
                await conn.execute(sql)
            logger.info("Migration applied: {}", _MIGRATION_FILE.name)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def save(self, session: ResearchSession) -> None:
        """Upsert session into database."""
        config_json = session.config.model_dump_json()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO research_sessions
                    (id, topic, config, status, documents_count, chunks_count, brief, error, created_at, completed_at)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    documents_count = EXCLUDED.documents_count,
                    chunks_count = EXCLUDED.chunks_count,
                    brief = EXCLUDED.brief,
                    error = EXCLUDED.error,
                    completed_at = EXCLUDED.completed_at
                """,
                session.id,
                session.config.topic,
                config_json,
                session.status.value,
                session.documents_count,
                session.chunks_count,
                None,  # brief stored separately
                session.error,
                session.created_at,
                session.completed_at,
            )

    async def get(self, session_id: UUID) -> ResearchSession | None:
        """Get session by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM research_sessions WHERE id = $1",
                session_id,
            )
        if row is None:
            return None
        return self._row_to_session(row)

    async def find_similar(
        self,
        topic: str,
        max_age_hours: int = 24,
    ) -> ResearchSession | None:
        """Find a recent completed session with similar topic via tsvector."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM research_sessions
                WHERE status = 'ready'
                  AND documents_count > 0
                  AND created_at > NOW() - make_interval(hours => $2)
                  AND search_vector @@ plainto_tsquery('russian', $1)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                topic,
                max_age_hours,
            )
        if row is None:
            return None
        return self._row_to_session(row)

    async def list_recent(self, limit: int = 20) -> list[ResearchSession]:
        """List recent sessions ordered by creation date."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM research_sessions ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [self._row_to_session(r) for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: asyncpg.Record) -> ResearchSession:
        config_data = row["config"]
        if isinstance(config_data, str):
            config_data = json.loads(config_data)
        return ResearchSession(
            id=row["id"],
            config=ResearchConfig(**config_data),
            status=SessionStatus(row["status"]),
            documents_count=row["documents_count"] or 0,
            chunks_count=row["chunks_count"] or 0,
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )

"""PostgreSQL-backed async job store — shared across MCP nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg
from loguru import logger

_MIGRATION_FILE = Path(__file__).resolve().parent.parent.parent / "migrations" / "002_async_jobs.sql"

# Columns that map 1-to-1 between dict keys and DB columns
_COLUMNS = (
    "job_id", "topic", "query", "model", "status", "stage", "message",
    "total_urls", "auto_collected", "test_docs", "test_chunks", "test_failed",
    "session_id", "documents_count", "chunks_count", "failed_count",
    "blocked_count", "brief", "tokens_used", "sources_used", "saved_to", "error",
)


class JobStore:
    """Persist async research jobs in PostgreSQL."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        if _MIGRATION_FILE.exists():
            sql = _MIGRATION_FILE.read_text(encoding="utf-8")
            async with self._pool.acquire() as conn:
                await conn.execute(sql)
            logger.info("Migration applied: {}", _MIGRATION_FILE.name)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create(self, job: dict[str, Any]) -> None:
        """Insert a new job."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO async_jobs (job_id, topic, query, model, status, stage, message, total_urls, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                """,
                job["job_id"], job["topic"], job["query"], job.get("model"),
                job.get("status", "running"), job.get("stage", "queued"),
                job.get("message"), job.get("total_urls", 0),
            )

    async def update(self, job_id: str, **fields: Any) -> None:
        """Update specific fields of a job."""
        if not fields:
            return
        sets = []
        vals = []
        idx = 1
        for key, val in fields.items():
            if key in _COLUMNS and key != "job_id":
                sets.append(f"{key} = ${idx}")
                vals.append(val)
                idx += 1
        sets.append(f"updated_at = NOW()")
        vals.append(job_id)
        sql = f"UPDATE async_jobs SET {', '.join(sets)} WHERE job_id = ${idx}"
        async with self._pool.acquire() as conn:
            await conn.execute(sql, *vals)

    async def get(self, job_id: str) -> dict[str, Any] | None:
        """Get job by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM async_jobs WHERE job_id = $1", job_id,
            )
        if row is None:
            return None
        return self._row_to_dict(row)

    async def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent jobs."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM async_jobs ORDER BY created_at DESC LIMIT $1", limit,
            )
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
        d = dict(row)
        for key in ("created_at", "updated_at"):
            if key in d and d[key] is not None:
                d[key] = d[key].isoformat()
        return d

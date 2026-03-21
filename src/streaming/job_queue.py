"""Job Queue — global task queue via Redis Streams (SC-037)."""
from __future__ import annotations

import json

from loguru import logger

from src.streaming.redis_client import get_redis

QUEUE_KEY = "scout:queue"
QUEUE_GROUP = "workers"
QUEUE_TTL = 86400 * 7  # 7 days


async def ensure_queue() -> None:
    """Initialize queue stream and consumer group (idempotent)."""
    r = await get_redis()
    try:
        await r.xgroup_create(QUEUE_KEY, QUEUE_GROUP, id="0", mkstream=True)
    except Exception:
        pass  # group already exists
    await r.expire(QUEUE_KEY, QUEUE_TTL)


async def enqueue_job(job_params: dict) -> str:
    """Put a job into the queue. Returns msg_id."""
    r = await get_redis()
    await ensure_queue()
    msg_id = await r.xadd(QUEUE_KEY, {"payload": json.dumps(job_params)})
    logger.info(
        "job_queue: enqueued job_id={} msg_id={}",
        job_params.get("job_id", "?")[:8], msg_id,
    )
    return msg_id


async def dequeue_job(consumer_name: str, block_ms: int = 0):
    """
    Take next job from queue (blocking).
    block_ms=0 — block indefinitely.
    Returns (msg_id, job_params) or None on timeout.
    """
    r = await get_redis()
    result = await r.xreadgroup(
        QUEUE_GROUP,
        consumer_name,
        {QUEUE_KEY: ">"},
        count=1,
        block=block_ms,
    )
    if not result:
        return None
    _, messages = result[0]
    msg_id, fields = messages[0]
    job_params = json.loads(fields["payload"])
    logger.info(
        "job_queue: dequeued job_id={} by consumer={}",
        job_params.get("job_id", "?")[:8], consumer_name,
    )
    return msg_id, job_params


async def ack_job(msg_id: str) -> None:
    """Acknowledge job completion."""
    r = await get_redis()
    await r.xack(QUEUE_KEY, QUEUE_GROUP, msg_id)


async def requeue_failed(consumer_name: str, min_idle_ms: int = 300_000) -> int:
    """
    Reclaim jobs stuck in PEL longer than min_idle_ms.
    Call on worker startup to pick up abandoned tasks from crashed nodes.
    Returns number of reclaimed jobs.
    """
    r = await get_redis()
    try:
        result = await r.xautoclaim(
            QUEUE_KEY,
            QUEUE_GROUP,
            consumer_name,
            min_idle_time=min_idle_ms,
            start_id="0-0",
            count=10,
        )
        claimed = result[1] if result and len(result) > 1 else []
        if claimed:
            logger.info(
                "job_queue: reclaimed {} abandoned jobs for consumer {}",
                len(claimed), consumer_name,
            )
        return len(claimed)
    except Exception as exc:
        logger.warning("job_queue: requeue_failed error: {}", exc)
        return 0


async def queue_length() -> int:
    """Count jobs waiting in queue (not yet taken by workers)."""
    r = await get_redis()
    try:
        pending = await r.xpending(QUEUE_KEY, QUEUE_GROUP)
        total = await r.xlen(QUEUE_KEY)
        pending_count = pending.get("pending", 0) if isinstance(pending, dict) else 0
        return max(0, total - pending_count)
    except Exception:
        return 0

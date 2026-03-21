"""URL Stream — producer/consumer для URL батчей между collector и indexer."""
from __future__ import annotations

from uuid import UUID
from loguru import logger
from src.streaming.redis_client import get_redis

# Ключи
def url_stream_key(job_id: str) -> str:
    return f"scout:urls:{job_id}"

def ready_stream_key(job_id: str) -> str:
    return f"scout:ready:{job_id}"

URL_STREAM_TTL = 7200    # 2 часа
READY_STREAM_TTL = 86400 # 24 часа
CONSUMER_GROUP = "indexers"
BRIEF_GROUP = "briefers"


async def ensure_stream_groups(job_id: str) -> None:
    """Создать consumer groups для job. Вызывать на producer стороне перед публикацией."""
    r = await get_redis()
    for key, group in [
        (url_stream_key(job_id), CONSUMER_GROUP),
        (ready_stream_key(job_id), BRIEF_GROUP),
    ]:
        try:
            await r.xgroup_create(key, group, id="0", mkstream=True)
        except Exception:
            pass  # group уже существует — ок
    # TTL на стримы
    await r.expire(url_stream_key(job_id), URL_STREAM_TTL)
    await r.expire(ready_stream_key(job_id), READY_STREAM_TTL)


async def publish_url_batch(job_id: str, urls: list[str], batch_label: str) -> None:
    """Опубликовать батч URL в стрим."""
    r = await get_redis()
    await r.xadd(
        url_stream_key(job_id),
        {
            "type": "batch",
            "batch_label": batch_label,
            "urls": "\n".join(urls),
            "count": str(len(urls)),
        },
    )
    logger.info("url_stream {}: published batch {} ({} URLs)", job_id[:8], batch_label, len(urls))


async def publish_url_eof(job_id: str, total_urls: int) -> None:
    """Опубликовать маркер завершения — все батчи отправлены."""
    r = await get_redis()
    await r.xadd(
        url_stream_key(job_id),
        {"type": "eof", "total_urls": str(total_urls)},
    )
    logger.info("url_stream {}: EOF published (total={})", job_id[:8], total_urls)


async def publish_url_abort(job_id: str, reason: str) -> None:
    """Опубликовать abort — тест не прошёл, останавливаем консьюмеры."""
    r = await get_redis()
    await r.xadd(
        url_stream_key(job_id),
        {"type": "abort", "reason": reason},
    )
    logger.warning("url_stream {}: ABORT published: {}", job_id[:8], reason)


async def read_url_batch(job_id: str, consumer_name: str, block_ms: int = 5000):
    """
    Читать следующее сообщение из URL стрима (consumer group).
    Возвращает (msg_id, data_dict) или None если таймаут.
    """
    r = await get_redis()
    result = await r.xreadgroup(
        CONSUMER_GROUP,
        consumer_name,
        {url_stream_key(job_id): ">"},
        count=1,
        block=block_ms,
    )
    if not result:
        return None
    # result = [(stream_key, [(msg_id, fields), ...])]
    _, messages = result[0]
    msg_id, fields = messages[0]
    return msg_id, fields


async def ack_url_message(job_id: str, msg_id: str) -> None:
    r = await get_redis()
    await r.xack(url_stream_key(job_id), CONSUMER_GROUP, msg_id)


async def publish_index_ready(
    job_id: str,
    session_id: UUID,
    documents_count: int,
    chunks_count: int,
    failed_count: int,
) -> None:
    """Опубликовать сигнал готовности индекса → триггер для briefer."""
    r = await get_redis()
    await r.xadd(
        ready_stream_key(job_id),
        {
            "type": "ready",
            "session_id": str(session_id),
            "documents_count": str(documents_count),
            "chunks_count": str(chunks_count),
            "failed_count": str(failed_count),
        },
    )
    logger.info(
        "ready_stream {}: published (session={}, docs={}, chunks={})",
        job_id[:8], str(session_id)[:8], documents_count, chunks_count,
    )


async def read_index_ready(job_id: str, consumer_name: str, block_ms: int = 0):
    """Читать сигнал готовности индекса (блокирующий, block_ms=0 = бесконечно)."""
    r = await get_redis()
    result = await r.xreadgroup(
        BRIEF_GROUP,
        consumer_name,
        {ready_stream_key(job_id): ">"},
        count=1,
        block=block_ms,
    )
    if not result:
        return None
    _, messages = result[0]
    msg_id, fields = messages[0]
    return msg_id, fields


async def ack_ready_message(job_id: str, msg_id: str) -> None:
    r = await get_redis()
    await r.xack(ready_stream_key(job_id), BRIEF_GROUP, msg_id)


async def cleanup_streams(job_id: str) -> None:
    """Удалить стримы после завершения job (вызывать из completed/error stage)."""
    r = await get_redis()
    for key in [url_stream_key(job_id), ready_stream_key(job_id)]:
        try:
            await r.delete(key)
        except Exception:
            pass

"""Scout MCP Server — entrypoint."""

import asyncio
import os
import traceback
from uuid import UUID, uuid4

from fastmcp import FastMCP
from loguru import logger

from src.config import DepthLevel, LLMProvider, ResearchConfig, settings
from src.pipeline import ScoutPipeline
from src.storage.job_store import JobStore

mcp = FastMCP("Scout")
pipeline = ScoutPipeline()

# PostgreSQL-backed job store (shared across MCP nodes)
_job_store = JobStore(dsn=settings.postgres_dsn)
_job_store_initialized = False


async def _ensure_job_store() -> None:
    global _job_store_initialized
    if not _job_store_initialized:
        await _job_store.init()
        _job_store_initialized = True
    # SC-037: lazy-start worker loop on first tool call
    await _ensure_worker_loop()


# ── SC-037: Worker Pool ──────────────────────────────────────────────
MAX_WORKERS_PER_NODE = settings.max_workers_per_node
_worker_semaphore: asyncio.Semaphore | None = None
_worker_started = False


def _get_worker_semaphore() -> asyncio.Semaphore:
    global _worker_semaphore
    if _worker_semaphore is None:
        _worker_semaphore = asyncio.Semaphore(MAX_WORKERS_PER_NODE)
    return _worker_semaphore


async def _ensure_worker_loop() -> None:
    """Lazy-start the worker loop (once per process)."""
    global _worker_started
    if not _worker_started and settings.redis_streaming:
        _worker_started = True
        asyncio.create_task(_worker_loop())


@mcp.tool()
async def scout_index(
    topic: str,
    depth: str = "normal",
    queries: list[str] | None = None,
    language: str = "ru",
    llm_provider: str = "anthropic",
    cache_ttl_hours: int = 24,
    source_type: str = "web",
    source_urls: list[str] | None = None,
    file_paths: list[str] | None = None,
) -> dict:
    """Index documents for a research topic.

    Three modes:
    - source_type="web" (default): search via DuckDuckGo
    - source_type="urls": fetch provided URLs directly, no search
    - source_type="files": read local files (txt, md, pdf, docx)

    For urls mode, provide source_urls (up to 200 URLs).
    For files mode, provide file_paths with absolute paths on the server.
    Set cache_ttl_hours=0 to force re-indexing.
    """
    from src.config import SourceType

    effective_urls = source_urls or []
    effective_source_type = source_type
    if source_type == "files" and file_paths:
        effective_urls = file_paths
        effective_source_type = "local_file"

    config = ResearchConfig(
        topic=topic,
        depth=DepthLevel(depth),
        queries=queries or [],
        language=language,
        llm_provider=LLMProvider(llm_provider),
        cache_ttl_hours=cache_ttl_hours,
        source_type=SourceType(effective_source_type),
        source_urls=effective_urls,
    )

    session, failed_urls, blocked_count = await pipeline.index(config)

    return {
        "session_id": str(session.id),
        "status": session.status.value,
        "documents_count": session.documents_count,
        "chunks_count": session.chunks_count,
        "failed_urls": failed_urls,
        "failed_count": len(failed_urls),
        "blocked_count": blocked_count,
        "message": (
            f"Indexed {session.documents_count} docs "
            f"({len(failed_urls)} failed, {blocked_count} blocked) for '{topic}'"
            if session.status.value == "ready"
            else f"Indexing failed: {session.error}"
        ),
    }


@mcp.tool()
async def scout_search(
    session_id: str,
    query: str,
    top_k: int = 10,
) -> dict:
    """Search indexed documents by semantic similarity.

    Returns ranked chunks with source metadata.
    """
    sid = UUID(session_id)
    package = await pipeline.search(sid, query, top_k)

    return {
        "session_id": session_id,
        "query": query,
        "results": [
            {
                "text": r.text,
                "source_url": r.source_url,
                "source_title": r.source_title,
                "similarity": r.similarity,
            }
            for r in package.results
        ],
        "total_in_index": package.total_chunks_in_index,
    }


@mcp.tool()
async def scout_brief(
    session_id: str,
    query: str,
    top_k: int = 10,
    model: str = "haiku",
) -> dict:
    """[DEPRECATED] Generate a research brief using LLM from indexed data.

    Deprecated since SC-036. Use scout_get_context() + agent LLM + scout_save_brief() instead.
    Kept for backward compatibility — works only if ANTHROPIC_API_KEY is set on server.

    Args:
        model: LLM model — "haiku" (default), "sonnet", or "opus"
    """
    logger.warning("scout_brief called — deprecated (SC-036). Use scout_get_context instead.")
    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])
    sid = UUID(session_id)
    result = await pipeline.brief(sid, query, top_k, model=llm_model)
    result["sources_used"] = result.get("sources_used", 0)
    return result


@mcp.tool()
async def scout_research(
    topic: str,
    query: str,
    source_urls: list[str] | None = None,
    auto_collect: bool = False,
    auto_collect_count: int = 150,
    top_k: int = 15,
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
) -> dict:
    """Full research pipeline in one call: index URLs → generate brief.

    Combines scout_index + scout_brief into a single atomic operation.
    The agent does not need to manage session_id between steps.

    Three modes:
    - source_urls provided: index given URLs directly
    - auto_collect=True: Haiku searches the web to find URLs, then indexes them
    - both: auto_collect adds to provided source_urls

    Args:
        topic:              Research topic description (used for indexing and history)
        query:              Research question for the brief (what to synthesize)
        source_urls:        List of URLs to fetch and index (up to 400)
        auto_collect:       If True, use Haiku web_search to find URLs automatically
        auto_collect_count: How many URLs to collect when auto_collect=True (default 150)
        top_k:              Number of top chunks to pass to LLM (default 15)
        model:              LLM model — "haiku" (fast, factual), "sonnet" (narrative),
                            "opus" (balanced, most thorough). Default: "haiku"
        language:           Source language hint for embeddings — "ru" or "en"
        save_to:            Optional path on server to save the brief as markdown,
                            e.g. "/opt/scout/results/my_brief.md"

    Returns:
        brief:              Full text of the research brief
        model:              Model used
        tokens_used:        LLM token consumption
        sources_used:       Number of unique sources in context
        session_id:         Session ID for follow-up scout_search calls
        documents_count:    Successfully indexed documents
        chunks_count:       Total indexed chunks
        failed_count:       URLs that could not be fetched
        blocked_count:      URLs skipped (bot-protection blocklist)
        auto_collected_urls: Number of URLs found via auto_collect
        saved_to:           Path where brief was saved (if save_to provided)
    """
    from src.config import SourceType

    # SC-036: auto_collect deprecated — агент собирает URL сам
    if auto_collect:
        return {
            "error": (
                "auto_collect=True is deprecated (SC-036). "
                "Use scout_create_job() + scout_push_urls() instead. "
                "Agent should collect URLs via web_search and push them to Scout."
            )
        }

    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])

    # Объединить с явно переданными URL (auto_collect убран)
    collected_urls: list[str] = []
    if False:  # auto_collect removed
        from src.ingestion.url_collector import collect_urls
        collected_urls = await collect_urls(
            topic=topic,
            language=language,
            n_urls=auto_collect_count,
        )

    # Объединить с явно переданными URL
    all_urls = list(dict.fromkeys((source_urls or []) + collected_urls))

    if not all_urls:
        return {"error": "No URLs provided and auto_collect=False"}

    # Шаг 1: индексация
    logger.info("scout_research: indexing {} URLs for '{}'", len(all_urls), topic)
    config = ResearchConfig(
        topic=topic,
        depth=DepthLevel.NORMAL,
        language=language,
        llm_provider=LLMProvider.ANTHROPIC,
        cache_ttl_hours=0,  # всегда свежая индексация
        source_type=SourceType.SPECIFIC_URLS,
        source_urls=all_urls,
    )
    session, failed_urls, blocked_count = await pipeline.index(config)

    if session.status.value != "ready" or session.documents_count == 0:
        return {
            "error": f"Indexing failed or zero documents. Status: {session.status.value}",
            "session_id": str(session.id),
            "documents_count": session.documents_count,
            "failed_count": len(failed_urls),
            "blocked_count": blocked_count,
            "auto_collected_urls": len(collected_urls),
        }

    logger.info(
        "scout_research: indexed {} docs ({} failed, {} blocked)",
        session.documents_count, len(failed_urls), blocked_count,
    )

    # SC-039: brief generation removed from server side (SC-036 agent-first)
    return {
        "brief":           None,
        "model":           None,
        "tokens_used":     None,
        "sources_used":    0,
        "session_id":      str(session.id),
        "documents_count": session.documents_count,
        "chunks_count":    session.chunks_count,
        "failed_count":    len(failed_urls),
        "blocked_count":   blocked_count,
        "auto_collected_urls": 0,
        "saved_to":        None,
        "message": (
            f"Индексация завершена: {session.documents_count} docs. "
            f"Используйте scout_get_context(session_id='{session.id}', query=...) "
            f"для получения чанков и генерации брифа."
        ),
    }


MODEL_MAP = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-6",
}

TEST_BATCH_SIZE = 10

# Имя этого узла — используется как consumer name в Redis Streams
_NODE_NAME = f"node-{os.getenv('MCP_PORT', '8020')}"


async def _run_research_job_stream(
    job_id: str,
    topic: str,
    source_urls: list[str],
    query: str,
    top_k: int,
    llm_model: str,
    language: str,
    save_to: str | None,
    auto_collect: bool = False,
    auto_collect_count: int = 150,
) -> None:
    """
    Streaming pipeline через Redis Streams.

    Стейджи:
      0. collecting_urls   → Haiku пишет батчи в URL stream по мере готовности
      1. stream_indexing   → этот узел читает батчи из URL stream и индексирует
         (параллельно: второй узел тоже читает и индексирует свои батчи)
      2. indexing_done     → все URL проиндексированы, сигнал в ready stream
      3. generating_brief  → первый свободный узел генерирует бриф
      4. completed / error
    """
    from src.config import SourceType, ResearchSession, SessionStatus
    from src.streaming.url_stream import (
        read_url_batch, ack_url_message,
        read_index_ready, ack_ready_message,
        publish_index_ready, publish_url_abort,
        cleanup_streams,
    )

    await _ensure_job_store()

    import time as _time
    _job_start = _time.monotonic()

    async def _update(stage: str, **kw):
        elapsed = round(_time.monotonic() - _job_start, 1)
        kw["stage"] = stage
        kw["elapsed_sec"] = elapsed
        await _job_store.update(job_id, **kw)
        logger.info("job {} [{}s] stream: {}", job_id[:8], elapsed, stage)

    consumer = _NODE_NAME

    try:
        # ── Stage 0: запустить сбор URL (async, не блокируем) ────────
        if auto_collect:
            await _update("collecting_urls",
                          message=f"Haiku собирает URL, узел {consumer} готов к индексации...")
            from src.ingestion.url_collector import collect_urls_streaming
            asyncio.create_task(
                collect_urls_streaming(
                    topic=topic,
                    job_id=job_id,
                    language=language,
                    n_urls=auto_collect_count,
                )
            )
        else:
            # Явный список URL — публикуем одним батчем сразу
            # Если source_urls пуст — агент передаст URL через scout_push_urls
            from src.streaming.url_stream import (
                ensure_stream_groups, publish_url_batch, publish_url_eof,
            )
            await ensure_stream_groups(job_id)
            if source_urls:
                await publish_url_batch(job_id, source_urls, "manual")
                await publish_url_eof(job_id, len(source_urls))

        # ── Stage 1: читать URL батчи из стрима и индексировать ──────
        await _update("stream_indexing",
                      message=f"Узел {consumer} читает URL stream и индексирует...")

        # Создать сессию заранее
        from uuid import uuid4 as _uuid4
        session_id = _uuid4()
        session_config = ResearchConfig(
            topic=topic,
            depth=DepthLevel.NORMAL,
            language=language,
            llm_provider=LLMProvider.ANTHROPIC,
            cache_ttl_hours=0,
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=[],
        )
        session = ResearchSession(
            id=session_id,
            config=session_config,
            status=SessionStatus.INDEXING,
        )
        await pipeline._ensure_init()
        await pipeline._session_store.save(session)

        total_docs = 0
        total_chunks = 0
        total_failed = 0
        test_passed = False
        eof_received = False

        # SC-036: agent may take time to push URLs, extend timeout
        IDLE_TIMEOUT_MS = 600_000 if not source_urls else 120_000
        consecutive_empty = 0

        while not eof_received:
            msg = await read_url_batch(job_id, consumer, block_ms=5000)

            if msg is None:
                consecutive_empty += 1
                if consecutive_empty * 5000 > IDLE_TIMEOUT_MS:
                    logger.warning(
                        "job {} stream: idle timeout, assuming all batches processed",
                        job_id[:8],
                    )
                    break
                continue

            consecutive_empty = 0
            msg_id, fields = msg
            msg_type = fields.get("type", "batch")

            if msg_type == "abort":
                await ack_url_message(job_id, msg_id)
                await _update("error", status="failed",
                              error=f"Aborted: {fields.get('reason', 'unknown')}")
                return

            if msg_type == "eof":
                await ack_url_message(job_id, msg_id)
                eof_received = True
                logger.info("job {} stream: EOF received", job_id[:8])
                continue

            if msg_type != "batch":
                await ack_url_message(job_id, msg_id)
                continue

            # Обработка батча URL
            batch_urls = [u for u in fields.get("urls", "").split("\n") if u.strip()]
            batch_label = fields.get("batch_label", "?")

            if not batch_urls:
                await ack_url_message(job_id, msg_id)
                continue

            # Тест на первых 10 URL первого батча
            if not test_passed:
                test_urls = batch_urls[:TEST_BATCH_SIZE]
                test_config = ResearchConfig(
                    topic=f"[test] {topic}",
                    depth=DepthLevel.NORMAL,
                    language=language,
                    llm_provider=LLMProvider.ANTHROPIC,
                    cache_ttl_hours=0,
                    source_type=SourceType.SPECIFIC_URLS,
                    source_urls=test_urls,
                )
                test_session, _, _ = await pipeline.index(test_config)
                if (test_session.status.value != "ready"
                        or test_session.documents_count == 0
                        or test_session.chunks_count == 0):
                    await ack_url_message(job_id, msg_id)
                    await publish_url_abort(
                        job_id,
                        f"test failed: docs={test_session.documents_count}, "
                        f"chunks={test_session.chunks_count}",
                    )
                    await _update(
                        "test_failed", status="failed",
                        error=f"Тест провален: docs={test_session.documents_count}",
                    )
                    return
                test_passed = True
                await _update("test_passed",
                              message="Тест пройден, индексирую оставшиеся батчи...")

            # Индексировать батч через append
            try:
                batch_config = ResearchConfig(
                    topic=topic,
                    depth=DepthLevel.NORMAL,
                    language=language,
                    llm_provider=LLMProvider.ANTHROPIC,
                    cache_ttl_hours=0,
                    source_type=SourceType.SPECIFIC_URLS,
                    source_urls=batch_urls,
                )
                docs, failed_urls, blocked = await pipeline._web_collector.collect(batch_config)
                chunks_list = []
                for doc in docs:
                    chunks_list.extend(pipeline._chunker.chunk(doc))

                if chunks_list:
                    indexed = pipeline._indexer.index_append(chunks_list, session_id)
                    total_chunks += indexed

                total_docs += len(docs)
                total_failed += len(failed_urls)

                session.documents_count = total_docs
                session.chunks_count = total_chunks
                await pipeline._session_store.save(session)

                await _update(
                    "stream_indexing",
                    documents_count=total_docs,
                    chunks_count=total_chunks,
                    failed_count=total_failed,
                    message=(
                        f"Батч {batch_label}: +{len(docs)} docs, "
                        f"итого {total_docs} docs / {total_chunks} chunks"
                    ),
                )

            except Exception as exc:
                logger.error("job {} batch {} indexing failed: {}", job_id[:8], batch_label, exc)
            finally:
                await ack_url_message(job_id, msg_id)

        # Финализировать сессию
        if total_chunks == 0:
            session.status = SessionStatus.FAILED
            session.error = "0 chunks after stream indexing"
            await pipeline._session_store.save(session)
            await _update("error", status="failed", error="0 chunks indexed")
            return

        session.status = SessionStatus.READY
        from datetime import datetime as _dt
        session.completed_at = _dt.utcnow()
        await pipeline._session_store.save(session)

        await _update(
            "indexing_done",
            session_id=str(session_id),
            documents_count=total_docs,
            chunks_count=total_chunks,
            failed_count=total_failed,
            message=(
                f"Индексация завершена: {total_docs} docs, "
                f"{total_chunks} chunks, {total_failed} failed."
            ),
        )

        # SC-039: brief generation removed — agent uses scout_get_context + scout_save_brief
        await _update(
            "completed",
            status="completed",
            session_id=str(session_id),
            documents_count=total_docs,
            chunks_count=total_chunks,
            failed_count=total_failed,
            message=(
                f"Индексация завершена: {total_docs} docs, {total_chunks} chunks. "
                f"Используйте scout_get_context(session_id='{session_id}') для генерации брифа."
            ),
        )

    except Exception as exc:
        tb = traceback.format_exc()
        await _update("error", status="failed", error=str(exc), traceback=tb)
        logger.error("job {} stream failed:\n{}", job_id[:8], tb)

    finally:
        await cleanup_streams(job_id)


async def _run_research_job(
    job_id: str,
    topic: str,
    source_urls: list[str],
    query: str,
    top_k: int,
    llm_model: str,
    language: str,
    save_to: str | None,
    auto_collect: bool = False,
    auto_collect_count: int = 150,
) -> None:
    """Background coroutine: (auto_collect →) test 10 URLs → full indexing → brief."""
    from src.config import SourceType

    await _ensure_job_store()

    import time as _time
    _job_start = _time.monotonic()

    async def _update(stage: str, **kw):
        elapsed = round(_time.monotonic() - _job_start, 1)
        kw["stage"] = stage
        kw["elapsed_sec"] = elapsed
        await _job_store.update(job_id, **kw)
        logger.info("job {} [{}s]: {}", job_id[:8], elapsed, stage)

    try:
        # ── Stage 0: auto_collect если запрошен ─────────────────────
        if auto_collect:
            await _update("collecting_urls",
                          message=f"Haiku собирает URL по теме '{topic}'...")
            from src.ingestion.url_collector import collect_urls as _collect
            collected_urls = await _collect(
                topic=topic, language=language, n_urls=auto_collect_count,
            )
            all_urls = list(dict.fromkeys(source_urls + collected_urls))
            await _update(
                "urls_collected",
                auto_collected=len(collected_urls),
                total_urls=len(all_urls),
                message=f"Собрано {len(collected_urls)} URL. Итого: {len(all_urls)}.",
            )
            source_urls = all_urls

        if not source_urls:
            await _update("error", status="failed", error="No URLs after auto_collect")
            return

        # ── Stage 1: test batch (first 10 URLs) ─────────────────────
        test_urls = source_urls[:TEST_BATCH_SIZE]
        await _update("test_indexing", message=f"Тест: индексация {len(test_urls)} URL из {len(source_urls)}")

        test_config = ResearchConfig(
            topic=f"[test] {topic}",
            depth=DepthLevel.NORMAL,
            language=language,
            llm_provider=LLMProvider.ANTHROPIC,
            cache_ttl_hours=0,
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=test_urls,
        )
        test_session, test_failed, _ = await pipeline.index(test_config)

        if (test_session.status.value != "ready"
                or test_session.documents_count == 0
                or test_session.chunks_count == 0):
            await _update(
                "test_failed",
                status="failed",
                error=(
                    f"Тест провален: docs={test_session.documents_count}, "
                    f"chunks={test_session.chunks_count}, "
                    f"status={test_session.status.value}"
                ),
            )
            return

        await _update(
            "test_passed",
            test_docs=test_session.documents_count,
            test_chunks=test_session.chunks_count,
            test_failed=len(test_failed),
            message=f"Тест пройден: {test_session.documents_count} docs, "
                    f"{test_session.chunks_count} chunks. Запускаю полный пул.",
        )

        # ── Stage 2: full indexing ───────────────────────────────────
        await _update("full_indexing", message=f"Индексация {len(source_urls)} URL...")

        full_config = ResearchConfig(
            topic=topic,
            depth=DepthLevel.NORMAL,
            language=language,
            llm_provider=LLMProvider.ANTHROPIC,
            cache_ttl_hours=0,
            source_type=SourceType.SPECIFIC_URLS,
            source_urls=source_urls,
        )
        session, failed_urls, blocked_count = await pipeline.index(full_config)

        if session.status.value != "ready" or session.documents_count == 0:
            await _update(
                "indexing_failed",
                status="failed",
                error=f"Индексация провалена: {session.documents_count} docs, "
                      f"{len(failed_urls)} failed",
                session_id=str(session.id),
            )
            return

        await _update(
            "indexing_done",
            session_id=str(session.id),
            documents_count=session.documents_count,
            chunks_count=session.chunks_count,
            failed_count=len(failed_urls),
            blocked_count=blocked_count,
            message=f"Индексация завершена: {session.documents_count} docs, "
                    f"{session.chunks_count} chunks, {len(failed_urls)} failed.",
        )

        # SC-039: brief generation removed — agent uses scout_get_context + scout_save_brief
        await _update(
            "completed",
            status="completed",
            session_id=str(session.id),
            documents_count=session.documents_count,
            chunks_count=session.chunks_count,
            failed_count=len(failed_urls),
            blocked_count=blocked_count,
            message=(
                f"Индексация завершена: {session.documents_count} docs, "
                f"{session.chunks_count} chunks. "
                f"Используйте scout_get_context(session_id='{session.id}') для брифа."
            ),
        )

    except Exception as exc:
        tb = traceback.format_exc()
        await _update("error", status="failed", error=str(exc), traceback=tb)
        logger.error("job {} failed:\n{}", job_id[:8], tb)


@mcp.tool()
async def scout_research_async(
    topic: str,
    query: str,
    source_urls: list[str] | None = None,
    auto_collect: bool = False,
    auto_collect_count: int = 150,
    top_k: int = 10,
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
) -> dict:
    """Start a background research job: (auto_collect →) test 10 URLs → full pipeline.

    Returns immediately with a job_id. Poll progress with scout_job_status(job_id).

    Two URL modes:
    - source_urls provided: use given list directly
    - auto_collect=True: Haiku finds URLs automatically via web_search

    Pipeline stages (reported in scout_job_status):
      0. collecting_urls / urls_collected  → only when auto_collect=True
      1. test_indexing  → test first 10 URLs
      2. test_passed / test_failed  → stop if test fails
      3. full_indexing  → index all URLs
      4. generating_brief  → LLM synthesis
      5. completed / error

    Args:
        topic:              Research topic
        query:              Research question for the brief
        source_urls:        Optional list of URLs (first 10 used for test)
        auto_collect:       If True, Haiku searches the web to find URLs automatically
        auto_collect_count: How many URLs to collect when auto_collect=True (default 150)
        top_k:              Chunks for LLM context (default 10)
        model:              "haiku", "sonnet", or "opus"
        language:           "ru" or "en"
        save_to:            Optional server path for brief markdown
    """
    # SC-036: auto_collect deprecated — агент собирает URL сам
    if auto_collect:
        return {
            "error": (
                "auto_collect=True is deprecated (SC-036). "
                "Use scout_create_job() + scout_push_urls() instead. "
                "Agent should collect URLs via web_search and push them to Scout."
            )
        }

    if not source_urls:
        return {"error": "Provide source_urls. auto_collect is deprecated (SC-036)."}

    await _ensure_job_store()
    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])
    job_id = str(uuid4())
    initial_urls = source_urls or []

    await _job_store.create({
        "job_id": job_id,
        "topic": topic,
        "total_urls": len(initial_urls),
        "query": query,
        "model": model,
        "status": "running",
        "stage": "queued",
        "message": "Задача создана" + (
            f": {len(initial_urls)} URL, тест на {TEST_BATCH_SIZE}" if initial_urls
            else f". auto_collect={auto_collect_count} URL"
        ),
    })

    async def _run_with_timeout() -> None:
        try:
            job_fn = (
                _run_research_job_stream
                if settings.redis_streaming
                else _run_research_job
            )
            await asyncio.wait_for(
                job_fn(
                    job_id, topic, initial_urls, query, top_k, llm_model,
                    language, save_to, auto_collect, auto_collect_count,
                ),
                timeout=3600.0,  # 1 час максимум на job
            )
        except asyncio.TimeoutError:
            await _ensure_job_store()
            await _job_store.update(
                job_id,
                status="failed",
                stage="timeout",
                error="Job exceeded 1 hour timeout",
            )
            logger.error("job {} timed out after 1h", job_id[:8])

    asyncio.create_task(_run_with_timeout())

    logger.info(
        "scout_research_async: job {} created (auto_collect={}, urls={})",
        job_id[:8], auto_collect, len(initial_urls),
    )

    return {
        "job_id": job_id,
        "status": "running",
        "message": (
            f"Задача запущена. auto_collect={auto_collect}. "
            f"Отслеживайте: scout_job_status(job_id='{job_id}')"
        ),
    }


@mcp.tool()
async def scout_job_status(job_id: str) -> dict:
    """Check progress of a background research job.

    Returns current stage, status, and all accumulated metrics.
    Stages: queued → test_indexing → test_passed → full_indexing →
            indexing_done → generating_brief → completed
    Status: "running", "completed", or "failed"
    """
    await _ensure_job_store()
    job = await _job_store.get(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}
    return {k: v for k, v in job.items() if k != "brief" or job.get("status") == "completed"}


@mcp.tool()
async def scout_job_result(job_id: str) -> dict:
    """Get the full result (including brief text) of a completed background job.

    Use scout_job_status first to check if the job is completed.
    """
    await _ensure_job_store()
    job = await _job_store.get(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}
    if job.get("status") != "completed":
        return {"error": f"Job not completed yet. Stage: {job.get('stage')}", "status": job.get("status")}
    return dict(job)


@mcp.tool()
async def scout_list_sessions(limit: int = 10) -> dict:
    """List recent research sessions.

    Shows history of indexed topics with status and counts.
    """
    sessions = await pipeline.list_sessions(limit)
    return {"sessions": sessions, "count": len(sessions)}


# ──────────────────────────────────────────────────────────────────────
# SC-036: Agent-First Pipeline — новые инструменты
# ──────────────────────────────────────────────────────────────────────


@mcp.tool()
async def scout_create_job(
    topic: str,
    query: str,
    top_k: int = 10,
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
) -> dict:
    """Create a research job without starting URL collection.

    Agent collects URLs separately and pushes them via scout_push_urls.
    Scout indexes them as they arrive via Redis streaming pipeline.

    Use this when agent provides URLs directly instead of auto_collect.

    Returns job_id immediately. Poll with scout_job_status(job_id).
    """
    await _ensure_job_store()
    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])
    job_id = str(uuid4())

    await _job_store.create({
        "job_id": job_id,
        "topic": topic,
        "query": query,
        "model": model,
        "status": "running",
        "stage": "waiting_for_urls",
        "total_urls": 0,
        "message": "Ожидание URL от агента. Передайте URL через scout_push_urls.",
    })

    async def _run_with_timeout() -> None:
        try:
            await asyncio.wait_for(
                _run_research_job_stream(
                    job_id, topic, [], query, top_k, llm_model,
                    language, save_to,
                    auto_collect=False,
                    auto_collect_count=0,
                ),
                timeout=3600.0,
            )
        except asyncio.TimeoutError:
            await _job_store.update(job_id, status="failed",
                                    stage="timeout",
                                    error="Job exceeded 1 hour timeout")

    asyncio.create_task(_run_with_timeout())

    logger.info("scout_create_job: job {} created, waiting for URLs", job_id[:8])

    return {
        "job_id": job_id,
        "status": "running",
        "stage": "waiting_for_urls",
        "message": (
            f"Job создан. Передайте URL: scout_push_urls(job_id='{job_id}', urls=[...]). "
            f"Для последнего батча: is_final=True."
        ),
    }


@mcp.tool()
async def scout_push_urls(
    job_id: str,
    urls: list[str],
    batch_label: str = "agent",
    is_final: bool = False,
) -> dict:
    """Receive URLs from agent and push to Redis stream for indexing.

    Agent collects URLs via its own web_search, then pushes them here.
    Scout indexes them as they arrive (streaming pipeline).

    Args:
        job_id:      Job ID from scout_create_job or scout_research_async
        urls:        List of URLs to index
        batch_label: Label for this batch (e.g. "batch_1", "final")
        is_final:    If True, send EOF signal after this batch (no more URLs)

    Returns:
        accepted: number of URLs accepted
        job_id:   echo of job_id
    """
    from src.streaming.url_stream import (
        ensure_stream_groups, publish_url_batch, publish_url_eof,
    )

    if not urls:
        return {"error": "urls list is empty"}

    await ensure_stream_groups(job_id)
    deduped = list(dict.fromkeys(u for u in urls if u.startswith("http")))
    await publish_url_batch(job_id, deduped, batch_label)

    if is_final:
        await publish_url_eof(job_id, len(deduped))
        logger.info("scout_push_urls: job {} batch '{}' {} URLs + EOF",
                    job_id[:8], batch_label, len(deduped))
    else:
        logger.info("scout_push_urls: job {} batch '{}' {} URLs",
                    job_id[:8], batch_label, len(deduped))

    return {
        "job_id": job_id,
        "accepted": len(deduped),
        "is_final": is_final,
        "message": (
            f"Принято {len(deduped)} URL в батч '{batch_label}'"
            + (" + EOF" if is_final else "")
        ),
    }


@mcp.tool()
async def scout_get_context(
    session_id: str,
    query: str,
    top_k: int = 10,
) -> dict:
    """Get top-k chunks for agent to synthesize into a brief.

    Agent uses these chunks with its own LLM (subscription) to generate brief,
    then saves result via scout_save_brief(session_id, brief).

    This replaces scout_brief() for agent-side brief generation.
    """
    sid = UUID(session_id)
    return await pipeline.get_context_for_brief(sid, query, top_k)


@mcp.tool()
async def scout_save_brief(
    session_id: str,
    brief: str,
    model: str = "agent",
    tokens_used: int | None = None,
    save_to: str | None = None,
) -> dict:
    """Save brief generated by agent to PostgreSQL and optionally to disk.

    Agent generates brief using its own LLM (subscription), then saves result here.
    This keeps the LLM call on agent side, not server side.

    Args:
        session_id:  Session ID from scout_index or scout_create_job result
        brief:       Full brief text generated by agent
        model:       Model name used (for metadata, e.g. "claude-opus-4-6")
        tokens_used: Token count (optional, for logging)
        save_to:     Optional server path to save brief as markdown
    """
    sid = UUID(session_id)

    try:
        await pipeline.save_brief(sid, brief)

        saved_path = None
        if save_to and brief:
            try:
                import os as _os
                _os.makedirs(_os.path.dirname(save_to), exist_ok=True)
                with open(save_to, "w", encoding="utf-8") as f:
                    session = await pipeline.get_session(sid)
                    topic = session.config.topic if session else "Research"
                    f.write(f"# {topic}\n\n")
                    f.write(f"**Модель**: {model}  \n")
                    if tokens_used:
                        f.write(f"**Токены**: {tokens_used}  \n")
                    f.write(f"**Session ID**: {session_id}  \n\n---\n\n")
                    f.write(brief)
                saved_path = save_to
            except Exception as e:
                logger.warning("scout_save_brief: failed to save to disk: {}", e)

        logger.info(
            "scout_save_brief: session {} brief saved ({} chars, model={})",
            session_id[:8], len(brief), model,
        )
        return {
            "session_id": session_id,
            "saved": True,
            "saved_to": saved_path,
            "brief_length": len(brief),
        }

    except Exception as exc:
        logger.error("scout_save_brief failed: {}", exc)
        return {"error": str(exc)}


# ──────────────────────────────────────────────────────────────────────
# SC-037: Worker Pool — queue-based parallelism control
# ──────────────────────────────────────────────────────────────────────


async def _worker_loop() -> None:
    """
    Persistent worker: reads jobs from Redis queue, executes with semaphore.
    Starts once per node, never stops. Launched via _ensure_worker_loop().
    """
    from src.streaming.job_queue import (
        dequeue_job, ack_job, requeue_failed, ensure_queue,
    )

    await ensure_queue()
    reclaimed = await requeue_failed(_NODE_NAME, min_idle_ms=300_000)
    if reclaimed:
        logger.info("worker_loop {}: reclaimed {} abandoned jobs", _NODE_NAME, reclaimed)

    logger.info(
        "worker_loop {}: started (MAX_WORKERS_PER_NODE={})",
        _NODE_NAME, MAX_WORKERS_PER_NODE,
    )

    sem = _get_worker_semaphore()

    while True:
        try:
            await sem.acquire()
            try:
                result = await dequeue_job(_NODE_NAME, block_ms=30_000)
                if result is None:
                    sem.release()
                    continue

                msg_id, job_params = result
                asyncio.create_task(_run_queued_job(msg_id, job_params, sem))
            except Exception:
                sem.release()
                raise

        except Exception as exc:
            logger.error("worker_loop {}: loop error: {}", _NODE_NAME, exc)
            await asyncio.sleep(5)


async def _run_queued_job(
    msg_id: str, job_params: dict, sem: asyncio.Semaphore
) -> None:
    """Execute a queued job and release semaphore when done."""
    from src.streaming.job_queue import ack_job

    job_id = job_params["job_id"]
    try:
        await _ensure_job_store()
        await _job_store.update(
            job_id,
            status="running",
            stage="starting",
            message=f"Взято воркером {_NODE_NAME}",
        )

        job_fn = (
            _run_research_job_stream
            if settings.redis_streaming
            else _run_research_job
        )
        await asyncio.wait_for(
            job_fn(
                job_id=job_id,
                topic=job_params["topic"],
                source_urls=job_params.get("source_urls", []),
                query=job_params["query"],
                top_k=job_params.get("top_k", 10),
                llm_model=job_params["llm_model"],
                language=job_params.get("language", "ru"),
                save_to=job_params.get("save_to"),
                auto_collect=False,
                auto_collect_count=0,
            ),
            timeout=3600.0,
        )

    except asyncio.TimeoutError:
        await _job_store.update(
            job_id, status="failed", stage="timeout",
            error="Job exceeded 1h timeout in worker",
        )
        logger.error("worker_loop {}: job {} timed out", _NODE_NAME, job_id[:8])

    except Exception as exc:
        tb = traceback.format_exc()
        await _job_store.update(
            job_id, status="failed", stage="error", error=str(exc),
        )
        logger.error("worker_loop {}: job {} failed:\n{}", _NODE_NAME, job_id[:8], tb)

    finally:
        await ack_job(msg_id)
        sem.release()
        logger.info("worker_loop {}: job {} done, slot released", _NODE_NAME, job_id[:8])


@mcp.tool()
async def scout_enqueue(
    topic: str,
    query: str,
    source_urls: list[str] | None = None,
    top_k: int = 10,
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
    priority: int = 0,
) -> dict:
    """Add a research job to the queue. Workers pick it up when a slot is free.

    Unlike scout_research_async (which starts immediately),
    scout_enqueue puts the job in Redis queue.
    Each node processes MAX_WORKERS_PER_NODE=2 jobs at a time.
    Remaining jobs wait in queue until a slot opens.

    Use for swarm runs (many tasks) to avoid node overload.
    Use scout_research_async for single interactive tasks.

    Args:
        source_urls: URLs to index (agent collects them, then enqueues)
        priority:    Higher = processed first (default 0)

    Returns:
        job_id:       Track progress via scout_job_status(job_id)
        queue_depth:  Jobs waiting in queue after this one
        msg_id:       Redis stream message ID
    """
    if not source_urls:
        return {"error": "source_urls required for scout_enqueue. Collect URLs first, then enqueue."}

    from src.streaming.job_queue import enqueue_job, queue_length

    await _ensure_job_store()
    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])
    job_id = str(uuid4())

    await _job_store.create({
        "job_id": job_id,
        "topic": topic,
        "query": query,
        "model": model,
        "status": "queued",
        "stage": "queued",
        "total_urls": len(source_urls),
        "message": f"В очереди. URL: {len(source_urls)}. Ждёт свободного слота на воркере.",
    })

    job_params = {
        "job_id": job_id,
        "topic": topic,
        "source_urls": source_urls,
        "query": query,
        "top_k": top_k,
        "llm_model": llm_model,
        "language": language,
        "save_to": save_to,
        "priority": priority,
    }
    msg_id = await enqueue_job(job_params)
    depth = await queue_length()

    logger.info(
        "scout_enqueue: job {} queued ({} URLs, queue_depth={})",
        job_id[:8], len(source_urls), depth,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "msg_id": msg_id,
        "queue_depth": depth,
        "total_urls": len(source_urls),
        "message": (
            f"Задача поставлена в очередь. "
            f"Отслеживайте: scout_job_status(job_id='{job_id}'). "
            f"Задач в очереди: {depth}."
        ),
    }


@mcp.tool()
async def scout_queue_status() -> dict:
    """Get current state of the job queue and workers on this node.

    Returns:
        queue_depth:     Jobs waiting in queue
        active_slots:    Slots currently in use on this node
        free_slots:      Available slots on this node
        max_slots:       MAX_WORKERS_PER_NODE for this node
        node:            This node name
    """
    from src.streaming.job_queue import queue_length

    sem = _get_worker_semaphore()
    active = MAX_WORKERS_PER_NODE - sem._value
    depth = await queue_length()

    return {
        "node": _NODE_NAME,
        "queue_depth": depth,
        "active_slots": active,
        "free_slots": sem._value,
        "max_slots": MAX_WORKERS_PER_NODE,
        "message": (
            f"Узел {_NODE_NAME}: {active}/{MAX_WORKERS_PER_NODE} слотов занято. "
            f"В очереди: {depth} задач."
        ),
    }


# ── SC-040: REST API for Scout Monitor ────────────────────────────────


@mcp.custom_route("/api/jobs", methods=["GET"])
async def api_jobs(request):
    """REST endpoint for Scout Monitor dashboard.

    Query params:
      limit  — max jobs to return (default 100)
      status — filter: running/completed/failed/queued/all (default all)
      since  — jobs updated after this ISO timestamp
    """
    import datetime as _dt

    from starlette.responses import JSONResponse

    params = request.query_params
    limit = int(params.get("limit", 100))
    status = params.get("status", "all")
    since = params.get("since", None)

    await _ensure_job_store()

    async with _job_store._pool.acquire() as conn:
        conditions = []
        values = []
        idx = 1

        if status != "all":
            conditions.append(f"status = ${idx}")
            values.append(status)
            idx += 1

        if since:
            conditions.append(f"updated_at > ${idx}")
            values.append(since)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        values.append(limit)

        rows = await conn.fetch(
            f"""SELECT job_id, topic, model, status, stage, message,
                       total_urls, documents_count, chunks_count,
                       failed_count, tokens_used, sources_used,
                       session_id, error, elapsed_sec,
                       created_at, updated_at
               FROM async_jobs
               {where}
               ORDER BY created_at DESC
               LIMIT ${idx}""",
            *values,
        )

    jobs = []
    for row in rows:
        d = dict(row)
        for key in ("created_at", "updated_at"):
            if d.get(key):
                d[key] = d[key].isoformat()
        jobs.append(d)

    return JSONResponse(
        {
            "jobs": jobs,
            "total": len(jobs),
            "node": _NODE_NAME,
            "timestamp": _dt.datetime.utcnow().isoformat(),
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
        },
    )


@mcp.custom_route("/api/jobs/clear", methods=["POST"])
async def api_jobs_clear(request):
    """Delete completed/failed jobs from DB. Keeps running/queued.

    Query params:
      status — which to delete: completed/failed/all (default: all finished)
    """
    from starlette.responses import JSONResponse

    params = request.query_params
    status = params.get("status", "finished")

    await _ensure_job_store()

    async with _job_store._pool.acquire() as conn:
        if status == "completed":
            result = await conn.execute("DELETE FROM async_jobs WHERE status = 'completed'")
        elif status == "failed":
            result = await conn.execute("DELETE FROM async_jobs WHERE status = 'failed'")
        elif status == "all":
            result = await conn.execute("DELETE FROM async_jobs")
        else:
            result = await conn.execute(
                "DELETE FROM async_jobs WHERE status IN ('completed', 'failed')"
            )

    deleted = int(result.split()[-1]) if result else 0
    logger.info("api_jobs_clear: deleted {} jobs (filter={})", deleted, status)

    return JSONResponse(
        {"deleted": deleted, "filter": status},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
        },
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check — проверяет PostgreSQL и ChromaDB."""
    import httpx
    from starlette.responses import JSONResponse

    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        await pipeline._ensure_init()
        async with pipeline._session_store._pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    # ChromaDB — пинг через HTTP heartbeat
    try:
        from src.config import settings as _s
        chroma_url = f"http://{_s.chroma_host}:{_s.chroma_port}/api/v2/heartbeat"
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(chroma_url)
            checks["chroma"] = "ok" if r.status_code == 200 else f"status {r.status_code}"
    except Exception as exc:
        checks["chroma"] = f"error: {exc}"

    # Redis (только если streaming включён)
    if settings.redis_streaming:
        try:
            from src.streaming.redis_client import get_redis
            r = await get_redis()
            await r.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {
            "status": "ok" if all_ok else "degraded",
            "service": "scout-mcp",
            "checks": checks,
        },
        status_code=200 if all_ok else 503,
    )


@mcp.custom_route("/tools", methods=["GET"])
async def tools_list(request):
    """List registered MCP tools — for CI smoke test."""
    from starlette.responses import JSONResponse

    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    return JSONResponse({"tools": tool_names})


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8020"))
    host = os.getenv("MCP_HOST", "0.0.0.0")
    logger.info("Starting Scout MCP on {}:{}", host, port)
    mcp.run(transport="http", host=host, port=port)

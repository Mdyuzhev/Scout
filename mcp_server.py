"""Scout MCP Server — entrypoint."""

import asyncio
import os
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
    """Generate a research brief using LLM from indexed data.

    Searches top-k relevant chunks and synthesizes a brief.

    Args:
        model: LLM model — "haiku" (default), "sonnet", or "opus"
    """
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

    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])

    # Автосбор URL если запрошен
    collected_urls: list[str] = []
    if auto_collect:
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

    # Шаг 2: генерация брифа
    result = await pipeline.brief(session.id, query, top_k, model=llm_model)

    brief_text = result.get("brief", "")

    # Шаг 3: сохранить на диск если запрошено
    saved_path = None
    if save_to and brief_text:
        try:
            import os as _os
            _os.makedirs(_os.path.dirname(save_to), exist_ok=True)
            with open(save_to, "w", encoding="utf-8") as f:
                f.write(f"# {topic}\n\n")
                f.write(f"**Модель**: {result.get('model')}  \n")
                f.write(f"**Токены**: {result.get('tokens_used')}  \n")
                f.write(f"**Источников**: {result.get('sources_used', 0)}  \n")
                f.write(f"**Session ID**: {session.id}  \n\n---\n\n")
                f.write(brief_text)
            saved_path = save_to
            logger.info("scout_research: brief saved to {}", save_to)
        except Exception as e:
            logger.warning("scout_research: failed to save brief: {}", e)

    return {
        # Бриф
        "brief":          brief_text,
        "model":          result.get("model"),
        "tokens_used":    result.get("tokens_used"),
        "sources_used":   result.get("sources_used", 0),
        # Сессия (для follow-up вызовов scout_search)
        "session_id":     str(session.id),
        # Статистика индексации
        "documents_count": session.documents_count,
        "chunks_count":    session.chunks_count,
        "failed_count":    len(failed_urls),
        "blocked_count":   blocked_count,
        "auto_collected_urls": len(collected_urls),
        # Файл
        "saved_to":        saved_path,
    }


MODEL_MAP = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-6",
}

TEST_BATCH_SIZE = 10


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

    async def _update(stage: str, **kw):
        kw["stage"] = stage
        await _job_store.update(job_id, **kw)
        logger.info("job {}: {}", job_id[:8], stage)

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

        if test_session.status.value != "ready" or test_session.documents_count == 0:
            await _update(
                "test_failed",
                status="failed",
                error=f"Тест провален: {test_session.documents_count} docs, "
                      f"{len(test_failed)} failed, status={test_session.status.value}",
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

        # ── Stage 3: brief generation ───────────────────────────────
        await _update("generating_brief", message=f"Генерация брифа (model={llm_model}, top_k={top_k})...")

        result = await pipeline.brief(session.id, query, top_k, model=llm_model)
        brief_text = result.get("brief", "")

        # ── Stage 4: save to disk if requested ──────────────────────
        saved_path = None
        if save_to and brief_text:
            try:
                os.makedirs(os.path.dirname(save_to), exist_ok=True)
                with open(save_to, "w", encoding="utf-8") as f:
                    f.write(f"# {topic}\n\n")
                    f.write(f"**Модель**: {result.get('model')}  \n")
                    f.write(f"**Токены**: {result.get('tokens_used')}  \n")
                    f.write(f"**Источников**: {result.get('sources_used', 0)}  \n")
                    f.write(f"**Session ID**: {session.id}  \n\n---\n\n")
                    f.write(brief_text)
                saved_path = save_to
            except Exception as e:
                logger.warning("job {}: failed to save brief: {}", job_id[:8], e)

        await _update(
            "completed",
            status="completed",
            brief=brief_text,
            model=result.get("model"),
            tokens_used=result.get("tokens_used"),
            sources_used=result.get("sources_used", 0),
            saved_to=saved_path,
            message=f"Готово! {session.documents_count} docs, "
                    f"{result.get('tokens_used')} tokens, model={result.get('model')}",
        )

    except Exception as exc:
        await _update("error", status="failed", error=str(exc))
        logger.error("job {} failed: {}", job_id[:8], exc)


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
    if not source_urls and not auto_collect:
        return {"error": "Provide source_urls or set auto_collect=True"}

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
            await asyncio.wait_for(
                _run_research_job(
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


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint для CI и мониторинга."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "service": "scout-mcp"})


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

"""Scout MCP Server — entrypoint."""

import os
from uuid import UUID

from fastmcp import FastMCP
from loguru import logger

from src.config import DepthLevel, LLMProvider, ResearchConfig
from src.pipeline import ScoutPipeline

mcp = FastMCP("Scout")
pipeline = ScoutPipeline()


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
) -> dict:
    """Index documents for a research topic.

    Two modes:
    - source_type="web" (default): search via DuckDuckGo
    - source_type="urls": fetch provided URLs directly, no search

    For urls mode, provide source_urls (up to 200 URLs).
    Set cache_ttl_hours=0 to force re-indexing.
    """
    from src.config import SourceType

    config = ResearchConfig(
        topic=topic,
        depth=DepthLevel(depth),
        queries=queries or [],
        language=language,
        llm_provider=LLMProvider(llm_provider),
        cache_ttl_hours=cache_ttl_hours,
        source_type=SourceType(source_type),
        source_urls=source_urls or [],
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
    model_map = {
        "haiku":  "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus":   "claude-opus-4-6",
    }
    llm_model = model_map.get(model, model_map["haiku"])
    sid = UUID(session_id)
    result = await pipeline.brief(sid, query, top_k, model=llm_model)
    result["sources_used"] = result.get("sources_used", 0)
    return result


@mcp.tool()
async def scout_research(
    topic: str,
    source_urls: list[str],
    query: str,
    top_k: int = 15,
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
) -> dict:
    """Full research pipeline in one call: index URLs → generate brief.

    Combines scout_index + scout_brief into a single atomic operation.
    The agent does not need to manage session_id between steps.

    Args:
        topic:       Research topic description (used for indexing and history)
        source_urls: List of URLs to fetch and index (up to 400)
        query:       Research question for the brief (what to synthesize)
        top_k:       Number of top chunks to pass to LLM (default 15)
        model:       LLM model — "haiku" (fast, factual), "sonnet" (narrative),
                     "opus" (balanced, most thorough). Default: "haiku"
        language:    Source language hint for embeddings — "ru" or "en"
        save_to:     Optional path on server to save the brief as markdown,
                     e.g. "/opt/scout/results/my_brief.md"

    Returns:
        brief:            Full text of the research brief
        model:            Model used
        tokens_used:      LLM token consumption
        sources_used:     Number of unique sources in context
        session_id:       Session ID for follow-up scout_search calls
        documents_count:  Successfully indexed documents
        chunks_count:     Total indexed chunks
        failed_count:     URLs that could not be fetched
        blocked_count:    URLs skipped (bot-protection blocklist)
        saved_to:         Path where brief was saved (if save_to provided)
    """
    from src.config import SourceType

    # Выбор модели: короткое имя → полная строка
    model_map = {
        "haiku":  "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus":   "claude-opus-4-6",
    }
    llm_model = model_map.get(model, model_map["haiku"])

    # Шаг 1: индексация
    logger.info("scout_research: indexing {} URLs for '{}'", len(source_urls), topic)
    config = ResearchConfig(
        topic=topic,
        depth=DepthLevel.NORMAL,
        language=language,
        llm_provider=LLMProvider.ANTHROPIC,
        cache_ttl_hours=0,  # всегда свежая индексация
        source_type=SourceType.SPECIFIC_URLS,
        source_urls=source_urls,
    )
    session, failed_urls, blocked_count = await pipeline.index(config)

    if session.status.value != "ready" or session.documents_count == 0:
        return {
            "error": f"Indexing failed or zero documents. Status: {session.status.value}",
            "session_id": str(session.id),
            "documents_count": session.documents_count,
            "failed_count": len(failed_urls),
            "blocked_count": blocked_count,
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
        # Файл
        "saved_to":        saved_path,
    }


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

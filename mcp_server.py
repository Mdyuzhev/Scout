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

    session, failed_urls = await pipeline.index(config)

    return {
        "session_id": str(session.id),
        "status": session.status.value,
        "documents_count": session.documents_count,
        "chunks_count": session.chunks_count,
        "failed_urls": failed_urls,
        "failed_count": len(failed_urls),
        "message": (
            f"Indexed {session.documents_count} docs "
            f"({len(failed_urls)} failed) for '{topic}'"
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
) -> dict:
    """Generate a research brief using LLM from indexed data.

    Searches top-k relevant chunks and synthesizes a brief.
    """
    sid = UUID(session_id)
    result = await pipeline.brief(sid, query, top_k)
    result["sources_used"] = result.get("sources_used", 0)
    return result


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

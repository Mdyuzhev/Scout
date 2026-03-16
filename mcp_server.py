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
) -> dict:
    """Index documents from web for a research topic.

    Collects web pages, chunks text, and indexes into vector store.
    Returns session_id for subsequent search/brief calls.
    """
    config = ResearchConfig(
        topic=topic,
        depth=DepthLevel(depth),
        queries=queries or [],
        language=language,
        llm_provider=LLMProvider(llm_provider),
    )

    session = await pipeline.index(config)

    return {
        "session_id": str(session.id),
        "status": session.status.value,
        "documents_count": session.documents_count,
        "chunks_count": session.chunks_count,
        "message": (
            f"Indexed {session.documents_count} documents, "
            f"{session.chunks_count} chunks for '{topic}'"
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


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8020"))
    host = os.getenv("MCP_HOST", "0.0.0.0")
    logger.info("Starting Scout MCP on {}:{}", host, port)
    mcp.run(transport="http", host=host, port=port)

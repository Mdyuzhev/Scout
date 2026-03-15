"""Scout MCP Server — entrypoint."""

from fastmcp import FastMCP

mcp = FastMCP(
    "Scout",
    description="MCP-сервер предобработки данных для продуктовых исследований",
)


@mcp.tool()
async def scout_index(sources: list[str], topic: str) -> dict:
    """Index documents from given sources for a research topic."""
    return {"status": "not_implemented"}


@mcp.tool()
async def scout_search(query: str, top_k: int = 10) -> dict:
    """Search indexed documents by semantic similarity."""
    return {"status": "not_implemented"}


@mcp.tool()
async def scout_brief(topic: str) -> dict:
    """Generate a research brief from indexed and retrieved data."""
    return {"status": "not_implemented"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8020)

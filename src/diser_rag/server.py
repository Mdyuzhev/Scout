"""Diser RAG — FastAPI server.

/ask  → returns context chunks for agent-side synthesis (no server LLM calls, SC-036 pattern)
/search → semantic search, returns raw chunks
/index  → index/reindex briefs
/health → status
"""

import sys
import os

# Allow running as `python src/diser_rag/server.py` from project root
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from loguru import logger

from src.diser_rag import config
from src.diser_rag.indexer import index as run_index
from src.diser_rag.searcher import Searcher
from src.diser_rag.synthesizer import get_context

app = FastAPI(title="Diser RAG", version="1.1.0")
_searcher: Searcher | None = None


def get_searcher() -> Searcher:
    global _searcher
    if _searcher is None:
        _searcher = Searcher()
    return _searcher


# --- Request models ---

class AskRequest(BaseModel):
    query: str
    domain: str | None = None
    swarm: str | None = None
    top_k: int | None = None   # override default top_k if needed

class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    domain: str | None = None
    swarm: str | None = None

class IndexRequest(BaseModel):
    swarm: str | None = None


# --- Endpoints ---

@app.get("/health")
def health():
    s = get_searcher()
    return {
        "status": "ok",
        "chunks": s._collection.count(),
        "briefs_dir": config.BRIEFS_DIR,
        "version": "1.1.0",
    }


@app.post("/index")
def index_endpoint(req: IndexRequest):
    result = run_index(swarm_filter=req.swarm)
    # Reload searcher to pick up new chunks
    get_searcher().reload()
    return result


@app.post("/search")
def search_endpoint(req: SearchRequest):
    s = get_searcher()
    results = s.search(req.query, top_k=req.top_k, domain=req.domain, swarm=req.swarm)
    return {
        "results": [
            {
                "text": r.text[:500],
                "brief_id": r.brief_id,
                "topic": r.topic,
                "swarm": r.swarm,
                "domain": r.domain,
                "similarity": round(r.similarity, 3),
            }
            for r in results
        ]
    }


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    """Return context for agent-side synthesis.

    Response:
      found         — True if relevant chunks found
      context       — assembled text from top-k chunks
      sources       — list of source briefs with metadata
      chunks_count  — number of chunks in context
      system_prompt — system prompt to use when generating the answer
      user_prompt   — ready-made user message: context + question

    The agent calls this endpoint, then generates the answer using its own LLM.
    No server-side LLM calls (SC-036 pattern — LLM stays on agent side).
    """
    s = get_searcher()
    top_k = req.top_k or config.TOP_K
    return get_context(req.query, s, domain=req.domain, swarm=req.swarm)


if __name__ == "__main__":
    logger.info(f"Starting Diser RAG v1.1 on port {config.SERVER_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT)

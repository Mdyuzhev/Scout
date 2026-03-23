"""Diser RAG — configuration from environment."""

import os

BRIEFS_DIR = os.getenv("DISER_BRIEFS_DIR", "/opt/scout/diser_briefs")
CHROMA_PATH = os.getenv("DISER_CHROMA_PATH", "/app/data/diser_chroma")
COLLECTION = os.getenv("DISER_COLLECTION", "diser_briefs")
TOP_K = int(os.getenv("DISER_TOP_K", "12"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8031"))
LLM_MODEL = os.getenv("DISER_LLM_MODEL", "claude-sonnet-4-20250514")

DOMAIN_MAP: dict[str, str] = {
    "swarm_v1": "it-economics",
    "swarm_v1.1": "it-economics",
    "swarm_v2": "it-economics",
    "swarm_v3": "biotech",
    "swarm_v4": "java-td",
    "swarm_v5": "python-td",
    "swarm_v6": "ru-ai-se",
    "swarm_v7": "se-measurement-history",
    "dissercat": "ru-dissertations",
    "arxiv": "arxiv-papers",
    "synthesis": "synthesis",
}

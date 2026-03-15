"""Scout configuration — ResearchConfig + global settings."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Depth(str, Enum):
    quick = "quick"
    normal = "normal"
    deep = "deep"


class LLMProvider(str, Enum):
    anthropic = "anthropic"
    ollama = "ollama"


class ResearchConfig(BaseModel):
    """Per-research configuration passed by the agent."""

    topic: str
    sources: list[str] = Field(default_factory=list)
    depth: Depth = Depth.normal
    min_similarity: float = Field(default=0.60)
    max_chunks: int = Field(default=30)


class Settings(BaseModel):
    """Global server settings from environment."""

    mcp_host: str = Field(default="0.0.0.0")
    mcp_port: int = Field(default=8020)

    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5436)
    postgres_db: str = Field(default="scout_db")
    postgres_user: str = Field(default="scout_user")
    postgres_password: str = Field(default="")

    chroma_path: Path = Field(default=Path("./data/chroma_db"))

    embedding_model: str = Field(default="paraphrase-multilingual-MiniLM-L12-v2")

    llm_provider: LLMProvider = Field(default=LLMProvider.anthropic)
    anthropic_api_key: str = Field(default="")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="mistral")

    default_depth: Depth = Field(default=Depth.normal)
    default_cache_ttl_hours: int = Field(default=24)
    min_similarity: float = Field(default=0.60)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mcp_host=os.getenv("MCP_HOST", "0.0.0.0"),
            mcp_port=int(os.getenv("MCP_PORT", "8020")),
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5436")),
            postgres_db=os.getenv("POSTGRES_DB", "scout_db"),
            postgres_user=os.getenv("POSTGRES_USER", "scout_user"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
            chroma_path=Path(os.getenv("CHROMA_PATH", "./data/chroma_db")),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
            ),
            llm_provider=LLMProvider(os.getenv("LLM_PROVIDER", "anthropic")),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "mistral"),
            default_depth=Depth(os.getenv("DEFAULT_DEPTH", "normal")),
            default_cache_ttl_hours=int(
                os.getenv("DEFAULT_CACHE_TTL_HOURS", "24")
            ),
            min_similarity=float(os.getenv("MIN_SIMILARITY", "0.60")),
        )


settings = Settings.from_env()

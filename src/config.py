"""Scout configuration — модели данных и глобальные настройки."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


# --- Enums ---


class DepthLevel(str, Enum):
    QUICK = "quick"
    NORMAL = "normal"
    DEEP = "deep"


class SourceType(str, Enum):
    WEB = "web"
    LOCAL_FILE = "local_file"
    SPECIFIC_URLS = "urls"


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class SessionStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


# --- Domain models ---


class ResearchConfig(BaseModel):
    """Входные параметры исследования — передаётся агентом в scout_index."""

    topic: str
    queries: list[str] = Field(default_factory=list)
    source_type: SourceType = SourceType.WEB
    source_urls: list[str] = Field(default_factory=list)
    depth: DepthLevel = DepthLevel.NORMAL
    language: str = "ru"
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    cache_ttl_hours: int = 24
    min_similarity: float = 0.60
    top_k: int = 10


class Document(BaseModel):
    """Сырой документ после сбора."""

    url: str
    title: str
    content: str
    content_hash: str = ""
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: object) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


class Chunk(BaseModel):
    """Единица индексации — фрагмент документа."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    text: str
    source_url: str
    source_title: str
    metadata: dict = Field(default_factory=dict)


class ResearchSession(BaseModel):
    """Рабочее состояние — создаётся при scout_index, хранится в PostgreSQL."""

    id: UUID = Field(default_factory=uuid4)
    config: ResearchConfig
    status: SessionStatus = SessionStatus.PENDING
    documents_count: int = 0
    chunks_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def chroma_collection_name(self) -> str:
        return f"session_{self.id.hex}"


class SearchResult(BaseModel):
    """Один результат семантического поиска."""

    chunk_id: str
    text: str
    source_url: str
    source_title: str
    similarity: float


class ResearchPackage(BaseModel):
    """Выходной артефакт — то что получает агент после scout_search."""

    session_id: UUID
    topic: str
    query: str
    results: list[SearchResult]
    total_chunks_in_index: int
    brief: str | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# --- Global settings ---


class Settings(BaseModel):
    """Глобальные настройки сервера из переменных окружения."""

    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8020

    postgres_host: str = "localhost"
    postgres_port: int = 5436
    postgres_db: str = "scout_db"
    postgres_user: str = "scout_user"
    postgres_password: str = ""

    chroma_path: Path = Path("./data/chroma_db")
    chroma_mode: str = "local"  # "local" (PersistentClient) or "server" (HttpClient)
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"

    default_depth: DepthLevel = DepthLevel.NORMAL
    default_cache_ttl_hours: int = 24
    min_similarity: float = 0.60

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mcp_host=os.getenv("MCP_HOST", "0.0.0.0"),
            mcp_port=int(os.getenv("MCP_PORT", "8020")),
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5436")),
            postgres_db=os.getenv("POSTGRES_DB", "scout_db"),
            postgres_user=os.getenv("POSTGRES_USER", "scout_user"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
            chroma_path=Path(os.getenv("CHROMA_PATH", "./data/chroma_db")),
            chroma_mode=os.getenv("CHROMA_MODE", "local"),
            chroma_host=os.getenv("CHROMA_HOST", "localhost"),
            chroma_port=int(os.getenv("CHROMA_PORT", "8000")),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
            ),
            llm_provider=LLMProvider(os.getenv("LLM_PROVIDER", "anthropic")),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "mistral"),
            default_depth=DepthLevel(os.getenv("DEFAULT_DEPTH", "normal")),
            default_cache_ttl_hours=int(
                os.getenv("DEFAULT_CACHE_TTL_HOURS", "24")
            ),
            min_similarity=float(os.getenv("MIN_SIMILARITY", "0.60")),
        )


settings = Settings.from_env()

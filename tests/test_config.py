"""Тесты моделей данных SC-002."""

from uuid import UUID

from src.config import (
    Chunk,
    DepthLevel,
    Document,
    LLMProvider,
    ResearchConfig,
    ResearchPackage,
    ResearchSession,
    SearchResult,
    SessionStatus,
    SourceType,
)


def test_research_config_defaults():
    cfg = ResearchConfig(topic="test topic")
    assert cfg.topic == "test topic"
    assert cfg.depth == DepthLevel.NORMAL
    assert cfg.source_type == SourceType.WEB
    assert cfg.language == "ru"
    assert cfg.top_k == 10
    assert cfg.min_similarity == 0.60
    assert cfg.queries == []
    assert cfg.source_urls == []


def test_research_config_custom():
    cfg = ResearchConfig(
        topic="analytics",
        queries=["q1", "q2"],
        source_type=SourceType.SPECIFIC_URLS,
        source_urls=["http://example.com"],
        depth=DepthLevel.DEEP,
        language="en",
        llm_provider=LLMProvider.OLLAMA,
        top_k=20,
    )
    assert cfg.depth == DepthLevel.DEEP
    assert cfg.llm_provider == LLMProvider.OLLAMA
    assert len(cfg.source_urls) == 1


def test_document_content_hash():
    doc = Document(url="http://x.com", title="X", content="hello world")
    assert len(doc.content_hash) == 64  # sha256 hex
    doc2 = Document(url="http://y.com", title="Y", content="hello world")
    assert doc.content_hash == doc2.content_hash


def test_chunk_auto_id():
    c1 = Chunk(text="text", source_url="http://x.com", source_title="X")
    c2 = Chunk(text="text", source_url="http://x.com", source_title="X")
    assert c1.id != c2.id
    assert len(c1.id) == 32  # uuid hex


def test_research_session():
    cfg = ResearchConfig(topic="test")
    session = ResearchSession(config=cfg)
    assert session.status == SessionStatus.PENDING
    assert isinstance(session.id, UUID)
    assert session.chroma_collection_name.startswith("session_")
    assert session.completed_at is None
    assert session.error is None


def test_research_package_serialization():
    pkg = ResearchPackage(
        session_id=UUID("12345678-1234-1234-1234-123456789abc"),
        topic="test",
        query="test query",
        results=[
            SearchResult(
                chunk_id="abc",
                text="some text",
                source_url="http://x.com",
                source_title="X",
                similarity=0.85,
            )
        ],
        total_chunks_in_index=100,
    )
    d = pkg.model_dump()
    assert d["topic"] == "test"
    assert len(d["results"]) == 1
    assert d["results"][0]["similarity"] == 0.85
    assert d["brief"] is None

    j = pkg.model_dump_json()
    assert "test query" in j


def test_research_config_json_roundtrip():
    cfg = ResearchConfig(topic="roundtrip test", depth=DepthLevel.QUICK)
    j = cfg.model_dump_json()
    cfg2 = ResearchConfig.model_validate_json(j)
    assert cfg2.topic == cfg.topic
    assert cfg2.depth == DepthLevel.QUICK

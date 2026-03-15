# SC-002 — Модели данных: ResearchConfig, ResearchSession, ResearchPackage

## Цель

Определить центральные объекты данных системы через Pydantic-модели. Это
фундамент всего пайплайна — все компоненты говорят на одном языке через
эти структуры. После этой задачи ядро системы "знает" как выглядит
исследовательская задача, рабочая сессия и финальный результат.

---

## Контекст

Три ключевых объекта зафиксированы в архитектурном решении:

- `ResearchConfig` — входные параметры (что и как исследовать)
- `ResearchSession` — рабочее состояние (конфиг + накопленные данные + статус)
- `ResearchPackage` — выходной артефакт (топ-N чанков + метаданные + brief)

Всё в `src/config.py`. Используем Pydantic v2 для валидации и сериализации.

---

## Шаги выполнения

### 1. Enums

```python
class DepthLevel(str, Enum):
    QUICK  = "quick"   # ~15 документов, 1 поисковый запрос
    NORMAL = "normal"  # ~40 документов, 2-3 запроса
    DEEP   = "deep"    # ~100 документов, 5+ запросов

class SourceType(str, Enum):
    WEB        = "web"         # веб-скрейпинг по запросам
    LOCAL_FILE = "local_file"  # локальные файлы (txt, md, pdf)
    SPECIFIC_URLS = "urls"     # конкретные URL без поиска

class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OLLAMA    = "ollama"

class SessionStatus(str, Enum):
    PENDING  = "pending"
    INDEXING = "indexing"
    READY    = "ready"
    FAILED   = "failed"
```

### 2. ResearchConfig

Входные параметры исследования. Агент передаёт этот объект в `scout_index`.

```python
class ResearchConfig(BaseModel):
    topic: str                          # главная тема ("product analytics tools 2025")
    queries: list[str] = []             # дополнительные поисковые запросы
                                        # если пусто — генерируются из topic
    source_type: SourceType = SourceType.WEB
    source_urls: list[str] = []         # для SourceType.SPECIFIC_URLS или LOCAL_FILE
    depth: DepthLevel = DepthLevel.NORMAL
    language: str = "ru"                # язык контента (влияет на поиск)
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    cache_ttl_hours: int = 24           # сколько часов считать сессию актуальной
    min_similarity: float = 0.60        # порог релевантности для фильтрации
    top_k: int = 10                     # сколько чанков возвращать в ResearchPackage
```

### 3. Document и Chunk — внутренние объекты пайплайна

```python
class Document(BaseModel):
    """Сырой документ после сбора."""
    url: str
    title: str
    content: str                        # очищенный текст
    content_hash: str                   # sha256 для дедупликации
    collected_at: datetime

class Chunk(BaseModel):
    """Единица индексации — фрагмент документа."""
    id: str                             # uuid
    text: str
    source_url: str
    source_title: str
    metadata: dict = {}
```

### 4. ResearchSession

Рабочее состояние — создаётся при `scout_index`, хранится в PostgreSQL.

```python
class ResearchSession(BaseModel):
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
```

### 5. ResearchPackage

Выходной артефакт, который получает агент после `scout_search`.

```python
class SearchResult(BaseModel):
    chunk_id: str
    text: str
    source_url: str
    source_title: str
    similarity: float

class ResearchPackage(BaseModel):
    session_id: UUID
    topic: str
    query: str                          # запрос по которому искали
    results: list[SearchResult]
    total_chunks_in_index: int
    brief: str | None = None            # заполняется после scout_brief
    generated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 6. Тест моделей

В `tests/test_config.py` — базовые тесты: создание объектов с дефолтными
значениями, валидация обязательных полей, сериализация в dict/json.

---

## Критерии готовности

- `src/config.py` создан, все модели определены и импортируются без ошибок
- `python -c "from src.config import ResearchConfig; print(ResearchConfig(topic='test'))"` работает
- Тесты в `tests/test_config.py` проходят

---

*Дата создания: 2026-03-16*

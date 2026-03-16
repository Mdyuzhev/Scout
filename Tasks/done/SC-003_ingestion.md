# SC-003 — Ingestion: сбор, нарезка, индексация

## Цель

Реализовать детерминированный слой сбора данных: веб-коллектор, стратегия нарезки
на чанки и индексация в ChromaDB. После этой задачи Scout умеет принимать
`ResearchConfig`, собирать документы из веба, нарезать их и строить
векторный индекс для поиска.

---

## Контекст

Это самый важный слой — именно здесь реализуется главная идея Scout:
детерминированная предобработка без LLM. Три компонента работают последовательно:

```
ResearchConfig
    → WebCollector   → list[Document]
    → Chunker        → list[Chunk]
    → Indexer        → ChromaDB collection
```

За основу chunker и indexer берём код из `E:\RAG_qa\src\ingestion\` —
адаптируем под новые модели данных.

---

## Шаги выполнения

### 1. BaseCollector (src/ingestion/base.py)

Абстракция — все коллекторы реализуют один интерфейс:

```python
from abc import ABC, abstractmethod
from src.config import ResearchConfig, Document

class BaseCollector(ABC):
    @abstractmethod
    async def collect(self, config: ResearchConfig) -> list[Document]:
        """Собрать документы согласно конфигу. Возвращает очищенные Document."""
        ...
```

### 2. WebCollector (src/ingestion/web.py)

Алгоритм работы зависит от `config.source_type`:
- `WEB` — строит поисковые запросы из `config.topic` + `config.queries`,
  делает поиск через DuckDuckGo HTML-интерфейс (без API), парсит результаты,
  скачивает страницы через httpx, очищает через BeautifulSoup (убирает nav,
  footer, script, style — оставляет только основной контент).
- `SPECIFIC_URLS` — скачивает только указанные `config.source_urls`.

Глубина (`depth`) управляет количеством запросов и страниц:
- `QUICK` → 1 запрос, до 15 страниц
- `NORMAL` → 3 запроса, до 40 страниц
- `DEEP` → 5 запросов, до 100 страниц

Дедупликация по `content_hash` (sha256 первых 1000 символов) —
не добавляем документ если уже видели такое содержимое.

Таймаут на запрос: 10 секунд. При ошибке — логировать и пропускать, не падать.

### 3. SlidingWindowChunker (src/chunking/sliding_window.py)

Для веб-контента иерархическая группировка из RAG-QA не подходит — там нет
структуры модулей. Используем скользящее окно:

```python
class SlidingWindowChunker:
    def __init__(self, window_size: int = 500, overlap: int = 100):
        # window_size — слов в чанке
        # overlap — перекрытие между соседними чанками (сохраняет контекст)
        ...

    def chunk(self, doc: Document) -> list[Chunk]:
        # Разбиваем текст на слова, делаем окна с перекрытием
        # Каждый чанк получает id = uuid, source_url и source_title из Document
        ...
```

Параметры по умолчанию подобраны под `paraphrase-multilingual-MiniLM-L12-v2`:
модель хорошо работает с фрагментами 200-600 слов.

### 4. Indexer (src/ingestion/indexer.py)

Принимает `list[Chunk]` и `session_id`, создаёт коллекцию в ChromaDB
с именем `session_{session_id_hex}`:

```python
class Indexer:
    def __init__(self, chroma_path: str, model_name: str):
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=model_name)

    def index(self, chunks: list[Chunk], session_id: UUID) -> int:
        """Индексирует чанки. Возвращает количество проиндексированных."""
        collection_name = f"session_{session_id.hex}"
        # Создать коллекцию (или получить если уже есть)
        # Добавить документы батчами по 100 (ChromaDB limit)
        # Вернуть итоговое количество
        ...
```

Батчевая индексация важна — ChromaDB не любит добавление 1000 документов
за один вызов.

### 5. Smoke-test (tests/test_ingestion.py)

Тест не должен делать реальных HTTP-запросов — мокируем `httpx.AsyncClient`.
Проверяем: коллектор возвращает `list[Document]`, чанкер нарезает корректно
(без пустых чанков, с правильными полями), индексер создаёт коллекцию.

---

## Критерии готовности

- `WebCollector` собирает документы по теме без падений (тест с реальным запросом
  на одну страницу — например, Wikipedia)
- `SlidingWindowChunker` нарезает текст в 2000 слов на ~5 чанков с перекрытием
- `Indexer` создаёт коллекцию в ChromaDB, `collection.count()` > 0
- Smoke-тесты проходят

---

*Дата создания: 2026-03-16*

---

## ✅ Статус: ВЫПОЛНЕНА

**Дата завершения:** 2026-03-16

**Что сделано:**
- `WebCollector` — полная реализация: DuckDuckGo HTML search, httpx fetch, BS4 очистка, дедупликация по content_hash
- `SlidingWindowChunker` — скользящее окно (500 слов, 100 overlap), использует `Chunk` из config.py
- `Indexer` — ChromaDB batch-индексация (батчи по 100), session-scoped коллекции
- `BaseChunker` приведён к единой модели `Chunk` из config.py (убран дублирующий Chunk из chunking/base.py)
- `BaseCollector` сигнатура приведена в соответствие со спецификацией
- 10 smoke-тестов: 3 WebCollector (specific_urls, dedup, error handling), 5 SlidingWindowChunker (basic, no_empty, source, empty_doc, overlap), 2 Indexer (collection, batching)
- Все 17 тестов проекта pass (7 SC-002 + 10 SC-003)

**Отклонения от плана:**
- Стабы из SC-001 имели расходящиеся сигнатуры (web.py: AsyncIterator вместо list, chunking/base.py: свой Chunk) — приведены к единой архитектуре из задачи

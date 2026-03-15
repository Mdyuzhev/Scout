# SC-004 — Retrieval: поиск и формирование пакета данных

## Цель

Реализовать слой получения данных: семантический поиск по ChromaDB-индексу и
формирование `ResearchPackage` — структурированного пакета, который агент
получает в ответ на `scout_search`. После этой задачи Scout умеет находить
релевантные чанки по произвольному запросу и упаковывать их в удобный формат.

---

## Контекст

Retrieval — это выходные ворота системы перед LLM. Код `Searcher` практически
идентичен `E:\RAG_qa\src\retrieval\searcher.py` — нужна адаптация под
новые модели данных (Pydantic v2, `SearchResult` из `src/config.py`).

`ContextBuilder` — новый компонент: собирает результаты поиска, форматирует
метаданные, вычисляет статистику и возвращает готовый `ResearchPackage`.

---

## Шаги выполнения

### 1. Searcher (src/retrieval/searcher.py)

Порт из RAG-QA с адаптацией под новые типы:

```python
class Searcher:
    def __init__(self, chroma_path: str, model_name: str):
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=model_name)

    def search(
        self,
        query: str,
        session_id: UUID,
        top_k: int = 10,
        min_similarity: float = 0.60,
    ) -> list[SearchResult]:
        collection_name = f"session_{session_id.hex}"
        # Получить коллекцию, выполнить query, отфильтровать по similarity
        # Нормализовать дистанцию ChromaDB в similarity: 1 / (1 + distance)
        ...
```

Важный момент: если коллекция для `session_id` не существует — бросать
`SessionNotFoundError` с понятным сообщением, а не общий ChromaDB exception.

### 2. ContextBuilder (src/retrieval/context_builder.py)

Принимает результаты поиска и собирает `ResearchPackage`:

```python
class ContextBuilder:
    def build(
        self,
        session: ResearchSession,
        query: str,
        results: list[SearchResult],
        total_in_index: int,
    ) -> ResearchPackage:
        # Отсортировать результаты по similarity (убывание)
        # Дедуплицировать по source_url — не более 3 чанков с одного источника
        # Заполнить ResearchPackage
        ...
```

Дедупликация по источнику важна: если один длинный документ даёт 10 похожих чанков,
агент получит монотонный контекст. Ограничение "не более 3 с источника" обеспечивает
разнообразие.

### 3. Тест (tests/test_retrieval.py)

Создать тестовую ChromaDB-коллекцию с несколькими документами, выполнить поиск,
проверить что результаты отсортированы по similarity и дедуплицированы корректно.

---

## Критерии готовности

- `Searcher.search()` возвращает `list[SearchResult]` отфильтрованный по `min_similarity`
- `ContextBuilder.build()` возвращает корректный `ResearchPackage` без дубликатов источников
- Тесты проходят

---

*Дата создания: 2026-03-16*

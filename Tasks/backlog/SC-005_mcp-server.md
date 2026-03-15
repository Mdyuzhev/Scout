# SC-005 — MCP-сервер: scout_index / scout_search / scout_brief

## Цель

Собрать всё вместе в рабочий MCP-сервер. Реализовать три основных инструмента
и связать их с компонентами Ingestion и Retrieval. После этой задачи Scout
является полноценным MCP-сервером — агент может вызывать инструменты и получать
реальные результаты исследования.

---

## Контекст

`mcp_server.py` — главная точка сборки проекта. За основу берём паттерн из
`E:\LocOll\mcp-server\server.py`: FastMCP 2.0, регистрация инструментов
через декоратор, транспорт `streamable-http`.

На этом этапе PostgreSQL ещё не подключён (это SC-006). Сессии хранятся
в памяти (`dict`) — временное решение для POC, которое SC-006 заменит.

---

## Шаги выполнения

### 1. Pipeline (src/pipeline.py)

Оркестратор, который агрегирует все компоненты и реализует основной
рабочий цикл:

```python
class ScoutPipeline:
    def __init__(self, config_path: str = ".env"):
        # Инициализировать все компоненты из env-переменных:
        # WebCollector, SlidingWindowChunker, Indexer, Searcher, ContextBuilder
        # Временное хранилище сессий: self._sessions: dict[UUID, ResearchSession]
        ...

    async def index(self, config: ResearchConfig) -> ResearchSession:
        # 1. Создать ResearchSession со статусом PENDING
        # 2. Собрать документы через WebCollector
        # 3. Нарезать через SlidingWindowChunker
        # 4. Проиндексировать через Indexer
        # 5. Обновить статус на READY, заполнить counts
        # 6. Вернуть сессию
        ...

    def search(self, session_id: UUID, query: str, top_k: int = 10) -> ResearchPackage:
        # Найти сессию → Searcher.search() → ContextBuilder.build()
        ...
```

### 2. Инструменты MCP (mcp_server.py)

**`scout_index`** — запустить сбор и индексацию:
```
Параметры:
  topic: str — главная тема исследования
  depth: str — "quick" | "normal" | "deep" (default: "normal")
  queries: list[str] — дополнительные поисковые запросы (опционально)
  language: str — язык контента (default: "ru")
  llm_provider: str — "anthropic" | "ollama" (default: "anthropic")

Возвращает:
  session_id: str
  status: str
  documents_count: int
  chunks_count: int
  message: str
```

**`scout_search`** — семантический поиск по сессии:
```
Параметры:
  session_id: str
  query: str — поисковый запрос
  top_k: int — количество результатов (default: 10)

Возвращает:
  session_id: str
  query: str
  results: list[{text, source_url, source_title, similarity}]
  total_in_index: int
```

**`scout_brief`** — сгенерировать brief через LLM:
```
Параметры:
  session_id: str
  query: str — на что сфокусировать brief
  top_k: int — сколько чанков использовать как контекст (default: 10)

Возвращает:
  brief: str
  sources_used: int
  model: str
  tokens_used: int | null
```

### 3. AnthropicBriefer (src/llm/anthropic_briefer.py)

Паттерн один-в-один из `E:\moex\src\brain\explainer.py`: принимает
`ResearchPackage`, строит промпт с контекстом из чанков, вызывает
`claude-haiku-4-5-20251001`, возвращает текст. При ошибке — возвращает None,
не бросает исключения. Системный промпт: роль аналитика, задача — синтез
из предоставленного контекста, без выдумывания информации вне контекста.

### 4. Запуск

```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8020")))
```

---

## Критерии готовности

- `python mcp_server.py` стартует без ошибок
- Полный цикл вручную: `scout_index(topic="FastAPI best practices")` →
  `scout_search(session_id=..., query="dependency injection")` →
  `scout_brief(session_id=..., query="dependency injection")` — работает end-to-end
- Результат `scout_brief` содержит связный текст на русском или английском
  основанный на реально собранных данных

---

*Дата создания: 2026-03-16*

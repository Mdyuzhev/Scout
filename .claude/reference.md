# reference.md — Scout

Справочник. Читать по запросу, не при каждом старте.

---

## Архитектура

```
Агент (Claude Code)
    │  MCP: scout_index / scout_search / scout_brief
    ▼
Scout MCP Server (FastMCP 2.0, порт 8020, network_mode: host)
    ├── Ingestion: WebCollector → SlidingWindowChunker → Indexer (ChromaDB)
    └── Retrieval: Searcher → ContextBuilder → ResearchPackage
    │
    └── LLM (Anthropic Haiku / Ollama) — только финальный brief
```

**Детерминированный слой** (без LLM): сбор, очистка, нарезка, векторизация, фильтрация.
**LLM-слой**: только `scout_brief` — синтез из готового пакета данных.

**Хранилище**:
- PostgreSQL (порт 5436) — история сессий, tsvector + GIN для полнотекстового поиска
- ChromaDB — векторные индексы, коллекция `session_{id}` на каждую сессию

**Логика "сначала проверь историю"**: перед сбором данных Scout ищет
похожую сессию в PostgreSQL (по теме, в рамках `cache_ttl_hours`).

---

## Стек и зависимости

| Компонент | Технология |
|-----------|-----------|
| MCP Framework | FastMCP 2.0+ |
| HTTP клиент | httpx |
| Web parsing | httpx + BeautifulSoup4 |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| Vector DB | ChromaDB (persistent) |
| Data lake | PostgreSQL 16 (порт 5436) |
| LLM | anthropic SDK (Haiku) + openai SDK (Ollama) |
| Логи | loguru |
| Deploy | Docker Compose + GitHub Actions CI |

---

## Структура проекта

```
Scout/
├── src/
│   ├── config.py               # ResearchConfig, ResearchSession, ResearchPackage
│   ├── ingestion/
│   │   ├── base.py             # BaseCollector
│   │   └── web.py              # WebCollector (httpx + BS4)
│   ├── chunking/
│   │   ├── base.py             # BaseChunker
│   │   └── sliding_window.py   # SlidingWindowChunker
│   ├── retrieval/
│   │   ├── searcher.py         # Searcher (ChromaDB)
│   │   └── context_builder.py  # ContextBuilder → ResearchPackage
│   ├── llm/
│   │   ├── base.py             # BaseBriefer
│   │   └── anthropic_briefer.py
│   └── storage/
│       ├── vector_store.py     # ChromaDB обёртка
│       └── session_store.py    # PostgreSQL: история сессий
├── mcp_server.py               # FastMCP entrypoint
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Порты на сервере

| Порт | Сервис |
|------|--------|
| 8020 | Scout MCP |
| 5436 | Scout PostgreSQL |
| 8765 | Homelab MCP |
| 8010 | LocOll backend |
| 8001 | RAG-QA API |

---

## Ключевые команды (через homelab MCP: run_shell_command)

```bash
# Деплой
cd /opt/scout && docker compose up -d --build 2>&1 | tail -30

# Логи
docker logs scout-mcp --tail 50

# Health check
curl -s http://localhost:8020/health

# Статус
docker ps --filter name=scout --format "{{.Names}} {{.Status}}"

# PostgreSQL
docker exec scout-postgres psql -U scout_user -d scout_db -c "\dt"
```

---

## Известные особенности FastMCP 2.0

- Конструктор: только `FastMCP("name")` — `description=` не принимает
- Транспорт: `transport="http"` (не `"streamable-http"`)
- `custom_route` с dict не работает — нужен `JSONResponse` из starlette
- `/health` реализован через `@mcp.custom_route`

---

## Доноры компонентов

- **RAG-QA** (`E:\RAG_qa`): `searcher.py`, `chunker.py` — основа retrieval-слоя
- **MOEX** (`E:\moex`): паттерн `explainer.py` — LLM только для финального шага
- **Homelab MCP** (`E:\LocOll\mcp-server`): паттерн FastMCP-сервера

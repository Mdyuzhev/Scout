# SC-001 — Scaffold: структура проекта

## Цель

Создать базовую структуру проекта Scout на сервере и локально: директории, зависимости,
конфиги Docker, переменные окружения. После этой задачи у нас есть пустой, но
правильно организованный проект, готовый к наполнению кодом.

---

## Контекст

Проект живёт в двух местах:
- Локально: `E:\Scout` (разработка)
- На сервере: `/opt/scout` (production)

За основу структуры берём паттерн из RAG-QA (`E:\RAG_qa`) и Homelab MCP
(`E:\LocOll\mcp-server`). Деплой через GitHub Actions self-hosted runner —
паттерн такой же как в LocOll.

Порт Scout MCP: **8020** (свободен на сервере).
Порт PostgreSQL: **5436** (свободен, по аналогии с 5434/5435 у других проектов).

---

## Шаги выполнения

### 1. Локальная структура директорий

Создать в `E:\Scout\src\`:

```
src/
├── config.py
├── ingestion/
│   ├── __init__.py
│   ├── base.py
│   └── web.py
├── chunking/
│   ├── __init__.py
│   ├── base.py
│   └── sliding_window.py
├── retrieval/
│   ├── __init__.py
│   ├── searcher.py
│   └── context_builder.py
├── llm/
│   ├── __init__.py
│   ├── base.py
│   └── anthropic_briefer.py
└── storage/
    ├── __init__.py
    ├── vector_store.py
    └── session_store.py
```

Также создать: `mcp_server.py` в корне, `tests/` с `__init__.py`.

### 2. requirements.txt

```
fastmcp>=2.0
httpx>=0.27
beautifulsoup4>=4.12
sentence-transformers>=3.0
chromadb>=0.5
asyncpg>=0.29
pydantic>=2.7
anthropic>=0.30
openai>=1.40        # для Ollama через OpenAI-совместимый API
loguru>=0.7
python-dotenv>=1.0
```

### 3. .env.example

```env
# Server
MCP_HOST=0.0.0.0
MCP_PORT=8020

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5436
POSTGRES_DB=scout_db
POSTGRES_USER=scout_user
POSTGRES_PASSWORD=

# ChromaDB
CHROMA_PATH=./data/chroma_db

# Embeddings
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# LLM
LLM_PROVIDER=anthropic          # anthropic | ollama
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral

# Research defaults
DEFAULT_DEPTH=normal            # quick | normal | deep
DEFAULT_CACHE_TTL_HOURS=24
MIN_SIMILARITY=0.60
```

### 4. docker-compose.yml

Два сервиса: `scout-mcp` (Python, порт 8020, network_mode: host) и
`scout-postgres` (PostgreSQL 16-alpine, порт 5436).

```yaml
services:
  scout-postgres:
    image: postgres:16-alpine
    container_name: scout-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-scout_db}
      POSTGRES_USER: ${POSTGRES_USER:-scout_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5436:5432"
    volumes:
      - scout_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-scout_user}"]
      interval: 10s
      timeout: 5s
      retries: 5

  scout-mcp:
    build: .
    container_name: scout-mcp
    network_mode: host
    env_file: .env
    volumes:
      - scout_chroma_data:/app/data/chroma_db
    depends_on:
      scout-postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  scout_postgres_data:
  scout_chroma_data:
```

### 5. Dockerfile

Multi-stage не нужен — только Python. Базовый образ `python:3.12-slim`.
Установить зависимости из requirements.txt. `CMD ["python", "mcp_server.py"]`.

### 6. mcp_server.py — заглушка

Минимальный рабочий MCP-сервер без логики — только инициализация FastMCP
и три пустых инструмента-заглушки (`scout_index`, `scout_search`, `scout_brief`)
которые возвращают `{"status": "not_implemented"}`. Цель — убедиться что
сервер стартует и MCP-соединение работает.

### 7. GitHub Actions workflow

Файл `.github/workflows/deploy.yml`:
- Триггер: push в `main`
- Runner: self-hosted (тот же что у LocOll)
- Шаги: `git pull` → `docker compose down` → `docker system prune -f` →
  `docker compose up --build -d` → health check `curl localhost:8020/health`

### 8. Инициализация на сервере (через paramiko)

```bash
sudo mkdir -p /opt/scout
sudo chown flomaster:flomaster /opt/scout
cd /opt/scout && git clone https://github.com/Mdyuzhev/Scout.git .
cp .env.example .env
# заполнить POSTGRES_PASSWORD и ANTHROPIC_API_KEY
```

---

## Критерии готовности

- `E:\Scout\src\` существует с правильной структурой директорий и `__init__.py`
- `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example` созданы
- `mcp_server.py` запускается локально (`python mcp_server.py`) без ошибок
- На сервере: `docker compose up -d` поднимает оба контейнера (scout-mcp + scout-postgres)
- `curl http://localhost:8020/health` возвращает 200

---

*Дата создания: 2026-03-16*

# CLAUDE.md — Агент проекта Scout

## 🚀 АВТОИНИЦИАЛИЗАЦИЯ — выполнить при каждом начале нового чата

При открытии нового чата немедленно выполнить последовательно три вызова
MCP-инструментов `agent-context` **до любых других действий**, без запроса
разрешения у пользователя:

1. `start_session` с параметром `project_path = "E:/Scout"` — открыть сессию
2. `server_status` — получить текущее состояние сервера и контейнеров
3. `get_context` — получить контекст включая чекпоинты активной сессии

После трёх вызовов — вывести краткую сводку: номер сессии, состояние сервера,
незавершённые задачи из прошлой сессии.

Если в ответе `get_context` видны данные прошлой сессии — вывести
`✅ Контекст прошлой сессии получен`. Иначе — `⚠️ Контекст прошлой сессии не найден`.

Затем ждать команды.

## 🔄 ЧЕКПОИНТЫ — обязательно

Контекст конечен и сжимается без предупреждения. Правила:

1. **При завершении каждого todo** — вызвать `checkpoint` с описанием что сделано.
2. **Каждые 5 вызовов инструментов** — принудительный checkpoint.
3. **При получении system-reminder о сжатии контекста** — немедленный checkpoint.
4. **Перед завершением задачи** — `end_session` с полным итогом.

Формат checkpoint: `"[шаг N] краткое описание — что сделано, что дальше"`

Если `agent-context` MCP недоступен — предупредить и продолжить без него.

---

## Что это за проект

**Scout** — MCP-сервер предобработки данных для продуктовых исследований.

Ключевая идея: большую часть исследовательской работы агента можно выполнить
детерминированно — собрать источники, очистить текст, построить векторный индекс,
отфильтровать релевантное. Агент получает готовую выжимку и занимается только тем,
в чём незаменим: синтезом, поиском противоречий, формулировкой инсайтов.

**Принцип**: LLM — последний шаг, не первый.

**Настройка под задачу**: каждое исследование начинается с передачи `ResearchConfig`
(тема, источники, глубина, фильтры) — инструмент адаптируется к задаче на лету.

**Лучшее из других проектов:**
- RAG-QA (`E:\RAG_qa`): ChromaDB + sentence-transformers + chunker — готовое ядро поиска
- MOEX (`E:\moex`): паттерн "детерминированный анализ → LLM только для объяснения"
- Homelab MCP (`E:\LocOll\mcp-server`): FastMCP 2.0 + streamable-http — паттерн MCP-сервера

**Владелец**: Flomaster (Михаил)
**GitHub**: `github.com/Mdyuzhev/Scout` (создать при первом деплое)

---

## 🔴 КРИТИЧНО: КАК ПОДКЛЮЧАТЬСЯ К СЕРВЕРУ

**Голый `ssh` и `sshpass` НЕ РАБОТАЮТ.** Среда агента — Windows с кириллическим
именем пользователя (`C:\Users\Михаил`). Ломается путь к `~/.ssh/known_hosts`.

**Единственный правильный способ — Python + paramiko. Всегда. Без исключений.**

```python
import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('100.81.243.12', username='flomaster', password='Misha2021@1@', timeout=10)
_, stdout, stderr = client.exec_command('КОМАНДА')
print(stdout.read().decode('utf-8', errors='replace').strip())
client.close()
```

| Параметр | Значение |
|----------|----------|
| **Host (основной)** | **100.81.243.12** (Tailscale — работает всегда) |
| Host (LAN fallback) | 192.168.1.74 (только домашняя сеть) |
| User | flomaster |
| Password | Misha2021@1@ |
| Путь проекта на сервере | /opt/scout |
| Порт Scout MCP | **8020** |

---

## 🖥️ Сервер (актуально 2026-03-16)

Полный снимок инфраструктуры: `E:\LocOll\snapshot140326.md`

| Параметр | Значение |
|----------|---------|
| ОС | Ubuntu 24.04.3 LTS |
| CPU | Intel i7-9750HF, 6 cores / 12 threads |
| RAM | 23.4 GiB total, ~3.8 GiB used (16%) |
| Docker | 29.3.0, Compose v5.1.0 |
| Python | 3.12.13 |
| CI/CD | GitHub Actions self-hosted runner (`/home/flomaster/actions-runner/`) |

### Занятые порты (важно при деплое)

| Порт | Сервис |
|------|--------|
| 8001 | RAG-QA API |
| 8002 | ErrorLens API |
| 8010 | LocOll backend |
| 8765 | Homelab MCP |
| **8020** | **Scout MCP ← наш** |

### AI/LLM на сервере

- **Ollama** — systemd-сервис, порт `11434`, CPU-only
- Загружены: `mistral:latest` (4.2GB), `tinyllama:latest` (608MB)
- **⚠️ Новые модели не тянуть** — только существующие
- Для финального синтеза (brief): **Anthropic API** (Haiku по умолчанию)
- Для offline/локального режима: Ollama mistral

---

## 🏗️ Архитектура Scout

```
Агент (Claude Code / любой MCP-клиент)
        │
        │  MCP tools: scout_index / scout_search / scout_brief
        ▼
┌──────────────────────────────────────────────────────┐
│  Scout MCP Server (FastMCP 2.0, порт 8020)           │
│  streamable-http, network_mode: host                 │
│                                                      │
│  ┌──────────────────┐   ┌──────────────────────────┐ │
│  │  Ingestion       │   │  Retrieval               │ │
│  │  ──────────────  │   │  ──────────────────────  │ │
│  │  web_collector   │   │  Searcher (ChromaDB)     │ │
│  │  doc_parser      │   │  reranker                │ │
│  │  chunker         │   │  context_builder         │ │
│  │  indexer         │   └──────────────────────────┘ │
│  └──────────────────┘                                │
│                                                      │
│  ResearchConfig → настройка под каждую задачу        │
│  LLM (Anthropic Haiku / Ollama) → только финал       │
└──────────────────────────────────────────────────────┘
        │
        │  research_package: топ-N чанков + метаданные
        ▼
   Агент синтезирует отчёт
```

### Детерминированный слой (без LLM):
- Сбор источников: web scraping, парсинг документов
- Очистка и нормализация текста, дедупликация
- Chunking по семантически богатым единицам
- Векторная индексация (sentence-transformers + ChromaDB)
- Семантическая фильтрация по cosine similarity

### LLM-слой (только там где необходимо):
- Финальное переранжирование при широких или нечётких темах
- Генерация `research_brief` из топ-N релевантных чанков

---

## 🛠️ Технологический стек

| Компонент | Технология |
|-----------|-----------|
| MCP Framework | FastMCP 2.0+ |
| HTTP клиент | httpx |
| Web parsing | httpx + BeautifulSoup4 |
| Embeddings | sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`) |
| Vector DB | ChromaDB (persistent) |
| LLM клиент | anthropic SDK + openai SDK (для Ollama) |
| Логи | loguru |
| Deploy | Docker Compose + GitHub Actions CI |

**Модель эмбеддингов** — та же что в RAG-QA, уже проверена в production на сервере.
Не требует дополнительных загрузок.

---

## 📁 Целевая структура проекта

```
Scout/
├── src/
│   ├── config.py               # ResearchConfig + глобальный конфиг
│   ├── ingestion/
│   │   ├── web_collector.py    # сбор данных из веба (httpx + BS4)
│   │   ├── doc_parser.py       # парсинг локальных документов (txt, md, pdf)
│   │   ├── chunker.py          # семантически богатые чанки (из RAG-QA)
│   │   └── indexer.py          # индексация в ChromaDB
│   ├── retrieval/
│   │   ├── searcher.py         # семантический поиск (из RAG-QA)
│   │   ├── reranker.py         # переранжирование кандидатов
│   │   └── context_builder.py  # формирование research_package
│   └── llm/
│       └── briefer.py          # генерация brief — только финальный шаг
├── mcp_server.py               # FastMCP entrypoint + инструменты
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── Tasks/
│   ├── backlog/                # SC-NNN_slug.md (ожидают выполнения)
│   └── done/                   # SC-NNN_slug.md (выполненные)
└── .claude/                    # этот каталог
    ├── CLAUDE.md
    ├── settings.json
    └── commands/
        ├── init.md
        ├── task.md
        ├── fin.md
        └── fix_context.md
```

---

## ⚡ Ключевые команды (через paramiko)

```bash
# Деплой
cd /opt/scout && docker compose up -d --build 2>&1 | tail -30

# Логи
docker logs -f scout-mcp-1

# Health check
curl -s http://localhost:8020/health

# Тест MCP инструментов
curl -s http://localhost:8020/tools
```

---

## 📋 Реестр задач

| ID | Название | Статус |
|----|----------|--------|
| SC-001 | project-scaffold | 🔲 в очереди |

Файлы задач: `E:\Scout\Tasks\backlog\SC-NNN_slug.md` (в работе),
`E:\Scout\Tasks\done\SC-NNN_slug.md` (выполненные)

---

## 🚫 Запрещено

- `ssh`, `sshpass` — только paramiko
- Тянуть новые модели Ollama
- LLM на этапе сбора/фильтрации данных (только финальный шаг)
- K3s, GitLab — удалены с сервера

---

*Последнее обновление: 2026-03-16 (инициализация проекта)*

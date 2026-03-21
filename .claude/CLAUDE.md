# CLAUDE.md — Scout

## Начало работы

При открытии нового чата — запустить /init.
Для полного среза сервера — /server-status.

---

## ЧЕКПОИНТЫ — обязательно

Контекст разговора конечен и сжимается без предупреждения:

1. При завершении каждого шага задачи — вызвать `mcp__agent-context__checkpoint`
2. Каждые 5 вызовов инструментов — принудительный checkpoint
3. При system-reminder о сжатии контекста — немедленный checkpoint
4. Перед завершением задачи — `end_session` с полным итогом

Формат: `"[шаг N] что сделано — что дальше"`

Если agent-context недоступен — предупредить и продолжить без него.

---

## 🔀 Мультиагентный режим

Если задача допускает параллелизм — **используй мультиагентный режим**.

Когда применять:
- Изменения в нескольких независимых файлах/модулях
- Обновление конфигов в нескольких проектах одновременно
- Параллельные проверки (тесты, lint, health-check)
- Исследование кодовой базы по нескольким направлениям

Когда НЕ применять:
- Шаги зависят друг от друга (результат одного нужен для следующего)
- Работа с одним файлом
- Простые линейные задачи

Принцип: максимум параллельных агентов при независимых подзадачах, строгая последовательность при зависимостях.

---

## О проекте

**Scout** — MCP-сервер предобработки данных для продуктовых исследований.
Принцип: LLM — последний шаг, не первый.
GitHub: https://github.com/Mdyuzhev/Scout

Стек: Python 3.12, FastMCP 2.0, ChromaDB, PostgreSQL (порт 5436),
sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`), httpx, BS4.

Пайплайн: `ResearchConfig → WebCollector → Chunker → ChromaDB → Searcher → ResearchPackage → LLM brief`

Контейнеры на сервере: `scout-mcp` (порт 8020), `scout-mcp-2` (порт 8021),
`scout-chroma` (порт 8000, общий), `scout-postgres` (порт 5436, общий),
`scout-redis` (только через scout-net, без внешнего порта).
Нечётные задачи роя → :8020, чётные → :8021.
Путь на сервере: `/opt/scout`

**Конфигурация нод:**
| Параметр | Primary | Secondary | Shared |
|----------|---------|-----------|--------|
| host | 192.168.1.74 | 192.168.1.74 | — |
| mcp_port | 8020 | 8021 | — |
| project | scout | scout-2 | — |
| chroma_port | — | — | 8000 |
| postgres_port | — | — | 5436 |

---

## Деплой

**ВАЖНО: `deploy_project("scout", build=True)` НЕ ИСПОЛЬЗОВАТЬ** —
timeout 300s, а build занимает 10-20 мин (Playwright + sentence-transformers = ~10GB образ).

### Процедура деплоя — 7 последовательных шагов

Каждый шаг проверяет завершение предыдущего перед продолжением.

**Шаг 1. Git pull**
```bash
run_shell_command("cd /opt/scout && git pull origin main")
```
Проверка: exit_code == 0

**Шаг 2. Build образа (ОТДЕЛЬНО от запуска)**
```bash
run_shell_command("cd /opt/scout && docker compose build scout-mcp", timeout=600)
```
Timeout: 600s. Если requirements.txt не менялся — Docker cache, ~30с.
Проверка: exit_code == 0

**Шаг 3. Поднять инфру (postgres, chroma, redis)**
```bash
run_shell_command("cd /opt/scout && docker compose up -d scout-postgres scout-chroma scout-redis")
```
Проверка: все 3 healthy:
```bash
run_shell_command("docker ps --filter name=scout-postgres --filter name=scout-chroma --filter name=scout-redis --format '{{.Names}}: {{.Status}}'")
```

**Шаг 4. Поднять MCP ноды (образ уже собран)**
```bash
run_shell_command("cd /opt/scout && docker compose up -d scout-mcp scout-mcp-2")
```
Проверка: контейнеры running

**Шаг 5. Ждать healthcheck (~30-45с)**
```bash
run_shell_command("sleep 30 && curl -s http://localhost:8020/health && echo '---' && curl -s http://localhost:8021/health")
```
Проверка: оба `{"status":"ok"}`. Если unhealthy — логи: `get_service_logs("scout")`

**Шаг 6. notify_deploy**
```
notify_deploy("scout")
```
Проверка: verdict VERIFIED_OK

**Шаг 7. Smoke-test (опционально)**
MCP init → scout_research_async → poll → completed

### Когда нужен build (шаг 2)

| Что изменилось | Build? | Время |
|---|---|---|
| Только `.py` файлы | `docker compose build scout-mcp` (cache pip/playwright) | ~30-60с |
| `requirements.txt` | `docker compose build --no-cache scout-mcp` | 10-20 мин |
| `Dockerfile` | `docker compose build --no-cache scout-mcp` | 10-20 мин |
| Только `.env` | Пропустить шаг 2, в шаге 4 добавить `--force-recreate` | ~30с |

scout-mcp и scout-mcp-2 используют **один образ** — build один раз.

### deploy_project — только для лёгких деплоев

`deploy_project("scout")` (без build) допустим когда:
- Изменились только `.py` файлы И образ уже актуален
- Нет изменений в requirements.txt/Dockerfile

### Инфраструктура деплоя (уже настроена, не трогать)

| Компонент | Статус |
|-----------|--------|
| `/opt/scout` | ✅ клонирован |
| `.env` | ✅ заполнен |
| GitHub Actions runner | ✅ `scout-homelab` systemd |
| `deploy.yml` | ✅ триггер на push в main |

---

## MCP-инструменты (homelab-mcp)

Все операции с сервером — через `mcp__homelab__*`. Не использовать
`run_shell_command` там где есть специализированный инструмент.

### Диагностика
| Инструмент | Использование |
|-----------|--------------|
| `get_service_logs("scout")` | Логи MCP-сервера |
| `get_service_logs("scout-2")` | Логи второй ноды MCP |
| `get_service_logs("scout-postgres")` | Логи БД |
| `get_docker_stats(project="scout")` | CPU/RAM per контейнер |
| `run_health_check(project="scout")` | Статус сервисов проекта |
| `run_health_check(project="scout-2")` | Статус второй ноды |
| `git_status("scout")` | Что сейчас задеплоено |
| `git_log("scout", n=5)` | Последние коммиты на сервере |

### Деплой
| Инструмент | Использование |
|-----------|--------------|
| `deploy_project("scout")` | git pull + compose up + health + logs |
| `deploy_project("scout", build=True)` | + пересборка, health check с retry (до 5 попыток) |
| `deploy_project("scout-2")` | Деплой второй ноды |
| `restart_and_verify("scout")` | Рестарт + проверка + логи |
| `run_health_check(project="scout", no_cache=True)` | Свежие метрики без кэша |

### Выполнение команд в контейнере
| Инструмент | Использование |
|-----------|--------------|
| `exec_in_container("scout-mcp", "команда")` | Любая команда внутри |
| `exec_in_container("scout-postgres", "psql -U scout -d scout -c 'SELECT ...'")` | SQL в БД |
| `grep_docker_logs("scout-mcp", "ERROR")` | Поиск по логам |

---

## КАК ПОДКЛЮЧАТЬСЯ К СЕРВЕРУ

**Homelab MCP** — основной способ (см. таблицу MCP-инструменты выше)

**Paramiko** — только если homelab MCP недоступен, только после явного разрешения:

```python
import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.1.74', username='flomaster', password='Misha2021@1@', timeout=10)
_, stdout, stderr = client.exec_command('КОМАНДА')
print(stdout.read().decode('utf-8', errors='replace').strip())
client.close()
```

LAN (дома): `192.168.1.74` | Tailscale (удалённо): `100.81.243.12`
ssh/sshpass НЕ РАБОТАЮТ — кириллический `C:\Users\Михаил`.

---

## ⚠️ Важные технические правила

**FastMCP 2.0 — MCP Streamable HTTP протокол:**

1. Сначала `initialize` → получить `Mcp-Session-Id` из заголовка ответа
2. Все последующие запросы передают `-H "Mcp-Session-Id: <id>"`
3. Два обязательных заголовка на каждый запрос:

```bash
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <id>" \
  -d '...'
```

**SSE-парсинг** — ответ приходит в формате `event: message\ndata: {...}`.
НЕЛЬЗЯ: `body.startswith("data:")` — первая строка `event:`, не `data:`.
НУЖНО: искать строку построчно. Шаблон в `.claude/reference.md`.

**Процедура запуска исследования — сначала тест на 10 URL:**
Перед полным прогоном (100-400 URL) ВСЕГДА делать тест на первых 10 URL.
Убедиться что: `status: ready`, `documents_count > 0`, поиск даёт результаты.
Только после прохождения теста запускать полный пул.
Шаблон теста — в `.claude/reference.md` раздел "Процедура запуска нового исследования".

---

## Реестр задач

| ID | Название | Статус |
|----|----------|--------|
| SC-001 | project-scaffold | ✅ выполнена |
| SC-002 | data-models | ✅ выполнена |
| SC-003 | ingestion | ✅ выполнена |
| SC-004 | retrieval | ✅ выполнена |
| SC-005 | mcp-server | ✅ выполнена |
| SC-006 | postgres-session-store | ✅ выполнена |
| SC-007 | deploy | ✅ выполнена |
| SC-008 | first-real-run | ✅ выполнена |
| SC-009 | connect-llm-brief | ✅ выполнена |
| SC-010 | three-iterations | ✅ выполнена |
| SC-011 | dual-input-mode | ✅ выполнена |
| SC-012 | batch-200-urls | ✅ выполнена |
| SC-013 | batch-500-urls | ✅ выполнена |
| SC-014 | batch-ai-tools | ✅ выполнена |
| SC-015 | rostelecom-videosurveillance | ✅ выполнена |
| SC-016 | collector-level1 | ✅ выполнена |
| SC-017 | collector-level2-playwright | ✅ выполнена |
| SC-017.1 | auto-market-russia (v2) | ✅ выполнена |
| SC-017.2 | apartments-russia | ✅ выполнена |
| SC-017.3 | inflation-russia | ✅ выполнена |
| SC-018 | local-file-collector | ✅ выполнена |
| SC-019 | reranker | ✅ выполнена |
| SC-020 | scout-research-tool | ✅ выполнена |
| SC-021 | auto-url-collection | ✅ выполнена |
| SC-022 | briefer-retry-async | ✅ выполнена |
| SC-033 | stabilization (13 fixes) | ✅ выполнена |
| SC-034 | redis-streaming | ✅ выполнена |

Задачи: `Tasks/backlog/` (в работе), `Tasks/done/` (выполненные)

---

## Запрещено

- ssh, sshpass — только homelab MCP или paramiko
- Деплоить вручную — только через git push → CI/CD
- Настраивать /opt/scout или runner повторно — уже сделано
- LLM на этапе сбора/фильтрации (только финальный шаг)
- curl к MCP без заголовка `Accept: application/json, text/event-stream`
- `body.startswith("data:")` для SSE-парсинга — только построчный поиск
- `docker restart` для обновления env — только `--force-recreate --no-deps`
- `docker compose down` без указания сервисов — убивает ВСЕ контейнеры проекта + сеть. Proxy gateway меняется!
- Порт 6380 на хосте — homelab-redis, НЕ scout-redis (scout-redis без внешнего порта)
- Брать ANTHROPIC_API_KEY из других проектов — только от пользователя явно
- Запускать полный URL-пул без предварительного теста на 10 URL
- Конструировать URL по шаблону без верификации — только URL из поиска

---

Полный справочник: `.claude/reference.md`

*Обновлено: 2026-03-20 (dual-node: scout-mcp-2:8021, scout-chroma:8000, /swarm команда)*

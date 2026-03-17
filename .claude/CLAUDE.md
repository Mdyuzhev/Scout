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

## О проекте

**Scout** — MCP-сервер предобработки данных для продуктовых исследований.
Принцип: LLM — последний шаг, не первый.
GitHub: https://github.com/Mdyuzhev/Scout

Стек: Python 3.12, FastMCP 2.0, ChromaDB, PostgreSQL (порт 5436),
sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`), httpx, BS4.

Пайплайн: `ResearchConfig → WebCollector → Chunker → ChromaDB → Searcher → ResearchPackage → LLM brief`

Контейнеры на сервере: `scout-mcp` (порт 8020), `scout-postgres` (порт 5436).
Путь на сервере: `/opt/scout`

---

## ДЕПЛОЙ — единственный правильный флоу

```
1. Пишем/правим код локально (E:\Scout)
2. git add + git commit + git push origin main
3. GitHub Actions runner scout-homelab подхватывает push автоматически
4. CI: git pull → docker compose up --build -d → health check
5. Проверяем результат через homelab MCP: docker ps, curl /health
6. Завершаем задачу → обновляем CLAUDE.md → git push → checkpoint
```

**Агент НИКОГДА не деплоит вручную** — ни через homelab MCP, ни через paramiko.
Исключение: первичная настройка `/opt/scout` — уже выполнена, повторять не нужно.

### Инфраструктура деплоя (уже настроена, не трогать)

| Компонент | Статус |
|-----------|--------|
| `/opt/scout` | ✅ клонирован |
| `.env` | ✅ заполнен |
| GitHub Actions runner | ✅ `scout-homelab` systemd |
| `deploy.yml` | ✅ триггер на push в main |

---

## КАК ПОДКЛЮЧАТЬСЯ К СЕРВЕРУ

**Homelab MCP** — основной способ:
- `run_shell_command`, `exec_in_container`, `get_services_status`, `get_service_logs`

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
- Брать ANTHROPIC_API_KEY из других проектов — только от пользователя явно
- Запускать полный URL-пул без предварительного теста на 10 URL
- Конструировать URL по шаблону без верификации — только URL из поиска

---

Полный справочник: `.claude/reference.md`

*Обновлено: 2026-03-17 (SC-017.3 done — инфляция/ставка ЦБ РФ 2024-2025, 203 docs, 720 chunks, brief Haiku 23k токенов)*

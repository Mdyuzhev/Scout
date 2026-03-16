# SC-009 — Подключить LLM и запустить первые брифы

## Цель

Получить API ключ от пользователя, сохранить в GitHub Secrets и в `.env` на сервере,
запустить `scout_brief` на двух готовых сессиях (product analytics + AI tools),
оценить качество финального LLM-шага.

**Модель**: `claude-haiku-4-5-20251001` — быстрая и дешёвая, идеальна для первой проверки.

---

## Шаг 1 — Запросить API ключ у пользователя

Агент должен явно попросить:

```
Для SC-009 нужен ANTHROPIC_API_KEY.
Пожалуйста, передай ключ — начинается с "sk-ant-..."
```

**Не брать ключ из других проектов** (`/opt/moex/.env` и т.д.) — ключ вводит пользователь явно.

---

## Шаг 2 — Сохранить ключ в GitHub Secrets

Через homelab MCP (`run_shell_command`) — добавить секрет в репозиторий Scout через GitHub CLI:

```bash
# Проверить наличие gh cli
which gh && gh --version

# Авторизоваться если нужно (токен уже есть в .git-credentials)
gh auth status

# Добавить секрет в репозиторий
echo "sk-ant-..." | gh secret set ANTHROPIC_API_KEY --repo Mdyuzhev/Scout
```

Проверить что секрет добавлен:
```bash
gh secret list --repo Mdyuzhev/Scout
```

---

## Шаг 3 — Записать ключ в .env на сервере

```bash
# Записать ключ (заменить sk-ant-... на реальный ключ от пользователя)
sed -i 's/^ANTHROPIC_API_KEY=.*/ANTHROPIC_API_KEY=sk-ant-.../' /opt/scout/.env

# Проверить (показать только первые 20 символов для безопасности)
grep ANTHROPIC_API_KEY /opt/scout/.env | cut -c1-35
```

---

## Шаг 4 — Проверить модель в конфиге

Убедиться что в `src/llm/anthropic_briefer.py` используется `claude-haiku-4-5-20251001`:

```bash
grep -n "model" /opt/scout/src/llm/anthropic_briefer.py
```

Если модель другая — исправить через sed или редактированием файла, затем пересобрать:
```bash
cd /opt/scout && docker compose up --build -d scout-mcp
sleep 15 && curl -s http://localhost:8020/health
```

---

## Шаг 5 — Перезапустить scout-mcp для подхвата нового ключа

```bash
cd /opt/scout && docker compose restart scout-mcp
sleep 15 && curl -s http://localhost:8020/health
```

---

## Шаг 6 — Взять session_id двух последних сессий

```bash
docker exec scout-postgres psql -U scout_user -d scout_db -c "
SELECT id, topic, documents_count, chunks_count, created_at
FROM research_sessions
WHERE status = 'ready'
ORDER BY created_at DESC LIMIT 5;"
```

Записать:
- `SESSION_ANALYTICS` — сессия SC-013 (product analytics, ~1031 chunks)
- `SESSION_AI_TOOLS`  — сессия SC-014 (AI developer tools, ~746 chunks)

---

## Шаг 7 — Запустить brief на product analytics (SC-013)

```bash
python3 << 'SCRIPT'
import json, subprocess

def mcp_init():
    payload = json.dumps({
        "jsonrpc":"2.0","id":0,"method":"initialize",
        "params":{"protocolVersion":"2024-11-05","capabilities":{},
                  "clientInfo":{"name":"sc009","version":"1.0"}}
    })
    r = subprocess.run(
        ["curl","-si","-X","POST","http://localhost:8020/mcp",
         "-H","Content-Type: application/json",
         "-H","Accept: application/json, text/event-stream",
         "-d", payload],
        capture_output=True, text=True, timeout=30
    )
    for line in r.stdout.split("\n"):
        if line.lower().startswith("mcp-session-id:"):
            return line.split(":",1)[1].strip()
    return None

def mcp_call(method, params, session_id):
    payload = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params})
    r = subprocess.run(
        ["curl","-s","-X","POST","http://localhost:8020/mcp",
         "-H","Content-Type: application/json",
         "-H","Accept: application/json, text/event-stream",
         "-H",f"Mcp-Session-Id: {session_id}",
         "-d", payload],
        capture_output=True, text=True, timeout=120
    )
    body = r.stdout.strip()
    if body.startswith("data:"): body = body[5:].strip()
    return json.loads(body)

sid = mcp_init()
print(f"Session: {sid}")

SESSION_ID = "<SESSION_ANALYTICS>"  # ← подставить из шага 6

result = mcp_call("tools/call", {
    "name": "scout_brief",
    "arguments": {
        "session_id": SESSION_ID,
        "query": "сравнение инструментов продуктовой аналитики: ключевые отличия, цены, выбор",
        "top_k": 10
    }
}, sid)

r = result.get("result", {})
print(f"\n{'='*60}")
print(f"model:        {r.get('model')}")
print(f"tokens_used:  {r.get('tokens_used')}")
print(f"sources_used: {r.get('sources_used')}")
print(f"\nBRIEF:\n{r.get('brief', 'ERROR: ' + str(result))}")
SCRIPT
```

---

## Шаг 8 — Запустить brief на AI developer tools (SC-014)

Тот же скрипт, но другой session_id и запрос:

```python
SESSION_ID = "<SESSION_AI_TOOLS>"  # ← подставить из шага 6
query = "сравнение AI-инструментов для разработчиков: Cursor, Copilot, Claude Code — отличия и выбор"
```

---

## Шаг 9 — Оценить оба брифа

По каждому заполнить:

| Критерий | Analytics brief | AI tools brief |
|----------|----------------|----------------|
| Связный текст? | ✅ да | ✅ да |
| Конкретные инструменты названы? | ✅ Amplitude, Heap, Pendo, PostHog, Smartlook, VWO, Eppo | ✅ Cursor, Copilot, Claude Code, Windsurf, Amazon Q |
| Факты из реальных источников? | ✅ pricing, autocapture, warehouse-native | ✅ цены $10–20, бенчмарки GitHub survey |
| Язык ответа | русский | русский |
| tokens_used | 8402 | 9436 |
| model | claude-haiku-4-5-20251001 | claude-haiku-4-5-20251001 |
| Галлюцинации заметны? | нет явных | нет явных |

---

## Критерии готовности

- API ключ сохранён в GitHub Secrets (`gh secret list` показывает `ANTHROPIC_API_KEY`)
- `scout_brief` возвращает текст, не ошибку "No API key configured"
- Оба брифа получены (analytics + AI tools)
- Таблица оценки заполнена
- Модель в брифе — `claude-haiku-4-5-20251001`

---

*Дата создания: 2026-03-16 | Обновлено: 2026-03-16 (запрос ключа у пользователя, GitHub Secrets, Haiku, два брифа)*

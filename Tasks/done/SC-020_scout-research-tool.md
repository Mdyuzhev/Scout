# SC-020 — scout_research: атомарный инструмент полного цикла

## Цель

Добавить инструмент `scout_research` в `mcp_server.py` — единый MCP-вызов
который принимает тему + список URL и возвращает готовый бриф.

Сейчас агент делает три отдельных шага: `scout_index` → запомнить `session_id` →
`scout_brief`. `scout_research` сворачивает это в один вызов. Агент больше не
управляет `session_id` между шагами и не пишет Python-скрипты для каждого исследования.

---

## Контекст: что уже сделано

Код `scout_research` уже написан в `mcp_server.py` (добавлен вручную без деплоя).
Задача агента:
1. Проверить что код соответствует плану ниже
2. Доделать прокидывание параметра `model` в `pipeline.brief()`
3. Задеплоить (git push → CI)
4. Проверить что инструмент появился в `tools/list`
5. Запустить smoke-тест

---

## Шаг 1 — Проверить текущий код в mcp_server.py

Прочитать `mcp_server.py`, убедиться что `scout_research` содержит:

- Параметры: `topic`, `source_urls`, `query`, `top_k=15`, `model="haiku"`, `language="ru"`, `save_to=None`
- Маппинг моделей: `haiku` → `claude-haiku-4-5-20251001`, `sonnet` → `claude-sonnet-4-6`, `opus` → `claude-opus-4-6`
- Шаг 1: `pipeline.index(config)` с `cache_ttl_hours=0`
- Проверка `documents_count > 0` — ранний возврат с ошибкой если ноль документов
- Шаг 2: `pipeline.brief(session.id, query, top_k)`
- Опциональное сохранение в файл (`save_to`)
- Возврат: `brief`, `model`, `tokens_used`, `sources_used`, `session_id`, статистика индексации

---

## Шаг 2 — Прокинуть параметр model в pipeline.brief()

Текущая проблема: параметр `model` в `scout_research` документирован, но
не передаётся в `pipeline.brief()` — используется модель из `.env`.

### 2a. Обновить `src/llm/anthropic_briefer.py`

Найти метод `generate_brief` (или аналог). Добавить параметр `model: str | None = None`:

```python
async def generate_brief(
    self,
    context: str,
    query: str,
    model: str | None = None,   # ← новый параметр
) -> dict:
    # Если model передан — использовать его, иначе брать из self.model или env
    effective_model = model or self.model or os.getenv(
        "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
    )
    # ... остальная логика без изменений, но использовать effective_model
```

### 2b. Обновить `src/pipeline.py`

Найти метод `brief`. Добавить параметр `model: str | None = None` и прокинуть в briefer:

```python
async def brief(
    self,
    session_id: UUID,
    query: str,
    top_k: int = 10,
    model: str | None = None,   # ← новый параметр
) -> dict:
    # ... поиск чанков без изменений ...
    result = await self._briefer.generate_brief(context, query, model=model)
    return result
```

### 2c. Обновить `scout_research` в `mcp_server.py`

Передать `llm_model` в `pipeline.brief()`:

```python
result = await pipeline.brief(session.id, query, top_k, model=llm_model)
```

---

## Шаг 3 — Обновить `scout_brief` для единообразия (опционально)

Пока `pipeline.brief()` уже принимает `model` — можно и в `scout_brief` добавить
параметр `model: str = "haiku"` по аналогии. Но это не блокер — сделать если
изменение тривиальное.

---

## Шаг 4 — Деплой

```bash
git add mcp_server.py src/llm/anthropic_briefer.py src/pipeline.py
git commit -m "SC-020: add scout_research atomic tool, model param in brief"
git push origin main
```

CI пересоберёт контейнер (~3-5 мин).

---

## Шаг 5 — Проверка

### 5a. tools/list

```bash
curl -s http://localhost:8020/tools | python3 -m json.tool
```

Ожидаем `scout_research` в списке рядом с `scout_index`, `scout_search`, `scout_brief`.

### 5b. Smoke-тест

```bash
python3 << 'SCRIPT'
import json, subprocess

def mcp_init():
    r = subprocess.run(
        ["curl", "-si", "-X", "POST", "http://localhost:8020/mcp",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json, text/event-stream",
         "-d", '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{'
               '"protocolVersion":"2024-11-05","capabilities":{},'
               '"clientInfo":{"name":"sc020-test","version":"1.0"}}}'],
        capture_output=True, text=True, timeout=30
    )
    for line in r.stdout.split("\n"):
        if line.lower().startswith("mcp-session-id:"):
            return line.split(":", 1)[1].strip()
    return ""

sid = mcp_init()

# Минимальный тест: 3 URL, простой запрос
payload = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {
        "name": "scout_research",
        "arguments": {
            "topic": "тест scout_research SC-020",
            "source_urls": [
                "https://www.cbr.ru/press/keypr/",
                "https://rosstat.gov.ru/inflation",
                "https://www.rbc.ru/economics/",
            ],
            "query": "ключевая ставка инфляция текущее состояние",
            "top_k": 5,
            "model": "haiku",
        }
    }
})
r = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp",
     "-H", "Content-Type: application/json",
     "-H", "Accept: application/json, text/event-stream",
     "-H", f"Mcp-Session-Id: {sid}",
     "-d", payload],
    capture_output=True, text=True, timeout=120
)
body = ""
for line in r.stdout.split("\n"):
    if line.startswith("data:"):
        body = line[5:].strip()
        break

d = json.loads(body)
res = d.get("result", {})
print(f"documents_count: {res.get('documents_count')}")
print(f"tokens_used:     {res.get('tokens_used')}")
print(f"model:           {res.get('model')}")
print(f"brief[:200]:     {str(res.get('brief',''))[:200]}")
if res.get("error"):
    print(f"ERROR: {res['error']}")
SCRIPT
```

Ожидаем: `documents_count >= 1`, `tokens_used > 0`, `brief` не пустой.

### 5c. Тест параметра model

Повторить smoke-тест с `"model": "opus"` — убедиться что в ответе `model` содержит
строку `opus`, а не `haiku`.

---

## Критерии готовности

- `scout_research` появился в `curl http://localhost:8020/tools`
- Smoke-тест проходит: documents > 0, brief не пустой
- `model="opus"` в запросе → `claude-opus-4-6` в ответе
- CI зелёный

---

## Использование агентом после выполнения

Вместо трёхшагового пайплайна агент вызывает один инструмент:

```
scout_research(
    topic="инфляция ключевая ставка ЦБ России 2024-2025",
    source_urls=[ ...список от Qwen... ],
    query="динамика ставки и инфляции, причины, прогноз",
    model="opus",
    save_to="/opt/scout/results/inflation_brief.md"
)
```

Результат: бриф в `result.brief`, файл на сервере, `session_id` для уточняющих
поисков через `scout_search`.

---

*Дата создания: 2026-03-16*

## Известные особенности FastMCP 2.0

- Конструктор: только `FastMCP("name")` — `description=` не принимает
- Транспорт: `transport="http"` (не `"streamable-http"`)
- `custom_route` с dict не работает — нужен `JSONResponse` из starlette
- `/health` реализован через `@mcp.custom_route`

## Вызов MCP через curl — обязательные заголовки

FastMCP 2.0 требует:
1. `Accept: application/json, text/event-stream` — без него ошибка
2. `Mcp-Session-Id: <id>` — получить через `initialize` перед tool calls

```bash
# Шаг 1: initialize → получить session id
curl -si -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{
    "protocolVersion":"2024-11-05","capabilities":{},
    "clientInfo":{"name":"client","version":"1.0"}}}'
# → Mcp-Session-Id: <id> в заголовках ответа

# Шаг 2: tool call с session id
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <id>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}'
```

## SSE-парсинг ответов MCP (Python)

Ответ приходит в формате SSE с двумя строками:
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

**НЕ** `body.startswith("data:")` — это не работает, т.к. первая строка `event: message`.

Правильный шаблон `mcp_call` для всех скриптов:

```python
def mcp_call(params, sid, timeout=1200):
    payload = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":params})
    r = subprocess.run(
        ["curl","-s","-X","POST","http://localhost:8020/mcp",
         "-H","Content-Type: application/json",
         "-H","Accept: application/json, text/event-stream",
         "-H",f"Mcp-Session-Id: {sid}",
         "-d", payload],
        capture_output=True, text=True, timeout=timeout
    )
    # SSE: первая строка "event: message", вторая "data: {...}"
    body = ""
    for line in r.stdout.split("\n"):
        if line.startswith("data:"):
            body = line[5:].strip()
            break
    return json.loads(body)
```

## Процедура запуска нового исследования: сначала тест на 10 URL

**Обязательное правило перед любым полным прогоном scout_index.**

Прежде чем запускать полный URL-пул (100-400 ссылок), всегда сначала
делать тест на первых 10 URL. Цель — убедиться что MCP-сессия живая,
парсинг SSE работает, коллектор собирает документы, поиск возвращает результаты.
Полный прогон занимает 5-15 минут — тест занимает 30 секунд и экономит время
при любой ошибке в скрипте.

Шаблон теста (вставлять в начало скрипта шага 1):

```python
# ── ТЕСТ НА 10 URL ───────────────────────────────────────────────────────────
TEST_URLS = urls[:10]
print(f"Тест на {len(TEST_URLS)} URL...")
test_res = mcp_call({
    "name": "scout_index",
    "arguments": {
        "topic": topic,
        "source_type": "urls",
        "source_urls": TEST_URLS,
        "cache_ttl_hours": 0,
    }
}, sid, timeout=120)
tr = test_res.get("result", {})
test_docs = tr.get("documents_count", 0)
test_session = tr.get("session_id", "")
print(f"status: {tr.get('status')} | docs: {test_docs} | "
      f"failed: {tr.get('failed_count')} | blocked: {tr.get('blocked_count',0)}")

# Быстрая проверка поиска
if test_docs > 0:
    search_res = mcp_call({
        "name": "scout_search",
        "arguments": {"session_id": test_session,
                      "query": "тест проверка индексации", "top_k": 3}
    }, sid, timeout=30)
    sr = search_res.get("result", {}).get("results", [])
    print(f"Поиск OK: {len(sr)} результатов")
    if sr:
        print(f"  {sr[0]['similarity']:.3f} | {sr[0]['source_title'][:50]}")
    print("\n✅ ТЕСТ ПРОЙДЕН — можно запускать полный пул")
else:
    print("\n❌ ТЕСТ ПРОВАЛЕН — проверить MCP-сессию и парсинг SSE")
    raise SystemExit(1)
# ─────────────────────────────────────────────────────────────────────────────

# Полный прогон — запускать только после успешного теста
print(f"\nЗапускаю полный пул ({len(urls)} URL)...")
res = mcp_call({
    "name": "scout_index",
    "arguments": {
        "topic": topic,
        "source_type": "urls",
        "source_urls": urls,
        "cache_ttl_hours": 0,
    }
}, sid, timeout=1200)
```

Критерии прохождения теста: `status: ready`, `documents_count > 0`,
поиск возвращает хотя бы 1 результат. Если тест падает — исправить скрипт
до запуска полного пула.

## Anthropic SDK через прокси

Если на сервере нет прямого доступа к api.anthropic.com — SDK подхватывает прокси автоматически:

```bash
# В .env или перед запуском контейнера
HTTP_PROXY=http://localhost:8888
HTTPS_PROXY=http://localhost:8888
```

Или в docker-compose.yml:
```yaml
environment:
  - HTTP_PROXY=http://host.docker.internal:8888
```

## Перезапуск контейнера с подхватом нового .env

`docker compose restart` **не перечитывает** `.env` — только перезапускает процесс.
Для подхвата новых переменных окружения нужно пересоздать контейнер:

```bash
# Пересоздать только scout-mcp без остановки postgres
cd /opt/scout && docker compose -p scout up --force-recreate --no-deps -d scout-mcp
```

## Запуск docker compose через homelab MCP

homelab MCP работает внутри контейнера без прямого доступа к хосту.
Если нужно запустить `docker compose` с HOST-путями:

```bash
docker run --rm \
  -v /opt/scout:/workspace \
  -v /var/run/docker.sock:/var/run/docker.sock \
  docker:27-cli \
  compose -f /workspace/docker-compose.yml -p scout up --force-recreate --no-deps -d scout-mcp
```

## Playwright: парадокс Level 2 коллектора

Playwright headless Chromium **ухудшает** результат на технических и корпоративных сайтах.

По итогам SC-017 vs SC-014 (одна тема AI tools, похожий URL-список):

| Прогон | Инструмент | documents |
|--------|-----------|-----------|
| SC-014 | httpx + правильные заголовки | 184 |
| SC-017 | httpx + Playwright fallback | 19 |

Причина: GitHub, GitHub Docs, AWS Docs, arxiv — все они **распознают headless Chromium**
через fingerprinting (Canvas, WebGL, timing) и блокируют его жёстче чем httpx.
При этом httpx с правильными `Sec-Fetch-*` заголовками эти сайты пропускали.

**Правило применения Playwright:**

Playwright помогает только для **JS-SPA с открытым контентом** — то есть сайтов
где страница существует и контент публичный, но без JS возвращается пустой `<div>`.
Примеры: smarthome.rt.ru, b2b.rt.ru, некоторые российские корпоративные порталы.

Playwright **НЕ помогает** и **ухудшает** для:
- Технической документации (GitHub Docs, AWS Docs, Google Cloud Docs)
- Академических репозиториев (arxiv.org)
- Сайтов с Cloudflare Enterprise (определяет headless по WebGL/Canvas fingerprint)
- Любых сайтов где httpx с правильными заголовками уже проходил

**Итог для архитектуры SC-017**: Playwright следует применять только как targeted
fallback для конкретных доменов из whitelist (RT Smart Home, B2B порталы),
а не как общий fallback для всех 403-ответов.

---

## Доноры компонентов

- **RAG-QA** (`E:\RAG_qa`): `searcher.py`, `chunker.py` — основа retrieval-слоя
- **MOEX** (`E:\moex`): паттерн `explainer.py` — LLM только для финального шага
- **Homelab MCP** (`E:\LocOll\mcp-server`): паттерн FastMCP-сервера

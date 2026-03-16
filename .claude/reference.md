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

---

## Доноры компонентов

- **RAG-QA** (`E:\RAG_qa`): `searcher.py`, `chunker.py` — основа retrieval-слоя
- **MOEX** (`E:\moex`): паттерн `explainer.py` — LLM только для финального шага
- **Homelab MCP** (`E:\LocOll\mcp-server`): паттерн FastMCP-сервера

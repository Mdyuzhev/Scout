# _mcp_curl_fix.md — Правильный заголовок для curl → MCP

## Проблема

FastMCP 2.0 требует заголовок `Accept: application/json, text/event-stream`.
Без него сервер возвращает ошибку или пустой ответ.

## Правило

**Всегда** добавлять `-H "Accept: application/json, text/event-stream"` к любому
curl-запросу на `http://localhost:8020/mcp`.

## Bash curl (шаг 3 в SC-013)

```bash
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,...}'
```

## Python subprocess (шаг 1 в SC-013)

```python
result = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp",
     "-H", "Content-Type: application/json",
     "-H", "Accept: application/json, text/event-stream",
     "-d", "@/tmp/payload.json"],
    capture_output=True, text=True, timeout=900
)
```

> Применяется ко всем задачам: SC-009, SC-013 и любым будущим.

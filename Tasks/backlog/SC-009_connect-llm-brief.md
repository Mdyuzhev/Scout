# SC-009 — Подключить ANTHROPIC_API_KEY и проверить scout_brief

## Цель

Добавить ключ Anthropic в `.env` на сервере и проверить что `scout_brief`
генерирует связный текст на основе данных из SC-008.

**Блокер**: SC-008 должна быть выполнена — нужна готовая сессия с данными.

---

## Шаги выполнения

### Шаг 1 — Взять ключ из другого проекта

Через homelab MCP (`run_shell_command`):

```bash
grep ANTHROPIC_API_KEY /opt/moex/.env
```

### Шаг 2 — Вставить в .env Scout

```bash
sed -i 's/^ANTHROPIC_API_KEY=$/ANTHROPIC_API_KEY=<ключ>/' /opt/scout/.env
grep ANTHROPIC_API_KEY /opt/scout/.env
```

### Шаг 3 — Перезапустить scout-mcp

```bash
cd /opt/scout && docker compose restart scout-mcp
sleep 10 && curl -s http://localhost:8020/health
```

### Шаг 4 — Запустить scout_brief на сессии из SC-008

```bash
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"scout_brief","arguments":{
      "session_id":"<SESSION_ID из SC-008>",
      "query":"сравнение инструментов продуктовой аналитики: ключевые отличия и выбор",
      "top_k":10
    }}
  }' | python3 -m json.tool
```

### Шаг 5 — Оценить brief

- Связный ли текст?
- Основан ли на реальных собранных данных или выдуман?
- На каком языке (ожидаем русский)?
- Сколько токенов использовано?

---

## Критерии готовности

- `scout_brief` возвращает текст, не ошибку "No API key configured"
- Brief содержит конкретные факты из собранных источников
- `tokens_used` в ответе не null

---

*Дата создания: 2026-03-16*

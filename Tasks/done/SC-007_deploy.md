# SC-007 — Deploy: первый деплой через CI/CD

## Текущее состояние (уже сделано)

- ✅ `/opt/scout` на сервере — клонирован, `.env` заполнен
- ✅ GitHub Actions runner `scout-homelab` — зарегистрирован и запущен как systemd-сервис
- ✅ `deploy.yml` — настроен, триггер на push в `main`
- ⬜ Код не запушен — всё что написано с SC-002 по SC-006 лежит локально

## Цель

Запушить накопленный код → CI подхватывает → контейнеры поднимаются →
проверить что всё работает.

---

## Флоу деплоя (единственный правильный способ)

```
git add . → git commit → git push origin main
    ↓
GitHub Actions runner scout-homelab на сервере подхватывает push
    ↓
CI: git fetch + reset --hard → docker compose up --build -d
    ↓
CI: health check (curl /health) + smoke test (tools/list)
    ↓
Проверяем результат через homelab MCP
```

**Агент не трогает сервер вручную.** Только git push.

---

## Шаги выполнения

### Шаг 1 — Закоммитить и запушить накопленный код

```bash
git add .
git commit -m "feat: SC-002..SC-006 — data models, ingestion, retrieval, MCP server, postgres"
git push origin main
```

### Шаг 2 — Убедиться что CI прошёл

Проверить через homelab MCP (`run_shell_command`):

```bash
# Статус контейнеров
docker ps --filter name=scout --format "{{.Names}} {{.Status}}"

# Health check
curl -s http://localhost:8020/health

# Логи если что-то не так
docker logs scout-mcp --tail 50
```

### Шаг 3 — Добавить ANTHROPIC_API_KEY в .env

Ключ пуст — `scout_brief` не будет работать без него. Добавить через homelab MCP:

```bash
# Получить ключ из переменных окружения других проектов (например moex)
grep ANTHROPIC_API_KEY /opt/moex/.env

# Вставить в scout .env
sed -i 's/ANTHROPIC_API_KEY=/ANTHROPIC_API_KEY=sk-ant-.../' /opt/scout/.env

# Перезапустить scout-mcp чтобы подхватил новый ключ
cd /opt/scout && docker compose restart scout-mcp
```

### Шаг 4 — Smoke test end-to-end

Через homelab MCP (`run_shell_command`):

```bash
# Список инструментов
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json; tools=json.load(sys.stdin); print([t['name'] for t in tools.get('result',{}).get('tools',[])])"

# PostgreSQL
docker exec scout-postgres psql -U scout_user -d scout_db -c "\dt"
```

---

## Критерии готовности

- `git push` → Actions workflow проходит без ошибок
- `scout-mcp` и `scout-postgres` в статусе `running/healthy`
- `curl http://localhost:8020/health` → `{"status":"ok"}`
- Список инструментов содержит `scout_index`, `scout_search`, `scout_brief`

---

*Дата создания: 2026-03-16 | Обновлено: 2026-03-16 (runner и /opt/scout уже готовы, осталось только запушить)*

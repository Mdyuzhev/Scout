# SC-008 — Первый боевой прогон: индексация и поиск без LLM

## Цель

Проверить детерминированную часть пайплайна на реальных данных:
сбор → чанкинг → индексация → семантический поиск.

LLM (brief) пока не подключена — это отдельная задача SC-009.
Сейчас важно понять качество данных и поиска до добавления LLM-слоя.

---

## Тема для прогона

**"Инструменты продуктовой аналитики 2024-2025"**

Запросы для сбора:
- `"product analytics tools comparison 2024"`
- `"Amplitude Mixpanel PostHog comparison features"`

Выбор обоснован: хорошо известная тема, много качественных источников,
легко оценить релевантность результатов не будучи экспертом.

---

## Шаги выполнения

### Шаг 1 — Запустить индексацию

Через homelab MCP (`run_shell_command`):

```bash
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "scout_index",
      "arguments": {
        "topic": "product analytics tools 2024 2025",
        "depth": "quick",
        "queries": [
          "product analytics tools comparison 2024",
          "Amplitude Mixpanel PostHog comparison features"
        ],
        "language": "en"
      }
    }
  }' | python3 -m json.tool
```

Зафиксировать `session_id` из ответа — нужен для следующих шагов.

Ожидаемый ответ (через 1-3 минуты):
```json
{
  "session_id": "...",
  "status": "ready",
  "documents_count": 10-15,
  "chunks_count": 50-150
}
```

### Шаг 2 — Проверить историю в PostgreSQL

```bash
docker exec scout-postgres psql -U scout_user -d scout_db -c "
SELECT id, topic, status, documents_count, chunks_count, created_at
FROM research_sessions
ORDER BY created_at DESC LIMIT 5;
"
```

### Шаг 3 — Запросы к поиску (3-4 разных угла)

```bash
# Запрос 1: функциональность
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":2,"method":"tools/call",
    "params":{"name":"scout_search","arguments":{
      "session_id":"<SESSION_ID>",
      "query":"event tracking funnel analysis features",
      "top_k":5
    }}
  }' | python3 -m json.tool

# Запрос 2: ценообразование
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":3,"method":"tools/call",
    "params":{"name":"scout_search","arguments":{
      "session_id":"<SESSION_ID>",
      "query":"pricing free tier enterprise plan",
      "top_k":5
    }}
  }' | python3 -m json.tool

# Запрос 3: интеграции
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":4,"method":"tools/call",
    "params":{"name":"scout_search","arguments":{
      "session_id":"<SESSION_ID>",
      "query":"integrations API data export",
      "top_k":5
    }}
  }' | python3 -m json.tool
```

### Шаг 4 — Тест кэша (повторный запрос)

Запустить `scout_index` с той же темой повторно.
В логах должно быть: `"Найдена кэшированная сессия"`.
Ответ должен вернуться мгновенно с той же `session_id`.

```bash
docker logs scout-mcp --tail 20
```

### Шаг 5 — Оценить результаты и зафиксировать наблюдения

Честно ответить на вопросы и записать в раздел "Наблюдения" ниже:

**Сбор данных:**
- Сколько документов собрано?
- Есть ли мусорные источники (реклама, SEO-spam, cookie-баннеры)?
- Какие домены попали в выборку?

**Качество поиска:**
- Similarity scores — в каком диапазоне? (< 0.65 слабо, > 0.75 хорошо)
- Результаты реально релевантны запросу?
- Встречаются ли дубликаты из одного источника?
- Разнообразие источников в топ-5?

**Технические:**
- Были ли timeout при сборе страниц?
- Сколько документов отфильтровано как дубликаты?
- Что в логах `docker logs scout-mcp`?

---

## Наблюдения

```
documents_count: 8
chunks_count: 57
similarity_range: 0.61 — 0.72
```

### Сбор данных
- 10 URL найдено из DDG (depth=quick → 1 query из 2)
- 2 URL отклонены (403 Forbidden: gartner.com, cpoclub.com)
- 0 дубликатов отфильтровано
- **Домены:** userpilot.com, replug.io, contentsquare.com, productanalyticstools.com,
  hyscaler.com + ещё 3

### Качество поиска
- **Query 1** "event tracking funnel analysis features": 4 результата, 0.67–0.71 — хорошо, контент релевантен (Mixpanel, Datadog RUM, Glassbox, Fullstory)
- **Query 2** "pricing free tier enterprise plan": 5 результатов, 0.63–0.72 — хорошо, но только 2 уникальных домена в топ-5 (userpilot, replug)
- **Query 3** "integrations API data export": 1 результат, 0.61 — слабо, тема интеграций слабо покрыта в собранных данных
- Дубликаты из одного источника: да, userpilot.com доминирует (3 из 5 в Q2) — нет diversity penalty

### Технические
- Timeout: 0 (все запросы уложились в 10с)
- Кэш: работает, повторный scout_index возвращает ту же сессию мгновенно
- Время полного пайплайна: ~21с (search 2с + fetch 8с + chunking+indexing 11с)

### Баги найдены и исправлены
1. **DDG URL extraction** — ссылки вида `//duckduckgo.com/l/?uddg=<url>` не парсились (startswith "http" фильтр). Фикс: `_extract_ddg_url()` с парсингом uddg параметра
2. **Кэш пустых сессий** — find_similar возвращал сессии с documents_count=0. Фикс: добавлен `AND documents_count > 0`

### Выводы для Wave 2
- depth=quick берёт только 1 query — второй запрос ("Amplitude Mixpanel PostHog") игнорируется. Для лучшего покрытия нужен depth=normal
- Нет diversity penalty: один домен может занять все топ-5. Нужен round-robin или штраф за повтор источника
- 403 от gartner/cpoclub — нужен fallback (retry с другим UA или skip и логирование)
- Similarity 0.61–0.72 — нормально для multilingual модели, но можно улучшить с domain-specific embeddings

---

## Критерии готовности

- [x] `scout_index` завершается со статусом `ready`
- [x] В PostgreSQL есть запись о сессии
- [x] `scout_search` возвращает результаты с similarity > 0.60
- [x] Повторный `scout_index` возвращает кэшированную сессию (не пересобирает)
- [x] Наблюдения зафиксированы

---

*Дата создания: 2026-03-16*
*Выполнена: 2026-03-16*

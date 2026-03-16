# SC-011 — Два режима сбора данных: DDG search + URL batch input

## Цель

Добавить второй режим входных данных — пакетная загрузка готовых URL.
Оба режима работают через `source_type` в `ResearchConfig`.

После задачи Scout умеет:
- `source_type: "web"` — поиск через DDG (как сейчас)
- `source_type: "urls"` — принять список URL, скачать и проиндексировать без DDG

`source_type: "urls"` уже частично реализован в `WebCollector.collect()`,
но не хватает: параллельного фетча, отчёта об упавших URL,
поддержки параметров в `scout_index` через MCP.

---

## Контекст

Проблема DDG: rate limit после 2-3 итераций подряд.
Правильный флоу без DDG:

```
Claude web_search → список URL (поиск без rate limit)
    ↓
scout_index(source_type="urls", source_urls=[...])
    ↓
Scout: скачать параллельно → почистить → нарезать → проиндексировать
```

---

## Шаги выполнения

### Шаг 1 — Обновить MCP-инструмент scout_index

Файл `mcp_server.py` — добавить параметры:

```python
@mcp.tool()
async def scout_index(
    topic: str,
    depth: str = "normal",
    queries: list[str] | None = None,
    language: str = "ru",
    llm_provider: str = "anthropic",
    source_type: str = "web",              # "web" | "urls"
    source_urls: list[str] | None = None,  # только для source_type="urls"
) -> dict:
    """Index documents for a research topic.

    Two modes:
    - source_type="web" (default): search via DuckDuckGo
    - source_type="urls": fetch provided URLs directly, no search

    For urls mode, provide source_urls (up to 200 URLs).
    topic is required in both modes for session metadata and ChromaDB naming.
    """
```

Передать `source_type` и `source_urls` в `ResearchConfig`.

### Шаг 2 — Параллельный фетч в WebCollector

Файл `src/ingestion/web.py`.

Сейчас URL обрабатываются последовательно: 200 URL × 10с = до 33 минут.
Нужна конкурентная загрузка через `asyncio.Semaphore`:

```python
import asyncio

_MAX_CONCURRENT = 10  # не более 10 одновременных запросов

async def _fetch_all(
    self,
    client: httpx.AsyncClient,
    urls: list[str],
) -> tuple[list[Document], list[str]]:
    """Fetch URLs concurrently. Returns (documents, failed_urls)."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    async def fetch_with_sem(url: str) -> Document | None:
        async with semaphore:
            return await self._fetch_page(client, url)

    results = await asyncio.gather(
        *[fetch_with_sem(url) for url in urls],
        return_exceptions=True,
    )

    docs: list[Document] = []
    failed: list[str] = []
    seen_hashes: set[str] = set()

    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            logger.warning("Exception fetching {}: {}", url, result)
            failed.append(url)
        elif result is None:
            failed.append(url)
        elif result.content_hash in seen_hashes:
            logger.debug("Duplicate skipped: {}", url)
        else:
            seen_hashes.add(result.content_hash)
            docs.append(result)

    return docs, failed
```

Обновить `collect()`: использовать `_fetch_all` вместо последовательного цикла.
Дедупликацию перенести внутрь `_fetch_all` (убрать из `collect()`).

### Шаг 3 — Вернуть failed_urls в ответе scout_index

**Важно**: `failed_urls` — только в ответе MCP-инструмента, не в `ResearchSession`.
Добавлять в Pydantic-модель или PostgreSQL не нужно — это операционная информация
нужная агенту прямо сейчас, не для истории.

Обновить возврат в `pipeline.index()`:
```python
# pipeline.index() возвращает tuple или расширенный dict
return session, failed_urls  # передать наверх в mcp_server.py
```

Ответ `scout_index`:
```python
return {
    "session_id": str(session.id),
    "status": session.status.value,
    "documents_count": session.documents_count,
    "chunks_count": session.chunks_count,
    "failed_urls": failed_urls,
    "failed_count": len(failed_urls),
    "message": (
        f"Indexed {session.documents_count} docs "
        f"({len(failed_urls)} failed) for '{topic}'"
    ),
}
```

### Шаг 4 — Добавить задержку между DDG-запросами

Файл `src/ingestion/web.py`, метод `_search_urls`:

```python
for i, query in enumerate(queries):
    if i > 0:
        await asyncio.sleep(3)  # пауза между DDG-запросами
    found = await self._ddg_search(client, query, config.language)
```

### Шаг 5 — Тест URL-режима

```bash
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"scout_index","arguments":{
      "topic": "product analytics tools 2024",
      "source_type": "urls",
      "source_urls": [
        "https://posthog.com/blog/best-product-analytics-tools",
        "https://mixpanel.com/blog/mixpanel-vs-amplitude/",
        "https://amplitude.com/blog/amplitude-vs-mixpanel",
        "https://www.g2.com/categories/product-analytics",
        "https://www.productboard.com/blog/product-analytics-tools/"
      ]
    }}
  }' | python3 -m json.tool
```

Проверить:
- `documents_count` = успешно загружено
- `failed_count` = упавших (403, timeout)
- `failed_urls` = список конкретных упавших URL
- Время < 30с (параллельный фетч)

### Шаг 6 — Обновить тесты

- `test_ingestion.py`: добавить тест `_fetch_all` с моком (5 URL, 2 упавших)
- `test_pipeline.py`: тест `scout_index` с `source_type="urls"`

---

## Критерии готовности

- `scout_index` принимает `source_type` и `source_urls`
- URL-режим работает без вызова `_ddg_search`
- 20 URL загружаются параллельно (быстрее чем 20 × 10с)
- Ответ содержит `failed_urls` и `failed_count`
- DDG-режим: пауза 3с между запросами
- CI зелёный

---

*Дата создания: 2026-03-16*

---

## Результаты (2026-03-16)

- ✅ `scout_index` принимает `source_type` + `source_urls`
- ✅ `WebCollector._fetch_all` — конкурентный фетч `asyncio.Semaphore(10)`
- ✅ `collect()` возвращает `tuple[list[Document], list[str]]`
- ✅ `pipeline.index()` возвращает `(session, failed_urls)`
- ✅ Ответ содержит `failed_urls`, `failed_count`
- ✅ DDG: задержка 3с между запросами
- ✅ Тесты: `test_fetch_all_partial_failures`, `test_index_with_failed_urls`
- ✅ CI green — коммит `27d085a`

*Закрыто: 2026-03-16*

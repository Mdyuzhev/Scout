# SC-010 — Три итерации прогона: мини / миди / лонг

## Цель

Провести три последовательных прогона на одной теме с разной глубиной.
Собрать данные для сравнения: как меняется качество coverage, similarity scores
и разнообразие источников при увеличении глубины.

---

## Перед запуском: две правки в коде

### Правка 1 — Queries не должны обрезаться по depth

**Проблема**: сейчас `queries[:max_queries]` обрезает пользовательские запросы.
При `depth=quick` (max_queries=1) переданные 2 запроса → используется только первый.
Это нелогично: если агент явно передал queries — нужно использовать все.

`depth` должен контролировать только `max_pages` (сколько страниц скачать),
а не количество поисковых запросов.

**Файл**: `src/ingestion/web.py`

```python
# БЫЛО:
_DEPTH_LIMITS: dict[DepthLevel, tuple[int, int]] = {
    DepthLevel.QUICK:  (1, 15),
    DepthLevel.NORMAL: (3, 40),
    DepthLevel.DEEP:   (5, 100),
}
# ...
max_queries, max_pages = _DEPTH_LIMITS[config.depth]
queries = list(config.queries) if config.queries else []
if not queries:
    queries.append(config.topic)
queries = queries[:max_queries]

# СТАЛО:
_DEPTH_PAGES: dict[DepthLevel, int] = {
    DepthLevel.QUICK:  15,
    DepthLevel.NORMAL: 40,
    DepthLevel.DEEP:   100,
}
_DEPTH_DEFAULT_QUERIES: dict[DepthLevel, int] = {
    DepthLevel.QUICK:  1,   # если queries не переданы — генерируем 1
    DepthLevel.NORMAL: 3,   # если queries не переданы — генерируем 3
    DepthLevel.DEEP:   5,   # если queries не переданы — генерируем 5
}
# ...
max_pages = _DEPTH_PAGES[config.depth]
queries = list(config.queries) if config.queries else []
if not queries:
    # Нет явных queries — добавляем topic как единственный запрос
    # (в будущем можно генерировать через LLM)
    queries.append(config.topic)
# Все переданные queries используются, max_pages ограничивает total страниц
```

### Правка 2 — Diversity penalty в ContextBuilder

**Проблема**: один домен занимает всё топ-5 (userpilot.com в SC-008).
Текущий `_MAX_PER_SOURCE = 3` слишком мягкий.

**Файл**: `src/retrieval/context_builder.py`

Снизить до `_MAX_PER_SOURCE = 2` — не более 2 чанков с одного URL в выдаче.
Это заставит поиск показывать больше уникальных источников.

---

## Три итерации

**Тема одна для всех**: `"product analytics tools 2024 2025"`

**Queries одни для всех**:
```
"product analytics tools comparison 2024"
"Amplitude Mixpanel PostHog comparison features"
"product analytics pricing free tier enterprise"
```

**Поисковые запросы для `scout_search` одни для всех** (3 угла):
```
Q1: "event tracking funnel analysis"
Q2: "pricing plans enterprise"
Q3: "integrations API data warehouse"
```

---

### Итерация 1 — Мини (quick, 15 страниц)

```json
{
  "topic": "product analytics tools 2024 2025",
  "depth": "quick",
  "queries": [
    "product analytics tools comparison 2024",
    "Amplitude Mixpanel PostHog comparison features",
    "product analytics pricing free tier enterprise"
  ],
  "language": "en"
}
```

Ожидания: 8-12 docs, 40-80 chunks, время ~20-30с

---

### Итерация 2 — Миди (normal, 40 страниц)

```json
{
  "topic": "product analytics tools 2024 2025",
  "depth": "normal",
  "queries": [
    "product analytics tools comparison 2024",
    "Amplitude Mixpanel PostHog comparison features",
    "product analytics pricing free tier enterprise"
  ],
  "language": "en",
  "cache_ttl_hours": 0
}
```

`cache_ttl_hours: 0` — принудительно пересобрать, не брать кэш из мини.
Ожидания: 25-35 docs, 150-250 chunks, время ~60-90с

---

### Итерация 3 — Лонг (deep, 100 страниц)

```json
{
  "topic": "product analytics tools 2024 2025",
  "depth": "deep",
  "queries": [
    "product analytics tools comparison 2024",
    "Amplitude Mixpanel PostHog comparison features",
    "product analytics pricing free tier enterprise"
  ],
  "language": "en",
  "cache_ttl_hours": 0
}
```

Ожидания: 60-80 docs, 400-600 chunks, время ~3-5 мин

---

## Что измерять по каждой итерации

Заполнить таблицу:

| Метрика | Мини (quick) | Миди (normal) | Лонг (deep) |
|---------|-------------|--------------|-------------|
| session_id | | | |
| documents_count | | | |
| chunks_count | | | |
| время индексации | | | |
| Q1 similarity range | | | |
| Q2 similarity range | | | |
| Q3 similarity range | | | |
| уникальных доменов в топ-10 | | | |
| доминирующий домен | | | |

---

## Критерии готовности

- Обе правки в коде применены, закоммичены, задеплоены через CI
- Три итерации выполнены, таблица заполнена
- Выводы: при каком depth качество поиска перестаёт значимо расти
  (точка diminishing returns)

---

## После выполнения

Наблюдения станут основой для:
- Рекомендаций по умолчанию (`depth=normal` vs `quick`)
- SC-009 (brief): на каком наборе данных запускать LLM

---

*Дата создания: 2026-03-16*

---

## Результаты (2026-03-16)

### Код-правки
- ✅ Правка 1 применена в коммите `c1bf697`: `_DEPTH_PAGES` в `src/ingestion/web.py`, `max_queries` убран, queries не обрезаются
- ✅ Правка 2 применена в коммите `c1bf697`: `_MAX_PER_SOURCE = 2` в `src/retrieval/context_builder.py`

### Прогоны
❌ Не выполнены — заблокированы.

**Причина**: DuckDuckGo (html и lite эндпоинты) возвращает HTTP 202 без результатов для IP сервера 192.168.1.74 — bot-detection блокировка. При запуске мини-итерации: `0 docs, 0 chunks`.

### Блокер
Нужна замена поискового движка. Варианты:
- `duckduckgo-search` (DDGS Python lib — другой transport)
- SearXNG self-hosted
- Bing Search API

### Таблица метрик
Не заполнена (прогоны не выполнены).

*Закрыто: 2026-03-16*

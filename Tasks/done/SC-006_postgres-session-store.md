# SC-006 — PostgreSQL: схема сессий и логика "сначала проверь историю"

## Цель

Подключить PostgreSQL как data lake истории исследований. Реализовать `SessionStore`
и встроить логику проверки кэша в `ScoutPipeline`: перед сбором данных Scout
проверяет — не исследовали ли мы эту тему недавно? После этой задачи каждое
исследование сохраняется в БД, повторные запросы по той же теме мгновенно
возвращают старую сессию.

---

## Контекст

Главная ценность PostgreSQL в Scout — не просто хранение, а умный поиск по истории.
`tsvector` + `GIN`-индекс дают нам полнотекстовый поиск по темам без внешних
зависимостей. `JSONB` хранит `ResearchConfig` любой версии без миграций.

PostgreSQL запускается в docker-compose уже с SC-001. Теперь нужно создать схему
и подключить `SessionStore` к `ScoutPipeline`.

---

## Шаги выполнения

### 1. Схема БД (migrations/001_initial.sql)

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- для gen_random_uuid()

CREATE TABLE research_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic           TEXT NOT NULL,
    config          JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    documents_count INT  DEFAULT 0,
    chunks_count    INT  DEFAULT 0,
    brief           TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    -- tsvector для полнотекстового поиска по теме
    search_vector   TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('russian', topic)
    ) STORED
);

-- GIN-индекс для быстрого поиска
CREATE INDEX idx_sessions_search  ON research_sessions USING GIN(search_vector);
CREATE INDEX idx_sessions_status  ON research_sessions(status);
CREATE INDEX idx_sessions_created ON research_sessions(created_at DESC);
```

`GENERATED ALWAYS AS` — PostgreSQL 12+ автоматически обновляет `search_vector`
при изменении `topic`. Нам не нужно думать об этом в коде.

### 2. SessionStore (src/storage/session_store.py)

```python
class SessionStore:
    def __init__(self, dsn: str):
        # asyncpg connection pool
        ...

    async def init(self):
        # Создать пул соединений, выполнить миграцию если таблицы нет
        ...

    async def save(self, session: ResearchSession) -> None:
        # INSERT или UPDATE (upsert по id)
        ...

    async def find_similar(
        self,
        topic: str,
        max_age_hours: int = 24,
    ) -> ResearchSession | None:
        """
        Ключевой метод: поиск похожей завершённой сессии.
        Использует полнотекстовый поиск по tsvector.
        Возвращает самую свежую подходящую сессию или None.
        """
        # WHERE status = 'ready'
        #   AND created_at > NOW() - INTERVAL '{max_age_hours} hours'
        #   AND search_vector @@ plainto_tsquery('russian', topic)
        # ORDER BY created_at DESC LIMIT 1
        ...

    async def get(self, session_id: UUID) -> ResearchSession | None:
        ...

    async def list_recent(self, limit: int = 20) -> list[ResearchSession]:
        ...
```

### 3. Обновление ScoutPipeline (src/pipeline.py)

Добавить `SessionStore` в `__init__`. Изменить метод `index`:

```python
async def index(self, config: ResearchConfig) -> ResearchSession:
    # 1. СНАЧАЛА ПРОВЕРИТЬ ИСТОРИЮ
    existing = await self._session_store.find_similar(
        topic=config.topic,
        max_age_hours=config.cache_ttl_hours,
    )
    if existing:
        logger.info(f"Найдена кэшированная сессия {existing.id} для темы '{config.topic}'")
        return existing

    # 2. Только если истории нет — запускаем полный пайплайн
    session = ResearchSession(config=config, status=SessionStatus.PENDING)
    await self._session_store.save(session)

    try:
        # ... сбор, нарезка, индексация ...
        session.status = SessionStatus.READY
    except Exception as e:
        session.status = SessionStatus.FAILED
        session.error = str(e)
        raise
    finally:
        await self._session_store.save(session)

    return session
```

### 4. Инициализация БД на сервере

Через paramiko выполнить миграцию:
```bash
docker exec scout-postgres psql -U scout_user -d scout_db -f /migrations/001_initial.sql
```

Или при старте контейнера через `initdb.d` volume mount.

### 5. Добавить `scout_list_sessions` в MCP-сервер

Вспомогательный инструмент — показывает историю исследований:
```
Параметры: limit: int (default: 10)
Возвращает: list[{id, topic, status, chunks_count, created_at}]
```

---

## Критерии готовности

- `docker exec scout-postgres psql -U scout_user -d scout_db -c "\dt"` показывает
  таблицу `research_sessions`
- `SessionStore.save()` и `SessionStore.get()` работают корректно
- `SessionStore.find_similar("FastAPI")` находит существующую сессию с похожей темой
- Повторный вызов `scout_index` с той же темой возвращает кэшированную сессию
  (в логах видно "Найдена кэшированная сессия")
- `scout_list_sessions` возвращает историю

---

*Дата создания: 2026-03-16*

---

## ✅ Статус: ВЫПОЛНЕНА

**Дата завершения:** 2026-03-16

**Что сделано:**
- Создана миграция `migrations/001_initial.sql` — таблица `research_sessions` с tsvector + GIN
- Реализован `SessionStore` (asyncpg pool, upsert, find_similar по tsvector, list_recent)
- Добавлен `postgres_dsn` property в `Settings`
- `ScoutPipeline` переведён на PostgreSQL — in-memory dict заменён на `SessionStore`
- Логика кэша: `find_similar()` проверяет историю перед запуском пайплайна
- `search()` и `get_session()` стали async (через `SessionStore.get()`)
- Добавлен MCP-инструмент `scout_list_sessions`
- docker-compose: migrations монтируются в `initdb.d` для авто-инициализации
- 34/34 тестов pass (добавлены test_index_returns_cached, test_list_sessions)

**Отклонения от плана:**
- Шаг 4 (миграция на сервере) отложен до SC-007 deploy — контейнеры ещё не запущены

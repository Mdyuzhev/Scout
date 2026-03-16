# SC-016 — Уровень 1: правильные заголовки, задержки, стоп-лист

## Цель

Улучшить `WebCollector` так чтобы он выглядел как реальный браузер для большинства
сайтов. Это первый уровень трёхуровневого коллектора — самый простой и даёт 30-40%
меньше блокировок без внешних зависимостей.

Уровни 2 (Playwright fallback) и 3 (Proxy) — отдельные задачи, потом.

---

## Контекст

Текущие проблемы `src/ingestion/web.py`:

1. **Заголовки** — есть только `User-Agent` и `Accept-Language`, отсутствуют
   `Accept`, `Accept-Encoding`, `Sec-Fetch-*` и другие заголовки которые
   реальный Chrome шлёт обязательно.

2. **Задержки** — фиксированный `asyncio.sleep(3)` между DDG-запросами, но
   нет пауз между фетчем страниц. При параллельном `_MAX_CONCURRENT=10`
   десять запросов летят одновременно — это паттерн бота.

3. **Нет стоп-листа** — G2, Capterra, GitHub, Medium и другие сайты с
   bot-protection блокируют всегда. Мы тратим время на попытки и получаем
   `failed_count` вместо того чтобы сразу пропустить.

4. **Один User-Agent** — одна и та же строка на весь прогон, легко детектируется.

---

## Шаги выполнения

### Шаг 1 — Полный набор заголовков

Файл `src/ingestion/web.py`. Заменить `_HEADERS` на полный набор:

```python
import random

# Пул реальных User-Agent для ротации
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

def _random_headers() -> dict:
    """Возвращает заголовки случайного браузера."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }
```

Использовать `_random_headers()` при создании httpx клиента.
Для DDG-запросов — отдельный вызов `_random_headers()`.

### Шаг 2 — Случайные задержки между фетчем страниц

В методе `_fetch_all` — добавить случайную паузу внутри семафора:

```python
async def fetch_with_sem(url: str) -> Document | None:
    async with semaphore:
        # Случайная задержка 0.5–2.5 сек — имитация чтения страницы
        await asyncio.sleep(random.uniform(0.5, 2.5))
        return await self._fetch_page(client, url)
```

Пауза внутри семафора — значит при `_MAX_CONCURRENT=10` паузы идут параллельно,
общее время не увеличивается значительно, но паттерн запросов становится
менее регулярным.

### Шаг 3 — Стоп-лист доменов

Добавить в `src/ingestion/web.py` список доменов которые всегда блокируют
и попытка заведомо бессмысленна:

```python
# Домены с агрессивной bot-protection — пропускать без попытки
_BLOCKED_DOMAINS: frozenset[str] = frozenset([
    "g2.com",
    "capterra.com",
    "softwareadvice.com",
    "getapp.com",
    "trustradius.com",
    "gartner.com",
    "github.com",       # JS-heavy, нет полезного текста без рендера
    "medium.com",       # paywall + bot-protection
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "stackoverflow.com", # требует JS
    "reddit.com",
    "quora.com",
    "ycombinator.com",
    "slashdot.org",
    "peerspot.com",
    "stackshare.io",
])

def _is_blocked_domain(url: str) -> bool:
    """Проверить URL против стоп-листа."""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or ""
        # Проверяем и сам домен и поддомены
        return any(
            host == domain or host.endswith(f".{domain}")
            for domain in _BLOCKED_DOMAINS
        )
    except Exception:
        return False
```

В методе `collect()` — фильтровать URL до фетча:

```python
# Фильтрация стоп-листа
blocked = [u for u in urls if _is_blocked_domain(u)]
urls = [u for u in urls if not _is_blocked_domain(u)]
if blocked:
    logger.info("Пропущено {} URL из стоп-листа: {}", len(blocked), blocked[:5])
```

Добавить `blocked_count` в ответ `scout_index`:

```python
return {
    ...
    "failed_count": len(failed_urls),
    "blocked_count": len(blocked),  # ← новое поле
    "message": f"Indexed {session.documents_count} docs "
               f"({len(failed_urls)} failed, {len(blocked)} blocked) for '{topic}'"
}
```

### Шаг 4 — Retry при временных ошибках

Добавить одну повторную попытку при 429 (rate limit) и 503 (временная недоступность):

```python
async def _fetch_page(
    self, client: httpx.AsyncClient, url: str
) -> Document | None:
    for attempt in range(2):  # 2 попытки
        try:
            resp = await client.get(url, headers=_random_headers())
            if resp.status_code == 429:
                if attempt == 0:
                    wait = float(resp.headers.get("Retry-After", "5"))
                    logger.debug("429 на {}, жду {:.0f}с", url, wait)
                    await asyncio.sleep(min(wait, 10))
                    continue
                logger.warning("429 повторно на {}, пропускаем", url)
                return None
            if resp.status_code == 503 and attempt == 0:
                await asyncio.sleep(random.uniform(2, 5))
                continue
            resp.raise_for_status()
            # ... остальная логика без изменений
        except httpx.HTTPError as exc:
            if attempt == 0:
                logger.debug("Retry {} после ошибки: {}", url, exc)
                await asyncio.sleep(random.uniform(1, 3))
                continue
            logger.warning("Failed to fetch {}: {}", url, exc)
            return None
    return None
```

### Шаг 5 — Обновить тесты

В `tests/test_ingestion.py`:
- Тест что `_is_blocked_domain` корректно работает для g2.com, capterra.com,
  поддоменов (www.g2.com) и незаблокированных доменов.
- Тест что `_random_headers()` возвращает все обязательные ключи.
- Тест что заблокированные URL не попадают в фетч.

---

## Критерии готовности

- `_random_headers()` — в каждом запросе разный User-Agent
- Задержки `random.uniform(0.5, 2.5)` между фетчами страниц
- Стоп-лист работает: URL из `_BLOCKED_DOMAINS` пропускаются без попытки
- Ответ `scout_index` содержит `blocked_count`
- Retry на 429/503 — одна повторная попытка с паузой
- Тесты проходят, CI зелёный

## После выполнения

Запустить SC-015 (Ростелеком) повторно с `cache_ttl_hours: 0`
и сравнить `failed_count` до и после. Ожидаем: меньше failed,
больше documents.

---

*Дата создания: 2026-03-16*

---

## ✅ Статус: ВЫПОЛНЕНА

**Дата завершения:** 2026-03-16

**Что сделано:**
- `_USER_AGENTS` пул из 7 реальных UA строк + `_random_headers()` вызывается на каждый запрос
- Случайная задержка `0.5–2.5с` внутри семафора в `_fetch_all`
- `_BLOCKED_DOMAINS` (20 доменов) + `_is_blocked_domain()` с поддержкой субдоменов
- Фильтрация стоп-листа в `collect()` до фетча
- Retry на 429 (Retry-After header, max 10с) и 503 (2–5с случайная пауза)
- `collect()` возвращает 3-tuple `(docs, failed, blocked_count)`; pipeline и mcp_server обновлены
- `blocked_count` в ответе `scout_index`; 3 новых теста; 24/24 тестов проходят
- Коммит `24c5fc7`, CI задеплоен

**Отклонения от плана:**
- Выполнено в соответствии с планом

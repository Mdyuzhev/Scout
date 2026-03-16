# SC-017 — Уровень 2 коллектора: Playwright fallback для JS-сайтов

## Цель

Добавить второй уровень в WebCollector: если httpx получил 403/Cloudflare/пустой
контент — повторная попытка через headless Chromium (Playwright).

По итогам SC-016: success rate вырос только с 48% → 51% потому что основные
провалы это JS-рендеринг (smarthome.rt.ru, b2b.rt.ru, camera.rt.ru) и Cloudflare.
Заголовками это не лечится — нужен настоящий браузер.

**Не трогать**: уровень 1 (SC-016) остаётся как есть. Playwright включается только
как fallback, не заменяет httpx.

---

## Контекст: почему именно Playwright

Cloudflare JS Challenge и аналоги работают так: сервер отдаёт страницу с JS-кодом
который вычисляет fingerprint браузера (Canvas, WebGL, timing) и устанавливает
cookie. Обычный httpx не выполняет JS — получает либо 403 либо пустую страницу.
Playwright запускает реальный Chromium, выполняет JS, проходит challenge и получает
настоящий контент.

В текущем `web.py` это будет третий слой в `_fetch_page`:
```
1. httpx (быстро, 10x)
2. httpx retry (429/503)
3. playwright (медленно, только при 403 или подозрительно коротком контенте)
```

---

## Шаги выполнения

### Шаг 1 — Добавить зависимость

В `requirements.txt`:
```
playwright>=1.44
```

В `Dockerfile` — установить браузеры при сборке образа (важно делать в слое
после pip install, до COPY . .):

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps
```

Браузер весит ~150MB — добавится к размеру образа. Это приемлемо.

### Шаг 2 — PlaywrightFetcher как отдельный класс

Создать `src/ingestion/playwright_fetcher.py` — изолированный модуль, чтобы
Playwright импортировался только там и не ломал сборку если пакет отсутствует.

```python
"""Playwright-based fetcher for JS-rendered pages."""
from __future__ import annotations
import asyncio
from loguru import logger


class PlaywrightFetcher:
    """Fetches pages that require JS execution."""

    # Playwright браузер — создаём один раз, используем весь прогон
    _browser = None
    _playwright = None

    @classmethod
    async def ensure_started(cls) -> None:
        """Ленивая инициализация браузера."""
        if cls._browser is None:
            from playwright.async_api import async_playwright
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",     # важно для Docker
                    "--disable-blink-features=AutomationControlled",  # скрыть что headless
                    "--disable-extensions",
                ]
            )
            logger.info("Playwright Chromium запущен")

    @classmethod
    async def close(cls) -> None:
        if cls._browser:
            await cls._browser.close()
            await cls._playwright.stop()
            cls._browser = None
            cls._playwright = None

    @classmethod
    async def fetch(cls, url: str, timeout_ms: int = 15_000) -> str | None:
        """
        Загрузить страницу через реальный браузер.
        Возвращает HTML или None при ошибке.
        """
        await cls.ensure_started()
        try:
            context = await cls._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36",
                locale="ru-RU",
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )
            page = await context.new_page()

            # Блокировать тяжёлые ресурсы — ускоряет загрузку
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,ico}",
                lambda route: route.abort()
            )

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Подождать пока исчезнет Cloudflare spinner если есть
            await asyncio.sleep(2)

            html = await page.content()
            await context.close()
            return html

        except Exception as exc:
            logger.warning("Playwright failed for {}: {}", url, exc)
            return None
```

Singleton браузер (`_browser` как classvar) — создаётся один раз при первом вызове,
живёт весь прогон. Это критично: запуск Chromium занимает ~2 секунды, создавать
новый браузер на каждый URL неприемлемо.

### Шаг 3 — Интеграция в WebCollector

В `src/ingestion/web.py` добавить константу и логику fallback в `_fetch_page`.

Признаки что нужен Playwright fallback (добавить в начало `_fetch_page`):
```python
# Признаки Cloudflare challenge в ответе httpx
_CF_INDICATORS = [
    "cf-browser-verification",
    "challenge-platform",
    "cf_clearance",
    "Just a moment",
    "Enable JavaScript",
    "Checking your browser",
]

def _needs_playwright(resp: httpx.Response, text: str) -> bool:
    """Определить нужен ли Playwright по ответу httpx."""
    # 403 Forbidden — основной признак
    if resp.status_code == 403:
        return True
    # Очень короткая страница при 200 — скорее всего JS-redirect
    if resp.status_code == 200 and len(text) < 500:
        return True
    # Cloudflare JS challenge в теле
    if any(indicator in text for indicator in _CF_INDICATORS):
        return True
    return False
```

В `_fetch_page` после получения ответа от httpx:

```python
# После resp.raise_for_status() и получения soup:
raw_text = resp.text

# Проверить нужен ли Playwright
if _needs_playwright(resp, raw_text):
    logger.debug("Playwright fallback для {}", url)
    html = await PlaywrightFetcher.fetch(url)
    if html is None:
        return None
    raw_text = html  # дальше парсим playwright-контент
    soup = BeautifulSoup(raw_text, "html.parser")
else:
    soup = BeautifulSoup(raw_text, "html.parser")

# ... остальная логика извлечения текста без изменений
```

### Шаг 4 — Graceful shutdown в pipeline

В `src/pipeline.py` — закрыть браузер после завершения индексации:

```python
from src.ingestion.playwright_fetcher import PlaywrightFetcher

# В конце метода index(), в блоке finally:
finally:
    await PlaywrightFetcher.close()
    await self._session_store.save(session)
```

### Шаг 5 — Флаг включения/выключения

Playwright добавляет ~2-5 секунды на каждый fallback-вызов. Для прогонов где
все URL хорошие он только замедляет. Добавить ENV-переменную:

В `.env.example`:
```
PLAYWRIGHT_ENABLED=true   # выключить для быстрых тестов
```

В `_fetch_page`:
```python
import os
_PLAYWRIGHT_ENABLED = os.getenv("PLAYWRIGHT_ENABLED", "true").lower() == "true"
```

### Шаг 6 — Тест

В `tests/test_ingestion.py` — мокируем Playwright, проверяем что:
- `_needs_playwright` срабатывает на 403, короткий контент, CF-признаки
- При PLAYWRIGHT_ENABLED=false fallback не вызывается
- При успешном Playwright-фетче документ создаётся корректно

---

## Ожидаемый результат

Повторный прогон SC-015 (Ростелеком) с SC-017:
- `smarthome.rt.ru`, `b2b.rt.ru`, `camera.rt.ru` — должны загрузиться через Playwright
- Ожидаем `documents_count` 75-90 вместо 57 (прирост +30-50%)
- `failed_count` снизится с 54 до ~30-35
- Время индексации вырастет: ~77с → ~120-150с (нормально, содержательнее)

---

## Критерии готовности

- `playwright install chromium` в Dockerfile, образ собирается
- `PlaywrightFetcher.fetch()` возвращает HTML для smarthome.rt.ru
- `_needs_playwright()` корректно детектирует CF и 403
- `PLAYWRIGHT_ENABLED=false` отключает fallback
- CI зелёный
- Повторный прогон SC-015: `documents_count` > 75

---

*Дата создания: 2026-03-16*

---

## ✅ Статус: ВЫПОЛНЕНА

**Дата завершения:** 2026-03-16

**Что сделано:**
- Создан `src/ingestion/playwright_fetcher.py` — singleton Chromium браузер, lazy init, graceful close
- В `web.py` добавлены: `_CF_INDICATORS`, `_needs_playwright()`, `_PLAYWRIGHT_ENABLED` (env flag), fallback-логика в `_fetch_page`
- 403 обрабатывается без raise_for_status — сразу идёт в Playwright fallback
- `pipeline.py`: `PlaywrightFetcher.close()` в блоке finally после индексации
- `Dockerfile`: `playwright install chromium --with-deps` добавлен в слой pip install
- `requirements.txt`: `playwright>=1.44`
- `.env.example`: `PLAYWRIGHT_ENABLED=true`
- 5 новых тестов + патчи `_PLAYWRIGHT_ENABLED=False` в существующих httpx-тестах, 19/19 pass
- `deploy.yml`: sleep увеличен 30→60s (образ с playwright требует больше времени старта)

**Отклонения от плана:**
- Health check CI упал из-за timing (30s sleep): образ собирался 21 мин первый раз, контейнер не успевал стартовать. Исправлено: sleep 60s.

**Обнаруженные проблемы:**
- CI health check timeout требует корректировки при тяжёлых образах — зафиксировано и исправлено в deploy.yml

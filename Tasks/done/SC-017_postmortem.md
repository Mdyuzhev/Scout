---

## ⚠️ POST-MORTEM: Парадокс Playwright (обнаружен в SC-017 test run)

**Дата обнаружения:** 2026-03-16

**Проблема:** При повторном прогоне SC-017 (AI tools, похожий URL-список что в SC-014)
с включённым Playwright результат оказался хуже чем без него:

| Прогон | Инструмент | documents |
|--------|-----------|-----------|
| SC-014 | httpx + заголовки (без Playwright) | 184 |
| SC-017 test | httpx + Playwright fallback | 19 |

**Причина:** GitHub, GitHub Docs, AWS Docs, arxiv и аналогичные сайты **распознают
headless Chromium** через Canvas/WebGL fingerprinting и блокируют его агрессивнее,
чем httpx с правильными `Sec-Fetch-*` заголовками. В SC-014 httpx проходил — в SC-017
Playwright блокировался.

**Вывод о правиле применения Playwright:**

Playwright уместен только как **targeted fallback для конкретного whitelist доменов** —
тех что отдают JS-SPA с пустым `<div>` без JS, но контент у них публичный
(smarthome.rt.ru, b2b.rt.ru, российские корпоративные порталы на React).

Playwright НЕ применять к: техдокументации (GitHub Docs, AWS, Google Cloud),
академическим репозиториям (arxiv), Cloudflare Enterprise сайтам.

**Рекомендуемая правка в SC-018 или отдельной задаче:**

Изменить `_needs_playwright()` — вместо "все 403" использовать явный
`_PLAYWRIGHT_DOMAINS` whitelist:

```python
_PLAYWRIGHT_DOMAINS: frozenset[str] = frozenset([
    "smarthome.rt.ru",
    "b2b.rt.ru",
    "camera.rt.ru",
    # добавлять явно по мере обнаружения JS-SPA сайтов
])

def _needs_playwright(url: str, resp: httpx.Response, text: str) -> bool:
    host = urlparse(url).hostname or ""
    if any(host == d or host.endswith(f".{d}") for d in _PLAYWRIGHT_DOMAINS):
        return True  # явно в whitelist
    # НЕ использовать Playwright по коду ответа — 403 от GitHub/AWS
    # блокирует Playwright ещё сильнее
    return False
```

Подробнее: `.claude/reference.md` → раздел "Playwright: парадокс Level 2 коллектора"

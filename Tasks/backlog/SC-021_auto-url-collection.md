# SC-021 — Auto URL collection: Haiku web_search внутри scout_research

## Цель

Добавить режим автоматического сбора URL в `scout_research` — когда `source_urls`
не передан, инструмент сам вызывает Haiku с web_search для поиска релевантных
страниц по теме. Это устраняет последний ручной шаг в пайплайне: тема → бриф
без промежуточного составления списков.

**Зависимость**: SC-020 должна быть выполнена (scout_research базовый вариант).

---

## Мотивация

Текущий флоу требует ручного шага — подготовки URL-списка (через Qwen или вручную).
Haiku с инструментом `web_search_20250305` делает то же самое автоматически:
ищет реальные страницы по теме и возвращает верифицированные URL из результатов поиска.
Никаких угаданных адресов по шаблону.

Конечный флоу для агента:
```
scout_research(topic="инфляция ЦБ России", query="...", auto_collect=True)
→ Haiku ищет URL (web_search, ~10 запросов)
→ Scout индексирует найденные страницы
→ Opus генерирует бриф
→ Готовый бриф в ответе
```

---

## Шаг 1 — Создать `src/ingestion/url_collector.py`

Изолированный модуль для сбора URL через Anthropic API:

```python
"""URL collector via Haiku + web_search tool."""
from __future__ import annotations
import os, re
from loguru import logger


# Промпт для Haiku — просит сделать N поисковых запросов по теме
_SYSTEM = (
    "Ты помощник для продуктового исследования. "
    "Твоя задача — найти максимум реальных URL по заданной теме. "
    "Используй инструмент web_search 10-15 раз с разными запросами "
    "чтобы покрыть разные аспекты темы. "
    "Запросы должны охватывать: статистику, аналитику, официальные источники, "
    "новости, прогнозы, экспертные мнения. "
    "Возвращай только URL, по одному на строку, без пояснений."
)


def _build_search_prompt(topic: str, language: str, n_urls: int) -> str:
    lang_hint = "на русском языке" if language == "ru" else "in English"
    return (
        f"Найди {n_urls} реальных URL по теме: «{topic}» ({lang_hint}). "
        f"Сделай 10-15 поисковых запросов охватывающих разные аспекты: "
        f"статистика и данные, аналитические обзоры, официальные источники, "
        f"новости 2024-2025, прогнозы экспертов, региональная специфика. "
        f"Перечисли все найденные URL — по одному на строку."
    )


def _extract_urls(text: str) -> list[str]:
    """Извлечь URL из текстового ответа модели."""
    pattern = r'https?://[^\s\)\]\,\"\'<>]+'
    found = re.findall(pattern, text)
    # Фильтр: убрать поисковые страницы и соцсети
    bad = ("google.com/search", "yandex.ru/search", "bing.com/search",
           "vk.com", "t.me", "instagram.com", "facebook.com", "twitter.com")
    return [u for u in found if not any(b in u for b in bad)]


async def collect_urls(
    topic: str,
    language: str = "ru",
    n_urls: int = 150,
) -> list[str]:
    """
    Собрать URL по теме через Haiku + web_search.
    Возвращает дедuplicated список реальных URL.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic SDK не установлен")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY не задан в .env")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    logger.info("Collecting URLs for topic '{}' via Haiku web_search...", topic)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": _build_search_prompt(topic, language, n_urls)
        }],
    )

    # Собираем текст из всех content блоков (text + tool_result)
    all_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            all_text += block.text + "\n"
        # tool_result блоки содержат сниппеты с URL
        if hasattr(block, "content"):
            for inner in (block.content if isinstance(block.content, list) else []):
                if hasattr(inner, "text"):
                    all_text += inner.text + "\n"

    urls = _extract_urls(all_text)
    urls = list(dict.fromkeys(urls))  # дедупликация с сохранением порядка

    logger.info("Collected {} unique URLs for '{}'", len(urls), topic)
    return urls
```

### Шаг 2 — Обновить `scout_research` в `mcp_server.py`

Добавить параметр `auto_collect: bool = False` и логику вызова:

```python
@mcp.tool()
async def scout_research(
    topic: str,
    query: str,
    source_urls: list[str] | None = None,
    auto_collect: bool = False,          # ← новый параметр
    auto_collect_count: int = 150,       # сколько URL собрать
    top_k: int = 15,
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
) -> dict:
    """Full research pipeline in one call.

    Three modes:
    - source_urls provided: index given URLs directly
    - auto_collect=True: Haiku searches the web to find URLs, then indexes them
    - both: auto_collect adds to provided source_urls

    ...
    """
    # Автосбор URL если запрошен
    collected_urls: list[str] = []
    if auto_collect:
        from src.ingestion.url_collector import collect_urls
        collected_urls = await collect_urls(
            topic=topic,
            language=language,
            n_urls=auto_collect_count,
        )

    # Объединить с явно переданными URL
    all_urls = list(dict.fromkeys((source_urls or []) + collected_urls))

    if not all_urls:
        return {"error": "No URLs provided and auto_collect=False"}

    # ... остальная логика scout_research без изменений
    # (передаём all_urls вместо source_urls)
```

---

## Шаг 3 — Добавить `auto_collect_urls_count` в ответ

Чтобы агент видел сколько URL было собрано автоматически:

```python
return {
    ...
    "auto_collected_urls": len(collected_urls),   # ← новое поле
    "total_urls_submitted": len(all_urls),
    ...
}
```

---

## Шаг 4 — Тест

### 4a. Юнит-тест collect_urls

```python
# tests/test_url_collector.py
import pytest

@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key")
async def test_collect_urls_basic():
    from src.ingestion.url_collector import collect_urls
    urls = await collect_urls("инфляция ЦБ России 2024", language="ru", n_urls=20)
    assert len(urls) > 5
    assert all(u.startswith("http") for u in urls)
    # Не должно быть поисковых страниц
    assert not any("google.com/search" in u for u in urls)
```

### 4b. Интеграционный тест через MCP

```bash
python3 << 'SCRIPT'
import json, subprocess

def mcp_init():
    r = subprocess.run(
        ["curl", "-si", "-X", "POST", "http://localhost:8020/mcp",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json, text/event-stream",
         "-d", '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sc021-test","version":"1.0"}}}'],
        capture_output=True, text=True, timeout=30
    )
    for line in r.stdout.split("\n"):
        if line.lower().startswith("mcp-session-id:"):
            return line.split(":", 1)[1].strip()
    return ""

sid = mcp_init()

# Тест auto_collect — полностью автоматический пайплайн
payload = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {
        "name": "scout_research",
        "arguments": {
            "topic": "ключевая ставка ЦБ России снижение 2025",
            "query": "когда ЦБ снизит ставку и до какого уровня",
            "auto_collect": True,
            "auto_collect_count": 30,   # небольшой для теста
            "model": "haiku",
            "top_k": 10,
        }
    }
})
r = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp",
     "-H", "Content-Type: application/json",
     "-H", "Accept: application/json, text/event-stream",
     "-H", f"Mcp-Session-Id: {sid}",
     "-d", payload],
    capture_output=True, text=True, timeout=300  # дольше из-за web_search
)
body = ""
for line in r.stdout.split("\n"):
    if line.startswith("data:"):
        body = line[5:].strip()
        break

d = json.loads(body)
res = d.get("result", {})
print(f"auto_collected_urls: {res.get('auto_collected_urls')}")
print(f"total_urls_submitted: {res.get('total_urls_submitted')}")
print(f"documents_count:      {res.get('documents_count')}")
print(f"tokens_used:          {res.get('tokens_used')}")
print(f"brief[:300]:          {str(res.get('brief',''))[:300]}")
SCRIPT
```

Ожидаем: `auto_collected_urls > 10`, `documents_count > 5`, `brief` не пустой.

---

## Сравнение: Qwen vs Haiku для сбора URL

| Критерий | Qwen (текущий) | Haiku auto_collect |
|---|---|---|
| Ручной шаг | Да — составить задачу | Нет — полностью авто |
| Верификация URL | Да — через реальный поиск | Да — web_search |
| Кол-во URL за раз | 200-300 | ~100-150 |
| Разнообразие тем | Высокое (27 запросов) | Среднее (~10-15 запросов) |
| Стоимость | Бесплатно | ~$0.01-0.05 за сбор |
| Скорость | 5-10 мин | 1-2 мин |

Рекомендация: `auto_collect=True` для быстрых исследований и автоматизации.
Qwen-флоу оставить для тем где нужны 200+ URL с детальным покрытием.

---

## Критерии готовности

- `src/ingestion/url_collector.py` создан и импортируется без ошибок
- `scout_research(auto_collect=True)` возвращает `auto_collected_urls > 0`
- Тест: бриф получен без передачи source_urls вручную
- CI зелёный

---

*Дата создания: 2026-03-16 | Зависимость: SC-020*

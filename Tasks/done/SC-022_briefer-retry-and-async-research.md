# SC-022 — Надёжность брифа: retry на 429, явные ошибки, auto_collect в async

## Контекст

Во время исследования "Рынок труда России" вскрылись три системных дефекта.
Пайплайн дважды завершался с `status=done, brief=null` — агент не мог отличить
успех от провала и был вынужден перезапускать исследование вручную.

Лог ошибки:
```
ERROR | AnthropicBriefer failed: Error code: 429 — rate_limit_error:
"This request would exceed your organization's rate limit of 50,000 input tokens per minute"
```

Корневые причины — три независимых дефекта в разных слоях.

---

## Дефект 1 — AnthropicBriefer: нет retry на 429, ошибка не всплывает

**Файл:** `src/llm/anthropic_briefer.py`

Текущий код ловит `Exception` без разбора типа и возвращает `{"brief": None}`.
Вызывающий код не знает что произошла ошибка, а не просто нет данных.

**Что сделать:** добавить retry с backoff на `anthropic.RateLimitError`
и явное поле `error` в возврате.

```python
# В generate_brief — заменить try/except блок:

import asyncio
import anthropic

_RETRY_DELAYS = [15, 45]  # секунд ожидания перед 2-й и 3-й попыткой

last_error: str | None = None

for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
    if delay:
        logger.warning(
            "AnthropicBriefer: rate limit, retry {}/{} after {}s",
            attempt, len(_RETRY_DELAYS) + 1, delay,
        )
        await asyncio.sleep(delay)
    try:
        response = await self._client.messages.create(
            model=effective_model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        logger.info(
            "Brief generated: {} chars, {} tokens ({}, attempt {})",
            len(text), tokens, effective_model, attempt,
        )
        return {"brief": text, "model": effective_model,
                "tokens_used": tokens, "error": None}

    except anthropic.RateLimitError as exc:
        last_error = f"rate_limit: {exc}"
        logger.warning("AnthropicBriefer: 429 attempt {}: {}", attempt, exc)
        # продолжаем retry

    except Exception as exc:
        last_error = str(exc)
        logger.error("AnthropicBriefer failed (no retry): {}", exc)
        break  # не ретраить на другие ошибки

logger.error("AnthropicBriefer: exhausted retries. last_error={}", last_error)
return {"brief": None, "model": effective_model,
        "tokens_used": None, "error": last_error}
```

---

## Дефект 2 — pipeline.brief: проглатывает ошибку briefer

**Файл:** `src/pipeline.py`, метод `brief()`

После вызова `generate_brief` нет проверки что `brief` не None.
Нужно добавить проверку и явно пробрасывать ошибку в ответ:

```python
result = await self._briefer.generate_brief(context, package.topic, model=model)

# Добавить после вызова:
if result.get("brief") is None:
    logger.error(
        "pipeline.brief: LLM returned null brief. error={}",
        result.get("error"),
    )
    return {
        "brief": None,
        "sources_used": len(package.results),
        "model": result.get("model"),
        "tokens_used": None,
        "error": result.get("error") or "LLM returned null brief",
    }

result["sources_used"] = len(package.results)
return result
```

---

## Дефект 3 — scout_research_async: не поддерживает auto_collect

**Файл:** `mcp_server.py`, функция `scout_research_async`

Инструмент требует явный `source_urls: list[str]` и не умеет собирать URL
самостоятельно через Haiku web_search. Команда `/research` вынуждена использовать
`scout_research` (синхронный) + nohup-хак вместо нативного async инструмента.

**Что сделать:** добавить параметры `auto_collect` и `auto_collect_count`,
и вызов `collect_urls` в начале `_run_research_job` если `auto_collect=True`.

### Изменения в сигнатуре `scout_research_async`:

```python
@mcp.tool()
async def scout_research_async(
    topic: str,
    query: str,
    source_urls: list[str] | None = None,   # теперь опциональный
    auto_collect: bool = False,             # новый
    auto_collect_count: int = 150,          # новый
    top_k: int = 10,                        # снизить дефолт с 15 до 10
    model: str = "haiku",
    language: str = "ru",
    save_to: str | None = None,
) -> dict:
    """Start a background research job.

    Two URL modes:
    - source_urls provided: use given list directly
    - auto_collect=True: Haiku finds URLs automatically via web_search

    Returns immediately with job_id. Poll with scout_job_status(job_id).
    """
    if not source_urls and not auto_collect:
        return {"error": "Provide source_urls or set auto_collect=True"}

    llm_model = MODEL_MAP.get(model, MODEL_MAP["haiku"])
    job_id = str(uuid4())

    _jobs[job_id] = {
        "job_id": job_id,
        "topic": topic,
        "total_urls": len(source_urls) if source_urls else "auto",
        "query": query,
        "model": model,
        "status": "running",
        "stage": "queued",
        "message": "Задача создана",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    asyncio.create_task(_run_research_job(
        job_id, topic, source_urls or [], query, top_k, llm_model,
        language, save_to, auto_collect, auto_collect_count,
    ))
    return {
        "job_id": job_id,
        "status": "running",
        "message": (
            f"Задача запущена. auto_collect={auto_collect}. "
            f"Отслеживайте: scout_job_status(job_id='{job_id}')"
        ),
    }
```

### Изменения в `_run_research_job`:

Добавить параметры `auto_collect: bool` и `auto_collect_count: int`.
В начале функции, до стейджа test_indexing, вставить сбор URL:

```python
# Stage 0: auto_collect если запрошен
collected_urls: list[str] = []
if auto_collect:
    _update("collecting_urls",
            message=f"Haiku собирает URL по теме '{topic}'...")
    from src.ingestion.url_collector import collect_urls as _collect
    collected_urls = await _collect(
        topic=topic, language=language, n_urls=auto_collect_count
    )
    all_urls = list(dict.fromkeys((source_urls or []) + collected_urls))
    _update("urls_collected",
            auto_collected=len(collected_urls),
            total_urls=len(all_urls),
            message=f"Собрано {len(collected_urls)} URL. Итого: {len(all_urls)}.")
    source_urls = all_urls  # передать дальше в тест и полный прогон
    job["total_urls"] = len(all_urls)

if not source_urls:
    _update("error", status="failed", error="No URLs after auto_collect")
    return
```

---

## Шаг 4 — Обновить команду /research

**Файл:** `E:\Scout\.claude\commands\research.md`

Заменить использование `scout_research` + nohup на нативный `scout_research_async`.
Команда должна вызывать один инструмент и опрашивать статус через `scout_job_status`.

Новый шаг 3 в команде:

```
Вызвать scout_research_async с параметрами:
  topic, query, auto_collect=True, auto_collect_count=150, model, top_k=10

Сразу написать пользователю: "🚀 Запущено (job_id: XXX). Жду..."

Опрашивать scout_job_status(job_id) каждые 3 минуты.
При каждой проверке писать: "⏳ [N мин] stage=<stage> — <message>"

Когда status==completed — вызвать scout_job_result(job_id) для получения брифа.
```

---

## Шаг 5 — Тесты

### Тест retry (unit):

```python
# tests/test_briefer_retry.py
import pytest
from unittest.mock import AsyncMock, patch
import anthropic

@pytest.mark.asyncio
async def test_retry_on_rate_limit():
    """Briefer должен сделать 3 попытки при 429 и вернуть error."""
    from src.llm.anthropic_briefer import AnthropicBriefer

    briefer = AnthropicBriefer(api_key="test")
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        raise anthropic.RateLimitError(
            "rate limit", response=None, body={}
        )

    with patch.object(briefer._client.messages, "create", side_effect=fake_create):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await briefer.generate_brief("ctx", "topic")

    assert call_count == 3        # 1 попытка + 2 retry
    assert result["brief"] is None
    assert "rate_limit" in result["error"]
```

### Тест async инструмента (integration):

```bash
python3 << 'SCRIPT'
import json, subprocess, time

def mcp_init():
    r = subprocess.run(
        ["curl", "-si", "-X", "POST", "http://localhost:8020/mcp",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json, text/event-stream",
         "-d", '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sc022-test","version":"1.0"}}}'],
        capture_output=True, text=True, timeout=30
    )
    for line in r.stdout.split("\n"):
        if line.lower().startswith("mcp-session-id:"):
            return line.split(":", 1)[1].strip()
    return ""

def mcp_call(params, sid, timeout=60):
    payload = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":params})
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json, text/event-stream",
         "-H", f"Mcp-Session-Id: {sid}",
         "-d", payload],
        capture_output=True, text=True, timeout=timeout
    )
    body = ""
    for line in r.stdout.split("\n"):
        if line.startswith("data:"):
            body = line[5:].strip()
            break
    return json.loads(body)

sid = mcp_init()

# Запустить async research с auto_collect
res = mcp_call({
    "name": "scout_research_async",
    "arguments": {
        "topic": "тест SC-022 — рынок труда кадровый дефицит",
        "query": "дефицит кадров по отраслям, зарплаты",
        "auto_collect": True,
        "auto_collect_count": 20,
        "model": "haiku",
        "top_k": 7,
    }
}, sid)

job_id = res.get("result", {}).get("job_id")
print(f"job_id: {job_id}")
assert job_id, "job_id не получен"

# Polling статуса раз в 30 секунд, max 10 минут
for i in range(20):
    time.sleep(30)
    status = mcp_call({
        "name": "scout_job_status",
        "arguments": {"job_id": job_id}
    }, sid)
    r = status.get("result", {})
    stage = r.get("stage")
    msg = r.get("message", "")
    print(f"[{(i+1)*30}s] stage={stage} | {msg[:80]}")
    if r.get("status") in ("completed", "failed"):
        break

# Получить результат
result = mcp_call({
    "name": "scout_job_result",
    "arguments": {"job_id": job_id}
}, sid)
r = result.get("result", {})
print(f"\nstatus: {r.get('status')}")
print(f"auto_collected: {r.get('auto_collected')}")
print(f"documents: {r.get('documents_count')}")
print(f"tokens: {r.get('tokens_used')}")
print(f"error: {r.get('error')}")
print(f"brief[:200]: {str(r.get('brief', ''))[:200]}")
assert r.get("status") == "completed", f"Ожидали completed, получили: {r.get('status')}"
assert r.get("brief"), "brief пустой"
print("\n✅ SC-022 ТЕСТ ПРОЙДЕН")
SCRIPT
```

---

## Критерии готовности

Тест `test_briefer_retry.py` зелёный — briefer делает 3 попытки на 429.
`scout_research_async(auto_collect=True)` возвращает `job_id` немедленно.
`scout_job_status` показывает стейдж `collecting_urls` при auto_collect.
Когда бриф готов, `scout_job_result` возвращает непустой `brief` и `error=None`.
CI зелёный.

---

## После выполнения

Обновить команду `/research` (`.claude/commands/research.md`) — заменить
nohup-логику на `scout_research_async` + `scout_job_status` polling.
Задача `/research` должна вызывать только MCP-инструменты без shell-скриптов.

---

*Дата создания: 2026-03-18 | Вскрыто при SC исследовании рынка труда*

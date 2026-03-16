# SC-019 — Реранкер: двухэтапный поиск через CrossEncoder

## Цель

Улучшить качество поиска за счёт двухэтапного retrieval:
широкий захват через ChromaDB (top-50) → точная переоценка через CrossEncoder → финальный top-k для брифа.

По итогам SC-012..SC-017.2 cosine similarity держится в диапазоне 0.67–0.91.
Верхняя граница выросла за счёт качественных URL от Qwen, но проблема осталась —
CosineSimilarity не различает "хороший" и "посредственный" чанк внутри плотного
диапазона: разница между 5-м и 15-м результатом может быть всего 0.02–0.05.
CrossEncoder оценивает пару (запрос, документ) напрямую — это принципиально
точнее для ранжирования, особенно на нишевых запросах.

**Важно**: `sentence-transformers` уже установлен (используется в `Searcher`),
CrossEncoder входит в тот же пакет. Новых зависимостей в `requirements.txt` нет.

---

## ⚠️ Обязательно перед написанием кода

Прочитать эти файлы и убедиться что имена полей и сигнатуры методов совпадают
с тем что написано в задаче. Если есть расхождения — использовать то что в коде.

- `src/config.py` — модель `SearchResult`: проверить поля (ожидаются `chunk_id`,
  `text`, `source_url`, `source_title`, `similarity`) и модель `Settings`
- `src/retrieval/searcher.py` — сигнатура `Searcher.search()` и возвращаемый тип
- `src/retrieval/context_builder.py` — как принимает `list[SearchResult]`
- `src/pipeline.py` — метод `search()`: строки где вызываются `_searcher.search()`
  и `_context_builder.build()`

---

## Архитектура решения

Новый компонент `Reranker` встаёт между `Searcher` и `ContextBuilder` в `pipeline.search()`:

```
Searcher.search(top_k=50)       ← расширить захват
    ↓ list[SearchResult] × 50
Reranker.rerank(results, query) ← переоценить через CrossEncoder
    ↓ list[SearchResult] × 15   ← с обновлёнными similarity scores
ContextBuilder.build()          ← без изменений
```

`Searcher` и `ContextBuilder` не меняются. Весь новый код — в `reranker.py` и
небольшое изменение в `pipeline.py`.

---

## Шаг 1 — Создать `src/retrieval/reranker.py`

```python
"""CrossEncoder reranker — second-stage ranking over ChromaDB candidates."""

from __future__ import annotations

import os

from loguru import logger

from src.config import SearchResult

# Модель: лёгкая, ~80MB, хорошо работает на английском и неплохо на русском
_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ENV-флаг: выключить для быстрых тестов (RERANKER_ENABLED=false)
_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"


class Reranker:
    """Rerank search results using a CrossEncoder model.

    CrossEncoder scores query-document pairs directly — more accurate than
    cosine similarity, but slower (O(n) inference calls vs O(1) for bi-encoder).
    Use as a second stage over a small candidate set (top-50), not the full index.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # ленивая загрузка при первом вызове

    def _ensure_loaded(self) -> None:
        """Загрузить модель при первом обращении."""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info("Загружаю CrossEncoder модель: {}", self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("CrossEncoder готов")

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 15,
    ) -> list[SearchResult]:
        """Rerank results and return top_k with updated similarity scores.

        If RERANKER_ENABLED=false or results list is empty — returns results as-is
        (trimmed to top_k). This allows graceful degradation without reranking.

        Note: after reranking, the similarity field contains CrossEncoder logits
        (not cosine similarity). Values can be negative and are not bounded to [0,1].
        Only the relative ordering matters for ContextBuilder.
        """
        if not results:
            return results

        if not _ENABLED:
            logger.debug("Реранкер отключён (RERANKER_ENABLED=false), возвращаю top-{}", top_k)
            return results[:top_k]

        self._ensure_loaded()

        # CrossEncoder принимает список пар (query, document_text)
        # Проверить имя поля текста в SearchResult — должно быть .text
        pairs = [(query, r.text) for r in results]

        # predict() возвращает ndarray[float] — raw logits, не нормализованы
        scores: list[float] = self._model.predict(pairs).tolist()

        # Обновляем similarity в SearchResult и сортируем по новому score
        reranked = [
            SearchResult(
                chunk_id=r.chunk_id,
                text=r.text,
                source_url=r.source_url,
                source_title=r.source_title,
                similarity=round(float(score), 4),
            )
            for r, score in zip(results, scores)
        ]
        reranked.sort(key=lambda r: r.similarity, reverse=True)

        logger.info(
            "Reranker: {} кандидатов → top-{}, score range: {:.3f}..{:.3f}",
            len(results), top_k,
            reranked[0].similarity if reranked else 0,
            reranked[min(top_k, len(reranked)) - 1].similarity if reranked else 0,
        )
        return reranked[:top_k]
```

### Три архитектурных решения

**Ленивая загрузка** — `_model = None` при инициализации, загрузка при первом вызове.
CrossEncoder весит ~80MB и загружается ~3 секунды. Если грузить в `__init__`, то при
старте контейнера это блокирует health check. При ленивой загрузке первый `scout_search`
будет медленнее, но старт мгновенный.

**`RERANKER_ENABLED=false`** — graceful degradation. При выключенном флаге `rerank()`
просто возвращает `results[:top_k]`. Нужно для: быстрых тестов (не ждать загрузки),
отладки (сравнить с/без реранкера), production rollback.

**CrossEncoder score ≠ cosine similarity** — raw logits могут быть отрицательными,
не ограничены [0, 1]. Записываем их в поле `similarity` как есть. Для ContextBuilder
и брифа это не важно — он смотрит только на порядок и берёт top-k.

---

## Шаг 2 — Изменить `src/pipeline.py`

Агент обязан прочитать текущий `pipeline.py` перед правкой, особенно метод `search()`.

Добавить `Reranker` в `__init__` рядом с другими компонентами:

```python
from src.retrieval.reranker import Reranker

class ScoutPipeline:
    def __init__(self) -> None:
        # ... существующие компоненты без изменений ...
        self._reranker = Reranker()  # ← добавить
```

Изменить метод `search()` — расширить первичный захват и добавить шаг реранкинга.
Вставить реранкер строго между вызовом searcher и вызовом context_builder:

```python
# Расширенный захват: берём top-50 кандидатов вместо top_k
# Реранкер отберёт лучшие top_k из них
candidates_k = max(top_k * 5, 50)   # не менее 50, не менее 5×top_k

candidates = self._searcher.search(
    query=query,
    session_id=session_id,
    top_k=candidates_k,              # ← было top_k, стало candidates_k
    min_similarity=session.config.min_similarity,
)

# Реранкинг: CrossEncoder переоценивает кандидатов, возвращает top_k
results = self._reranker.rerank(query=query, results=candidates, top_k=top_k)

return self._context_builder.build(
    session=session,
    query=query,
    results=results,
    total_in_index=session.chunks_count,
)
```

Формула `candidates_k = max(top_k * 5, 50)`: при стандартном `top_k=10` → `candidates_k=50`,
при `top_k=15` (brief) → `candidates_k=75`. Разумный диапазон без лишней нагрузки.

---

## Шаг 3 — Добавить в `.env.example`

```
RERANKER_ENABLED=true   # false — отключить CrossEncoder для быстрых тестов
```

---

## Шаг 4 — Тесты

Создать `tests/test_reranker.py`. Тест с реальной моделью не включать в CI
(загрузка ~80MB замедляет CI). Покрываем только быстрые сценарии:

```python
import os
import pytest
from src.config import SearchResult
from src.retrieval.reranker import Reranker


def _make_result(text: str, idx: int = 0) -> SearchResult:
    return SearchResult(
        chunk_id=f"id_{idx}",
        text=text,
        source_url=f"https://example.com/{idx}",
        source_title=f"Doc {idx}",
        similarity=0.7,
    )


def test_reranker_disabled(monkeypatch):
    """При RERANKER_ENABLED=false возвращает results[:top_k] без загрузки модели."""
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    import importlib
    import src.retrieval.reranker as mod
    importlib.reload(mod)  # подхватить новый env
    reranker = mod.Reranker()
    results = [_make_result(f"text {i}", i) for i in range(10)]
    reranked = reranker.rerank("query", results, top_k=3)
    assert len(reranked) == 3
    assert reranker._model is None  # модель не загружалась


def test_reranker_empty_input():
    """Пустой список возвращается как есть."""
    monkeypatch = None  # не нужен — пустой список обрабатывается до проверки флага
    reranker = Reranker()
    assert reranker.rerank("query", [], top_k=5) == []


def test_reranker_fewer_than_top_k(monkeypatch):
    """Если кандидатов меньше top_k — возвращает все."""
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    import importlib
    import src.retrieval.reranker as mod
    importlib.reload(mod)
    reranker = mod.Reranker()
    results = [_make_result("text", 0)]
    reranked = reranker.rerank("query", results, top_k=10)
    assert len(reranked) == 1
```

---

## Ожидаемый эффект

Основная польза — на нишевых запросах где cosine similarity не различает
качество документов с разницей 0.02–0.05. CrossEncoder видит смысловую связь
query↔document, а не только векторную близость. По benchmark данным cross-encoder
over bi-encoder даёт +10–20% по MRR@10. Для Scout это значит что Haiku получит
более точный контекст и меньше шума → качественнее бриф.

---

## Критерии готовности

- `src/retrieval/reranker.py` создан, `Reranker.rerank()` работает
- `RERANKER_ENABLED=false` — модель не загружается, тест проходит
- `pipeline.search()` использует `candidates_k=max(top_k*5, 50)`
- `.env.example` обновлён
- Тесты проходят, CI зелёный

---

*Дата создания: 2026-03-16 | Обновлено: 2026-03-16 (мотивация актуализирована под SC-017.2, усилен акцент на чтение кода перед реализацией)*

---

## ✅ Статус: ВЫПОЛНЕНА

**Дата завершения:** 2026-03-16

**Что сделано:**
- Создан `src/retrieval/reranker.py` — `Reranker` с ленивой загрузкой CrossEncoder
- `RERANKER_ENABLED` env-флаг: при `false` — возврат `results[:top_k]` без загрузки модели
- `src/pipeline.py` — добавлен `self._reranker = Reranker()`, метод `search()` расширен: `candidates_k = max(top_k*5, 50)`, реранкинг между Searcher и ContextBuilder
- `.env.example` — добавлена секция `RERANKER_ENABLED=true`
- `tests/test_reranker.py` — 3 теста (disabled, empty input, fewer than top_k)
- `tests/test_pipeline.py` — добавлен mock `_reranker` в `_make_pipeline()`
- 47/47 тестов pass

**Отклонения от плана:**
- В `_make_pipeline()` потребовалось настроить `side_effect` для `rerank()` (возврат списка, а не MagicMock)

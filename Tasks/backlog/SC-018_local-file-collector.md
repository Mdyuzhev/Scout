# SC-018 — LocalFileCollector: поддержка локальных файлов как источников

## Цель

Реализовать `LocalFileCollector` — коллектор который читает локальные файлы
(`txt`, `md`, `pdf`, `docx`) и превращает их в `Document` объекты для дальнейшей
индексации в ChromaDB.

После задачи `source_type: "files"` в `scout_index` принимает список путей
к файлам вместо URL. Полезно для исследований по внутренним документам,
отчётам, выгрузкам из CRM, PDF-файлам аналитических агентств.

`SourceType.LOCAL_FILE` уже объявлен в `config.py` — нужно его реализовать.

---

## Контекст: где это применяется

Три реальных сценария которые SC-018 разблокирует:

Первый — исследование по скачанным PDF-отчётам. Например, скачал отчёт
Автостата или McKinsey, положил в папку, передал пути в scout_index. Scout
индексирует PDF без веб-краулинга.

Второй — внутренние документы компании. Маркетинговые брифы, технические
спецификации, экспорты из Confluence в формате markdown — всё это можно
проиндексировать и искать по ним семантически.

Третий — комбинирование источников. Часть данных взята из веба (URL-режим),
часть — локальные файлы. Сейчас такой сценарий невозможен.

---

## Шаги выполнения

### Шаг 1 — Создать `src/ingestion/local_file.py`

Новый коллектор по паттерну BaseCollector:

```python
"""LocalFileCollector — reads local files (txt, md, pdf, docx) into Documents."""

from __future__ import annotations

import hashlib
from pathlib import Path

from loguru import logger

from src.config import Document, ResearchConfig
from .base import BaseCollector


# Поддерживаемые расширения
_SUPPORTED_EXT = {".txt", ".md", ".pdf", ".docx"}


class LocalFileCollector(BaseCollector):
    """Collect documents from local filesystem paths."""

    async def collect(
        self, config: ResearchConfig
    ) -> tuple[list[Document], list[str], int]:
        """
        config.source_urls содержит пути к файлам (не URL).
        Возвращает (documents, failed_paths, 0).
        blocked_count всегда 0 — стоп-листа для файлов нет.
        """
        paths = list(config.source_urls)  # переиспользуем поле source_urls
        docs: list[Document] = []
        failed: list[str] = []

        for path_str in paths:
            path = Path(path_str)
            try:
                doc = await self._read_file(path)
                if doc is not None:
                    docs.append(doc)
                else:
                    failed.append(path_str)
            except Exception as exc:
                logger.warning("Ошибка чтения {}: {}", path_str, exc)
                failed.append(path_str)

        logger.info(
            "LocalFileCollector: {} документов, {} ошибок для темы '{}'",
            len(docs), len(failed), config.topic,
        )
        return docs, failed, 0

    async def _read_file(self, path: Path) -> Document | None:
        """Прочитать файл и вернуть Document. None если неподдерживаемый тип."""
        if not path.exists():
            logger.warning("Файл не найден: {}", path)
            return None

        ext = path.suffix.lower()

        if ext not in _SUPPORTED_EXT:
            logger.debug("Неподдерживаемый тип файла: {}", ext)
            return None

        if ext in {".txt", ".md"}:
            text = self._read_text(path)
        elif ext == ".pdf":
            text = self._read_pdf(path)
        elif ext == ".docx":
            text = self._read_docx(path)
        else:
            return None

        if not text or len(text.strip()) < 50:
            logger.debug("Слишком мало контента в {}", path)
            return None

        content_hash = hashlib.sha256(text[:1000].encode()).hexdigest()
        return Document(
            url=str(path),          # путь к файлу как "URL"
            title=path.stem,        # имя файла без расширения
            content=text.strip(),
            content_hash=content_hash,
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        """Чтение txt/md файлов."""
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _read_pdf(path: Path) -> str:
        """Извлечение текста из PDF через pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber не установлен: pip install pdfplumber")

        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)

    @staticmethod
    def _read_docx(path: Path) -> str:
        """Извлечение текста из docx через python-docx."""
        try:
            from docx import Document as DocxDocument
        except ImportError:
            raise ImportError("python-docx не установлен: pip install python-docx")

        doc = DocxDocument(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
```

Ключевое архитектурное решение: `source_urls` переиспользуется как список путей к
файлам. Это позволяет не менять `ResearchConfig` — поле уже есть, семантика
расширяется для нового `source_type`.

### Шаг 2 — Добавить зависимости в `requirements.txt`

```
pdfplumber>=0.10
python-docx>=1.1
```

Обе библиотеки импортируются лениво внутри методов — если не установлены,
выбросят `ImportError` с понятным сообщением. Это важно: не хочется делать
`pdfplumber` обязательной зависимостью для тех кто PDF не использует.

### Шаг 3 — Обновить `ScoutPipeline` в `src/pipeline.py`

Добавить выбор коллектора по `source_type`:

```python
from src.ingestion.local_file import LocalFileCollector
from src.config import SourceType

class ScoutPipeline:
    def __init__(self) -> None:
        # ...
        self._web_collector = WebCollector()
        self._local_collector = LocalFileCollector()
        # ...

    async def index(self, config: ResearchConfig) -> ResearchSession:
        # ...
        # Выбор коллектора по source_type
        if config.source_type == SourceType.LOCAL_FILE:
            collector = self._local_collector
        else:
            collector = self._web_collector

        docs, failed_urls, blocked_count = await collector.collect(config)
        # ... остальная логика без изменений
```

### Шаг 4 — Обновить `scout_index` в `mcp_server.py`

Добавить параметр `file_paths` как альтернативу `source_urls`:

```python
@mcp.tool()
async def scout_index(
    topic: str,
    depth: str = "normal",
    queries: list[str] | None = None,
    language: str = "ru",
    llm_provider: str = "anthropic",
    source_type: str = "web",
    source_urls: list[str] | None = None,
    file_paths: list[str] | None = None,  # ← новый параметр
) -> dict:
    """Index documents for a research topic.

    Three modes:
    - source_type="web": search via DuckDuckGo (default)
    - source_type="urls": fetch provided URLs directly
    - source_type="files": read local files (txt, md, pdf, docx)

    For files mode, provide file_paths list with absolute paths on the server.
    Example: file_paths=["/opt/data/report.pdf", "/opt/data/notes.md"]
    """
    # При source_type="files" пути передаются через source_urls (внутри)
    effective_urls = source_urls or []
    if source_type == "files" and file_paths:
        effective_urls = file_paths
        source_type = "local_file"  # маппинг на SourceType.LOCAL_FILE

    config = ResearchConfig(
        topic=topic,
        depth=DepthLevel(depth),
        queries=queries or [],
        language=language,
        llm_provider=LLMProvider(llm_provider),
        source_type=SourceType(source_type),
        source_urls=effective_urls,
    )
    # ...
```

### Шаг 5 — Тест

В `tests/test_ingestion.py` добавить тест `LocalFileCollector`:

```python
import tempfile, textwrap
from pathlib import Path
import pytest

@pytest.mark.asyncio
async def test_local_txt():
    """LocalFileCollector читает txt файл."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write("Это тестовый документ.\n" * 20)
        path = f.name

    collector = LocalFileCollector()
    config = ResearchConfig(
        topic="test", source_type=SourceType.LOCAL_FILE,
        source_urls=[path]
    )
    docs, failed, blocked = await collector.collect(config)
    assert len(docs) == 1
    assert docs[0].title == Path(path).stem
    assert len(failed) == 0
    assert blocked == 0

@pytest.mark.asyncio
async def test_local_missing_file():
    """LocalFileCollector корректно обрабатывает несуществующий файл."""
    collector = LocalFileCollector()
    config = ResearchConfig(
        topic="test", source_type=SourceType.LOCAL_FILE,
        source_urls=["/nonexistent/file.txt"]
    )
    docs, failed, blocked = await collector.collect(config)
    assert len(docs) == 0
    assert len(failed) == 1
```

---

## Проверка после деплоя

Скопировать любой текстовый файл на сервер и проиндексировать:

```bash
# Скопировать тестовый файл на сервер (через homelab MCP run_shell_command)
echo "Тест LocalFileCollector. Это документ для проверки индексации." \
  > /opt/scout/data/test_doc.txt

# Индексировать через scout_index
# source_type="files", file_paths=["/opt/scout/data/test_doc.txt"]
```

---

## Критерии готовности

- `LocalFileCollector` читает `.txt`, `.md`, `.pdf`, `.docx`
- Несуществующие файлы попадают в `failed`, не роняют пайплайн
- `source_type="files"` работает через `scout_index` MCP-инструмент
- Тесты проходят, CI зелёный

---

*Дата создания: 2026-03-16*

# Команда /swarm — запуск роя исследователей (dual-node)

## Назначение

Запускает параллельный рой Scout-исследований. Работает с любым роем:
swarm_v1 (IT, 16 задач), swarm_v2 (IT, 50 задач), swarm_v3 (биомед, 50 задач).

Инфраструктура: две ноды Scout (:8020 и :8021), общий ChromaDB :8000,
общий PostgreSQL :5436.

SC-036: Scout = детерминированный инструмент, LLM на стороне агента.
SC-037: scout_enqueue для контроля параллелизма (если доступен).

---

## Конфигурация по рою (ВЫБРАТЬ ОДИН)

### swarm_v2 (текущий IT-рой, 50 задач):
```
SWARM_DIR:    E:\Scout\Tasks\backlog\swarm_v2\
TASK_PREFIX:  SW2-
RESULTS_DIR:  /opt/scout/results/swarm_v2/
URLS_DIR:     E:\Scout\results\swarm_v2\urls\
LIT_DIR:      E:\Diser\literature\  (english\ или russian\ по полю language)
SYSTEM_PROMPT: E:\Scout\.claude\prompts\swarm_brief_system_prompt.md
```

### swarm_v3 (биомедицинский рой, 50 задач):
```
SWARM_DIR:    E:\Scout\Tasks\backlog\swarm_v3\
TASK_PREFIX:  SW3-
RESULTS_DIR:  /opt/scout/results/swarm_v3/
URLS_DIR:     E:\Scout\results\swarm_v3\urls\
LIT_DIR:      E:\Diser\literature\biotech\
SYSTEM_PROMPT: E:\Scout\Tasks\backlog\swarm_v3\SYSTEM_PROMPT_swarm_v3.md
```

Нечётные номера → NODE_A (:8020), чётные → NODE_B (:8021).

---

## Схема параллелизма

**Волна 1 — сбор URL (агент, подписка, батчи по 10):**
Агент выполняет web_search по каждой задаче. Результаты → URLS_DIR\{PREFIX}-{NNN}_urls.txt.
НЕ использовать auto_collect (deprecated SC-036).

**Волна 2 — индексация через scout_enqueue (если SC-037 доступен):**
Для каждой задачи: `scout_enqueue(topic, query, source_urls=urls, model="opus", save_to=...)`.
Worker pool автоматически ограничивает 2 задачи на ноду.

Если scout_enqueue недоступен — fallback: scout_research_async(source_urls=urls)
по 2 задачи на ноду, ждать завершения партии перед следующей.

**Волна 3 — брифы (агент генерирует из чанков):**
Для каждой завершённой задачи:
1. `scout_get_context(session_id, query, top_k=15)` → чанки
2. Агент генерирует бриф (LLM подписка, model="opus")
3. `scout_save_brief(session_id, brief, model="claude-opus-4-6", save_to=...)`

---

## Алгоритм выполнения

### Шаг 0 — Pre-flight
1. Определить рой: спросить пользователя или прочитать из аргумента команды
2. `run_health_check(project="scout", no_cache=True)` — обе ноды healthy
3. Smoke test на :8020 и :8021
4. `get_docker_stats` — RAM < 80%, disk > 2GB
5. Создать URLS_DIR если не существует

### Шаг 1 — Загрузить конфигурацию
Прочитать SYSTEM_PROMPT из пути для выбранного роя.
Собрать список задач из SWARM_DIR (файлы {PREFIX}-*.md со статусом TODO).
Разделить по нодам: нечётные NNN → NODE_A, чётные → NODE_B.

Сообщить:
```
🚀 Рой {имя}: {N} задач | :8020 ({K}) + :8021 ({M})
Промпт: {путь к SYSTEM_PROMPT}
```

### Шаг 2 — Волна 1: сбор URL (агент, подписка)
Параллельные агенты (батчами по 10):
- Для каждой задачи: web_search × 4-6 запросов → собрать 150-200 URL
- НЕМЕДЛЕННО сохранить в URLS_DIR\{PREFIX}-{NNN}_urls.txt

### Шаг 3 — Волна 2: индексация
Для каждой задачи с собранными URL:
```
scout_enqueue(topic, query, source_urls=urls, model="opus",
              save_to="/opt/scout/results/{рой}/{PREFIX}-{NNN}.md")
```
Мониторинг: `scout_queue_status()` каждые 2 мин.
Прогресс: `scout_job_status(job_id)` для каждой задачи.

### Шаг 4 — Волна 3: брифы (агент генерирует)
Для каждой задачи со stage=indexing_done:
1. `scout_get_context(session_id, query, top_k=15)` → context
2. Агент генерирует бриф с system_prompt роя
3. `scout_save_brief(session_id, brief, model="claude-opus-4-6")`

Батчи по 8 параллельно.

### Шаг 5 — Сохранение результатов
Для каждой завершённой задачи:
1. Бриф с сервера → LIT_DIR (для swarm_v3 всё в biotech\)
2. Статус задачи: TODO → DONE
3. Запись в E:\Diser\notes\research_synthesis\embedding_map_v1.md

### Шаг 6 — Итоговый отчёт
```
✅ Рой {имя} завершён
Задач: {N} | Docs: {сумма} | Chunks: {сумма}
URL: {сумма} → {URLS_DIR}
Брифы: {LIT_DIR}
```

---

## Правила

:8021 нестабильнее — при недоступности деградируем на одну ноду, не останавливаем рой.
Максимум 2 задачи на ноду (контролируется worker pool SC-037).
URL сохранять СРАЗУ после Волны 1.
Системный промпт — обязателен, разный для каждого роя.
BLOCKED задачи — пропускать, отмечать в отчёте.
НЕ использовать auto_collect — deprecated (SC-036).

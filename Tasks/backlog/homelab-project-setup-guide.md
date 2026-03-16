# Настройка нового проекта для работы с MCP-инфраструктурой

> Основано на реальной инфраструктуре homelab.
> Адаптировать значения в {{ }} под конкретный проект.

---

## Инфраструктура (общая для всех проектов)

| Компонент | Адрес | Назначение |
|-----------|-------|-----------|
| homelab-mcp | 192.168.1.74:8765 (LAN, основной) | Управление сервером, Docker, shell, заметки |
| homelab-mcp | 100.81.243.12:8765 (Tailscale, резерв) | Когда работаем не дома |
| agent-context | 127.0.0.1:8766 | Контекст сессий, история, чекпоинты (PM2 на Windows) |
| Сервер SSH | 192.168.1.74 / 100.81.243.12 | Деплой через paramiko |

Логика выбора адреса: 99% времени работаем дома — LAN быстрее и стабильнее.
Tailscale — резерв для работы вне дома. В .mcp.json всегда LAN, в /init — fallback на Tailscale.

---

## Шаг 1 — .mcp.json в корне проекта

Создать рядом с .git:

```json
{
  "mcpServers": {
    "homelab": {
      "type": "http",
      "url": "http://192.168.1.74:8765/mcp"
    },
    "agent-context": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

type: http — оба сервера постоянно запущены, нет spawn процессов при старте чата.
Это ключевое отличие от устаревшего "command: node" (stdio-транспорт).

---

## Шаг 2 — .claude/settings.json

```json
{
  "permissions": {
    "allow": [
      "Bash(*)", "Read(*)", "Write(*)", "Edit(*)",
      "Glob(*)", "Grep(*)", "WebFetch(*)", "WebSearch(*)",
      "Agent(*)", "NotebookEdit(*)",
      "mcp__homelab__*",
      "mcp__agent-context__*"
    ],
    "deny": []
  }
}
```

---

## Шаг 3 — .claude/commands/init.md

Заменить PROJECT_PATH на реальный путь (например "E:/moex").

```markdown
# Команда /init — инициализация сессии

Сразу написать: **Начинаю работу**

Выполни последовательно, после каждого шага писать статус:

**Шаг 1:** start_session с project_path = "{{ PROJECT_PATH }}"
-> написать: Шаг 1 готов — сессия открыта

**Шаг 2:** Проверь доступность homelab-mcp:
curl -s --max-time 2 http://192.168.1.74:8765/health
- Если "status":"ok" — написать "homelab-mcp доступен (LAN)"
- Если недоступен — попробовать Tailscale:
  curl -s --max-time 2 http://100.81.243.12:8765/health
  - Если "status":"ok" — написать "homelab-mcp доступен (Tailscale — не дома?)"
  - Если оба недоступны — написать "homelab-mcp недоступен"
-> написать: Шаг 2 готов — сервер проверен

**Шаг 3:** get_context — полный контекст включая чекпоинты
-> написать: Шаг 3 готов — контекст получен

---

После всех шагов — итоговая сводка:
- Номер открытой сессии
- Статус homelab-mcp (LAN / Tailscale / недоступен)
- Что было в предыдущей сессии (если есть)
- Текущий backlog задач
```

Пути проектов:
- LocOll     → E:/LocOll
- moex       → E:/moex
- ErrorLens  → E:/EL/errorlens
- Warehouse  → E:/WarehouseHub
- RAG_qa     → E:/RAG_qa

---

## Шаг 4 — .claude/commands/server-status.md

Полный срез сервера — отдельная команда, не в /init (чтобы не тормозить старт).

```markdown
# Команда /server-status — полный срез состояния сервера

Вызови server_status из agent-context MCP.

Покажи:
- CPU, RAM, диск, uptime
- Статусы контейнеров (особо выдели unhealthy)
- События за последний час
- Активные заметки
```

---

## Шаг 5 — .claude/CLAUDE.md

Держать компактным (~80-120 строк) — загружается при каждом старте.
Справочные данные (архитектура, стек, SQL) выносить в reference.md.

Шаблон:

```markdown
# CLAUDE.md — {{ НАЗВАНИЕ ПРОЕКТА }}

## Начало работы

При открытии нового чата — запустить /init.
Для полного среза сервера — /server-status.

## ЧЕКПОИНТЫ — обязательно

Контекст разговора конечен и сжимается без предупреждения:

1. При завершении каждого шага задачи — вызвать mcp__agent-context__checkpoint
2. Каждые 5 вызовов инструментов — принудительный checkpoint
3. При system-reminder о сжатии контекста — немедленный checkpoint
4. Перед завершением задачи — end_session с полным итогом

Формат: "[шаг N] что сделано — что дальше"

Если agent-context недоступен — предупредить и продолжить без него.

---

## О проекте

{{ НАЗВАНИЕ }} — {{ КРАТКОЕ ОПИСАНИЕ }}
GitHub: https://github.com/Mdyuzhev/{{ REPO }}

---

## КАК ПОДКЛЮЧАТЬСЯ К СЕРВЕРУ

ssh/sshpass НЕ РАБОТАЮТ — Windows + кириллический username ломает known_hosts.
Только Python + paramiko:

    import paramiko, sys
    sys.stdout.reconfigure(encoding='utf-8')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('192.168.1.74', username='flomaster', password='Misha2021@1@', timeout=10)
    _, stdout, stderr = client.exec_command('КОМАНДА')
    print(stdout.read().decode('utf-8', errors='replace').strip())
    client.close()

Параметры:
- Host LAN (основной):  192.168.1.74
- Host Tailscale (резерв): 100.81.243.12
- User: flomaster
- Password: Misha2021@1@
- Путь на сервере: {{ SERVER_PATH }}

Полные шаблоны: E:\HomeLab\server-access.md

---

{{ СПЕЦИФИКА ПРОЕКТА: стек, порты, запреты }}

---

Полный справочник: .claude/reference.md

---

## Реестр задач

| ID | Название | Статус |
|----|----------|--------|
| {{ PREFIX }}-001 | первая-задача | выполнена |

Задачи: Tasks/backlog/ (в работе), Tasks/done/ (выполненные)

---

## Запрещено

- ssh, sshpass — только paramiko
{{ СПЕЦИФИЧНЫЕ ЗАПРЕТЫ }}

---

Последнее обновление: {{ ДАТА }}
```

---

## Шаг 6 — .claude/reference.md (для больших проектов)

Выносить сюда всё что не нужно при каждом старте:
архитектурные диаграммы, таблицы стека, SQL-схемы, команды деплоя.

В CLAUDE.md оставить только строку:
  Полный справочник: .claude/reference.md

---

## Шаг 7 — Зарегистрировать в agent-context

Файл C:\Users\Михаил\.agent-context\registry.json — редактировать вручную.
Добавить в секцию "projects":

```json
"{{ АБСОЛЮТНЫЙ_ПУТЬ }}": {
  "name": "{{ НАЗВАНИЕ }}",
  "type": "{{ ТИП }}",
  "description": "{{ ОПИСАНИЕ }}"
}
```

Типы: experiment, backend, bot, infra, qa.

После добавления:
  pm2 restart agent-context

---

## Шаг 8 — Структура Tasks/

  {{ PROJECT_ROOT }}/
  └── Tasks/
      ├── backlog/    <- активные: PREFIX-NNN_slug.md
      └── done/       <- выполненные

---

## Проверка — открыть проект в Claude Code, вызвать /init

Ожидаемый результат:

  Начинаю работу

  [start_session]
  Шаг 1 готов — сессия открыта

  [curl 192.168.1.74:8765/health]
  homelab-mcp доступен (LAN)
  Шаг 2 готов — сервер проверен

  [get_context]
  Шаг 3 готов — контекст получен

  ════════════════════
  Сессия #1 | LAN
  Предыдущих сессий нет
  Backlog: пусто

Если "Tailscale" — не дома, всё работает но через VPN.
Если "недоступен" — сервер выключен или нет сети.

Если agent-context недоступен:
  pm2 list        <- проверить статус
  pm2 resurrect   <- поднять после перезагрузки

---

## Итоговая структура файлов

  {{ PROJECT_ROOT }}/
  ├── .mcp.json              <- LAN IP, http транспорт
  ├── .claude/
  │   ├── CLAUDE.md          <- компактный (~100 строк)
  │   ├── reference.md       <- справочник (по запросу)
  │   ├── settings.json      <- разрешения MCP
  │   └── commands/
  │       ├── init.md        <- /init
  │       ├── server-status.md <- /server-status
  │       └── task.md        <- /task
  └── Tasks/
      ├── backlog/
      └── done/

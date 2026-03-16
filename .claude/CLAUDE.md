# CLAUDE.md — Scout

## Начало работы

При открытии нового чата — запустить /init.
Для полного среза сервера — /server-status.

---

## ЧЕКПОИНТЫ — обязательно

Контекст разговора конечен и сжимается без предупреждения:

1. При завершении каждого шага задачи — вызвать `mcp__agent-context__checkpoint`
2. Каждые 5 вызовов инструментов — принудительный checkpoint
3. При system-reminder о сжатии контекста — немедленный checkpoint
4. Перед завершением задачи — `end_session` с полным итогом

Формат: `"[шаг N] что сделано — что дальше"`

Если agent-context недоступен — предупредить и продолжить без него.

---

## О проекте

**Scout** — MCP-сервер предобработки данных для продуктовых исследований.
Принцип: LLM — последний шаг, не первый.
GitHub: https://github.com/Mdyuzhev/Scout

Стек: Python 3.12, FastMCP 2.0, ChromaDB, PostgreSQL (порт 5436),
sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`), httpx, BS4.

Пайплайн: `ResearchConfig → WebCollector → Chunker → ChromaDB → Searcher → ResearchPackage → LLM brief`

Контейнеры на сервере: `scout-mcp` (порт 8020), `scout-postgres` (порт 5436).
Путь на сервере: `/opt/scout`

---

## ДЕПЛОЙ — единственный правильный флоу

```
1. Пишем/правим код локально (E:\Scout)
2. git add + git commit + git push origin main
3. GitHub Actions runner scout-homelab подхватывает push автоматически
4. CI: git pull → docker compose up --build -d → health check
5. Проверяем результат через homelab MCP: docker ps, curl /health
6. Завершаем задачу → обновляем CLAUDE.md → git push → checkpoint
```

**Агент НИКОГДА не деплоит вручную** — ни через homelab MCP, ни через paramiko.
Исключение: первичная настройка `/opt/scout` — уже выполнена, повторять не нужно.

### Инфраструктура деплоя (уже настроена, не трогать)

| Компонент | Статус | Где |
|-----------|--------|-----|
| `/opt/scout` | ✅ клонирован | сервер |
| `.env` | ✅ заполнен (ANTHROPIC_API_KEY пуст) | `/opt/scout/.env` |
| GitHub Actions runner | ✅ `scout-homelab` systemd | сервер |
| `deploy.yml` | ✅ триггер на push в main | `.github/workflows/` |

---

## КАК ПОДКЛЮЧАТЬСЯ К СЕРВЕРУ

**Homelab MCP** — основной способ для всех операций с сервером:
- `run_shell_command` — команды на сервере
- `exec_in_container` — команды внутри контейнера
- `get_services_status`, `get_service_logs`

**Paramiko** — только если homelab MCP недоступен, только после явного разрешения:

```python
import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.1.74', username='flomaster', password='Misha2021@1@', timeout=10)
_, stdout, stderr = client.exec_command('КОМАНДА')
print(stdout.read().decode('utf-8', errors='replace').strip())
client.close()
```

LAN (дома): `192.168.1.74` | Tailscale (удалённо): `100.81.243.12`
ssh/sshpass НЕ РАБОТАЮТ — кириллический `C:\Users\Михаил` ломает known_hosts.

---

## Реестр задач

| ID | Название | Статус |
|----|----------|--------|
| SC-001 | project-scaffold | ✅ выполнена |
| SC-002 | data-models | ✅ выполнена |
| SC-003 | ingestion | ✅ выполнена |
| SC-004 | retrieval | ✅ выполнена |
| SC-005 | mcp-server | ✅ выполнена |
| SC-006 | postgres-session-store | ✅ выполнена |
| SC-007 | deploy | ✅ выполнена |
| SC-008 | first-real-run | ✅ выполнена |

Задачи: `Tasks/backlog/` (в работе), `Tasks/done/` (выполненные)

---

## Запрещено

- ssh, sshpass — только homelab MCP или paramiko
- Деплоить вручную — только через git push → CI/CD
- Настраивать /opt/scout или runner повторно — уже сделано
- Тянуть новые модели Ollama
- LLM на этапе сбора/фильтрации (только финальный шаг)

---

Полный справочник: `.claude/reference.md`

*Обновлено: 2026-03-16 (SC-008 done — первый боевой прогон успешен, 2 бага пофикшены)*

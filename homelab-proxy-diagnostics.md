# Диагностика проблем: homelab-proxy.js → homelab-mcp

**Документ для агента, поддерживающего проект LocOll / HomeLab MCP.**
Описывает наблюдаемые симптомы, предполагаемые причины и что проверить.

---

## Симптомы

1. При старте Claude Code в проекте агент сообщает что инструменты
   `mcp__homelab__*` недоступны — несмотря на то что контейнер `homelab-mcp`
   на сервере находится в статусе `running`.

2. Проблема воспроизводится **нестабильно**: иногда всё работает, иногда нет.
   При перезапуске Claude Code MCP часто начинает работать.

3. При недоступности MCP агент пытается использовать Tailscale IP
   (`100.81.243.12`) вместо LAN (`192.168.1.74`), хотя оба устройства
   находятся в одной локальной сети.

---

## Схема работы прокси

```
Claude Code (Windows)
    │
    │ stdio (JSON-RPC)
    ▼
homelab-proxy.js   ← C:\Users\Михаил\.agent-context\homelab-proxy.js
    │
    │ HTTP POST/SSE
    ▼
http://{host}:8765/mcp
    │
    ▼
homelab-mcp (Docker, network_mode: host, Ubuntu 24.04)
```

---

## Анализ кода прокси

### Проблема 1 — Таймаут probe слишком короткий

```js
const PROBE_TIMEOUT = 1500;  // ← 1.5 секунды

async function probeHost(host) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT);
  await fetch(`http://${host}:${MCP_PORT}/mcp`, { method: 'GET', ... });
  ...
}
```

**Что происходит**: при старте Claude Code прокси делает probe-запрос к серверу.
Если сервер не отвечает за 1500ms (холодный старт, временная нагрузка на сеть,
Windows DNS-резолвинг) — прокси считает хост недоступным и кэширует этот
результат на **всю сессию**:

```js
let resolvedHost = null;  // кэш — сбрасывается только при ошибке запроса

async function resolveHost() {
  if (resolvedHost) return resolvedHost;  // ← повторный probe не делается
  ...
  throw new Error(`server unreachable (tried ${TAILSCALE_IP}, ${LAN_IP})`);
}
```

**Последствие**: если probe провалился при старте — MCP недоступен до перезапуска
Claude Code, даже если сервер уже давно ответил бы.

**Рекомендация**: увеличить `PROBE_TIMEOUT` до 4000–5000ms и добавить retry.

---

### Проблема 2 — Нет retry при неудачном probe

Если оба хоста не ответили за 1500ms — прокси сразу бросает исключение.
Нет ни одной повторной попытки с задержкой.

**Рекомендация**: добавить 2–3 попытки с паузой 2 секунды между ними:

```js
async function resolveHost(retries = 3) {
  for (let i = 0; i < retries; i++) {
    const [lan, ts] = await Promise.all([
      probeHost(LAN_IP),
      probeHost(TAILSCALE_IP)
    ]);
    if (lan) { resolvedHost = LAN_IP; log(`using LAN: ${LAN_IP}`); return resolvedHost; }
    if (ts)  { resolvedHost = TAILSCALE_IP; log(`using Tailscale: ${TAILSCALE_IP}`); return resolvedHost; }
    if (i < retries - 1) {
      log(`probe failed, retry ${i + 1}/${retries} in 2s...`);
      await new Promise(r => setTimeout(r, 2000));
    }
  }
  throw new Error(`server unreachable after ${retries} attempts (tried LAN + Tailscale)`);
}
```

---

### Проблема 3 — probe бьёт в `/mcp` методом GET

```js
await fetch(`http://${host}:${MCP_PORT}/mcp`, { method: 'GET', ... });
```

FastMCP 2.0 со `streamable-http` транспортом возвращает на `GET /mcp` код
**405 Method Not Allowed**. Прокси обрабатывает 405 как "хост доступен" — это
корректно. Но если FastMCP изменит поведение или endpoint изменится — логика
сломается без очевидного симптома.

**Рекомендация**: добавить `/health` endpoint в `server.py` и бить probe туда:

```js
// В прокси: бьём в /health вместо /mcp
await fetch(`http://${host}:${MCP_PORT}/health`, { method: 'GET', ... });
// /health возвращает 200 — нет неоднозначности с 405
```

```python
# В server.py: добавить health endpoint
from starlette.responses import JSONResponse
from starlette.requests import Request

@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "homelab-mcp"})
```

---

### Проблема 4 — Нет лога при сбросе кэша хоста

```js
.catch(err => {
  resolvedHost = null;  // ← сбрасывается молча
  ...
})
```

При ошибке запроса (не probe, а рабочий вызов инструмента) кэш сбрасывается,
но в stderr ничего не пишется. Трудно диагностировать когда именно прокси
перешёл на другой хост.

**Рекомендация**: добавить лог:
```js
log(`request error, resetting host cache. Will re-probe on next call. Error: ${err.message}`);
resolvedHost = null;
```

---

## Что проверить на сервере

### 1. Контейнер запущен и порт слушает на 0.0.0.0

```bash
docker ps --filter name=homelab-mcp

ss -tlnp | grep 8765
# Должно быть: 0.0.0.0:8765
# Если 127.0.0.1:8765 — Windows-машина не достучится
```

### 2. Сервер отвечает на probe-запросы

```bash
# GET /mcp — должен вернуть 405
curl -v -X GET http://localhost:8765/mcp

# POST /mcp — должен вернуть 200 + список инструментов
curl -v -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### 3. Firewall не блокирует порт

```bash
sudo ufw status | grep 8765
```

### 4. Доступность с Windows-машины (PowerShell)

```powershell
Test-NetConnection -ComputerName 192.168.1.74 -Port 8765
# TcpTestSucceeded должно быть True
```

### 5. Время ответа сервера

```bash
# Должно быть << 1500ms
time curl -s -X GET http://localhost:8765/mcp
```

Если время ответа близко к 1500ms — probe будет нестабильно проваливаться.

---

## Итог: приоритизированный список правок

| # | Правка | Файл | Сложность |
|---|--------|------|-----------|
| 1 | Увеличить `PROBE_TIMEOUT` 1500 → 4000 | `homelab-proxy.js` | тривиально |
| 2 | Добавить retry (3 попытки, пауза 2с) | `homelab-proxy.js` | просто |
| 3 | Добавить лог при сбросе кэша хоста | `homelab-proxy.js` | тривиально |
| 4 | Добавить `/health` endpoint в сервер | `server.py` | просто |
| 5 | Переключить probe с `/mcp` на `/health` | `homelab-proxy.js` | просто |

Правки 1–3 дают немедленный эффект и безопасны.
Правки 4–5 делать вместе — сначала endpoint, потом прокси.

---

## Контекст окружения

| Параметр | Значение |
|----------|----------|
| Сервер | Ubuntu 24.04, `192.168.1.74` / `100.81.243.12` (Tailscale) |
| Контейнер | `homelab-mcp`, `network_mode: host`, порт 8765 |
| Прокси | `C:\Users\Михаил\.agent-context\homelab-proxy.js` |
| MCP Framework | FastMCP 2.0, транспорт `streamable-http` |
| Проект | `E:\LocOll` / `E:\HomeLab` |

---

*Создан: 2026-03-16 | Автор: анализ из проекта Scout*

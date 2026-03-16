# Команда /server-status — полный срез состояния сервера

Вызови `server_status` из agent-context MCP.

Покажи:
- CPU, RAM, диск, uptime
- Статусы всех контейнеров (особо выдели `unhealthy`)
- Контейнеры Scout: `scout-mcp`, `scout-postgres`
- События за последний час
- Активные заметки

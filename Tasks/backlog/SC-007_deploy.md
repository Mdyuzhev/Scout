# SC-007 — Deploy: Dockerfile, CI/CD, сервер

## Цель

Задеплоить Scout на сервер (`/opt/scout`) через GitHub Actions. После этой задачи
Scout MCP-сервер доступен по адресу `http://100.81.243.12:8020` и автоматически
переразворачивается при push в `main`.

---

## Контекст

Паттерн деплоя идентичен LocOll: self-hosted GitHub Actions runner уже установлен
на сервере (`/home/flomaster/actions-runner/`). При push в `main` runner делает
`git pull` → `docker compose up --build -d`. Нужно подключить Scout к тому же
runner и создать GitHub-репозиторий.

Перед деплоем проверить что порты 8020 и 5436 свободны.

---

## Шаги выполнения

### 1. Финальный Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Зависимости слоем до кода — для кэширования Docker layers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# sentence-transformers при первом запуске скачивает модель — кэшируем в слой
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY . .

CMD ["python", "mcp_server.py"]
```

Загрузка модели в слой сборки критична — иначе при каждом старте контейнера
300MB скачиваются заново (~2 минуты).

### 2. .github/workflows/deploy.yml

```yaml
name: Deploy Scout

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: self-hosted
    steps:
      - name: Pull latest code
        run: |
          cd /opt/scout
          git fetch origin main
          git reset --hard origin/main

      - name: Deploy
        run: |
          cd /opt/scout
          docker compose down
          docker system prune -f
          docker compose up --build -d

      - name: Health check
        run: |
          sleep 10
          curl -f http://localhost:8020/health || exit 1
          echo "Scout MCP is up"
```

### 3. Первичная настройка на сервере (через paramiko)

```bash
# Создать директорию
sudo mkdir -p /opt/scout
sudo chown flomaster:flomaster /opt/scout

# Клонировать репозиторий
cd /opt/scout && git clone https://github.com/Mdyuzhev/Scout.git .

# Создать .env из примера и заполнить секреты
cp .env.example .env
# POSTGRES_PASSWORD, ANTHROPIC_API_KEY — вставить вручную или через paramiko

# Первый запуск
docker compose up --build -d

# Проверка
curl http://localhost:8020/health
docker compose ps
```

### 4. Регистрация runner для репозитория Scout

Runner уже запущен как systemd-сервис. Нужно добавить Scout-репозиторий:
```bash
cd /home/flomaster/actions-runner
./config.sh --url https://github.com/Mdyuzhev/Scout --token TOKEN
```

Или использовать organization runner если он настроен для всех репозиториев.

### 5. Проверка после деплоя

```bash
# Статусы контейнеров
docker compose -f /opt/scout/docker-compose.yml ps

# Логи MCP сервера
docker logs scout-mcp --tail 50

# Health check
curl http://localhost:8020/health

# Тест MCP инструмента через paramiko с рабочей машины
curl -X POST http://100.81.243.12:8020/tools/scout_list_sessions \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## Критерии готовности

- `docker compose ps` показывает `scout-mcp` и `scout-postgres` в статусе `running/healthy`
- `curl http://100.81.243.12:8020/health` возвращает 200 с Windows-машины
- Push в `main` триггерит деплой через GitHub Actions без ошибок
- Полный цикл end-to-end: `scout_index` → `scout_search` → `scout_brief` работает
  на задеплоенном сервере

---

*Дата создания: 2026-03-16*

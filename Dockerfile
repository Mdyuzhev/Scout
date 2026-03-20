FROM python:3.12-slim

WORKDIR /app

# Зависимости отдельным слоем — Docker кэширует если requirements.txt не менялся
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps \
    && rm -rf /root/.cache/pip

# Предзагрузка bi-encoder модели (для Indexer и Searcher)
# ~470MB — кэшируется в слой образа, не скачивается при каждом старте
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Предзагрузка CrossEncoder модели (для Reranker)
# ~80MB — без этого Reranker пытается скачать при первом вызове scout_search
# и падает через HTTPS_PROXY если он настроен
RUN python -c "from sentence_transformers import CrossEncoder; \
    CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY . .

EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8020/health')" || exit 1

CMD ["python", "mcp_server.py"]

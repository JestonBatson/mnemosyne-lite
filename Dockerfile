FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install . \
    && rm -rf /app/build /app/src \
    && useradd --create-home --uid 10001 appuser

COPY migrations ./migrations
COPY scripts/migrate.py ./scripts/migrate.py
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"
CMD ["uvicorn", "mnemosyne_lite.api:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]

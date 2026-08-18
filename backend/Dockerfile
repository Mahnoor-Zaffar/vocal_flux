FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin"

WORKDIR /app

COPY pyproject.toml ./
COPY uv.lock ./
COPY app ./app

RUN uv sync --locked --no-dev

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10m --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

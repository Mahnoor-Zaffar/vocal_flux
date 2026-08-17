FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY uv.lock ./
COPY app ./app

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

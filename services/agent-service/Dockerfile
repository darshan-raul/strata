FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

RUN pip install --no-cache-dir uv==0.5.4

COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests

RUN uv sync --frozen --no-dev || uv sync --no-dev

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]

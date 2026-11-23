FROM node:24-bookworm-slim AS web
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY vendor ./vendor
RUN uv sync --frozen --no-dev
COPY app ./app
COPY --from=web /build/dist ./frontend/dist
RUN useradd --create-home --uid 10001 app && mkdir /app/data && chown app:app /app/data
USER app
ENV PATH="/app/.venv/bin:$PATH" SPOTDL_DATA_DIR=/app/data
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/api/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

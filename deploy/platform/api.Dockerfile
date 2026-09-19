FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR=/tmp/uv-cache PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev && \
    groupadd --gid 10001 torii && useradd --uid 10001 --gid 10001 --no-create-home torii
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "torii_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]

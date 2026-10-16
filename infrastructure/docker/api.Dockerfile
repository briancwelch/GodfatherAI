FROM python:3.14.8-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
COPY apps/api ./apps/api
COPY packages ./packages
COPY infrastructure/migrations ./infrastructure/migrations
RUN uv sync --locked --all-packages --no-dev
RUN groupadd --gid 10001 godfather && useradd --uid 10001 --gid 10001 --no-create-home godfather

FROM base AS development
RUN uv sync --locked --all-packages
COPY scripts ./scripts
COPY tests ./tests
USER 10001:10001
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider"]

FROM base AS runtime
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "godfather_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

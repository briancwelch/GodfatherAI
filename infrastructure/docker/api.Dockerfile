ARG PYTHON_IMAGE=python:3.14.8-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1
FROM ${UV_IMAGE} AS uv-tool
FROM ${PYTHON_IMAGE} AS base
COPY --from=uv-tool /uv /usr/local/bin/uv
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
RUN mkdir -p /var/lib/godfather/artifacts && chown -R 10001:10001 /var/lib/godfather
ENV GODFATHER_ARTIFACT_DIRECTORY=/var/lib/godfather/artifacts

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

# Release-only stage: non-editable API dependency closure, with no worker/dev tools.
FROM base AS production-build
RUN uv sync --locked --package godfather-api --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS production
ARG RELEASE_VERSION
ARG RELEASE_REVISION
ARG RELEASE_BUILT_AT
ENV GODFATHER_RELEASE_VERSION=$RELEASE_VERSION GODFATHER_RELEASE_REVISION=$RELEASE_REVISION GODFATHER_RELEASE_BUILT_AT=$RELEASE_BUILT_AT
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    GODFATHER_ARTIFACT_DIRECTORY=/var/lib/godfather/artifacts \
    GODFATHER_MIGRATIONS_DIRECTORY=/app/infrastructure/migrations
COPY --from=production-build /app/.venv /app/.venv
COPY infrastructure/migrations /app/infrastructure/migrations
RUN groupadd --gid 10001 godfather && useradd --uid 10001 --gid 10001 --no-create-home godfather \
    && mkdir -p /var/lib/godfather/artifacts && chown -R 10001:10001 /var/lib/godfather
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "godfather_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

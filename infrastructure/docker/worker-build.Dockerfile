# Linux worker artifacts only. This image is never installed on a contributor host.
FROM python:3.14.8-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
# uv needs workspace metadata, but the API is not installed or included.
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY packages ./packages
COPY scripts ./scripts
COPY docs/operations/worker-distribution.md ./docs/operations/worker-distribution.md
ARG RELEASE_VERSION
RUN python -m scripts.build_worker --version "$RELEASE_VERSION"

FROM scratch AS artifacts
COPY --from=build /app/dist/ /

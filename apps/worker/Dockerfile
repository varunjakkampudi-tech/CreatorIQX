# syntax=docker/dockerfile:1
#
# Production image for the worker app (P0-021, ADR 0003): a thin Celery CLI
# wrapper (apps/worker has no task code of its own - creatoriqx-api's
# modules.jobs.infrastructure.tasks defines ops.ping/ops.flaky) that depends
# on creatoriqx-api as a workspace package, so both are installed here.
# Follows the same official uv multi-stage pattern as apps/api/Dockerfile:
# https://docs.astral.sh/uv/guides/integration/docker/
#
# Build context MUST be the repository root (see .dockerignore):
#   docker build -f apps/worker/Dockerfile -t creatoriqx-worker .

ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.12.23

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- builder: resolve and install the worker package plus creatoriqx-api -
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies-only layer, cached on the lockfile. Unlike apps/api/Dockerfile,
# this still needs apps/api/src: creatoriqx-worker depends on creatoriqx-api
# (a real workspace dependency, not just the --no-install-project target), so
# uv must be able to build it even in this "dependencies" sync. apps/mcp-server
# isn't a dependency of creatoriqx-worker, but uv needs every workspace member
# declared in the root pyproject.toml to exist on disk, so its pyproject.toml
# is copied even though its source never is (same reasoning apps/api/Dockerfile
# already documents for apps/worker).
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/README.md apps/api/
COPY apps/api/src apps/api/src
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/mcp-server/pyproject.toml apps/mcp-server/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable --package creatoriqx-worker

# Now the real worker source, then re-sync to install creatoriqx-worker itself.
COPY apps/worker apps/worker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --package creatoriqx-worker

# --- final: slim runtime image, non-root ----------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie

# Pick up Debian security patches published after this base image tag was
# built (Trivy image scan, ci-security.yml).
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 creatoriqx \
    && useradd --system --uid 10001 --gid creatoriqx --no-create-home creatoriqx

COPY --from=builder --chown=creatoriqx:creatoriqx /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER creatoriqx
WORKDIR /app

CMD ["celery", "-A", "creatoriqx_api.modules.jobs.infrastructure.celery_app.celery_app", "worker", "--loglevel=info"]

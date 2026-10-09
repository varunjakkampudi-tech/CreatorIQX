# syntax=docker/dockerfile:1
#
# Production image for the api app (P0-021, ADR 0003's worker gets the
# matching Dockerfile in apps/worker/Dockerfile). Multi-stage, non-root,
# built from the uv workspace root (see .dockerignore and the build
# context note below) following the official uv Docker guide:
# https://docs.astral.sh/uv/guides/integration/docker/
#
# Build context MUST be the repository root, not apps/api, because this
# is a uv workspace member and needs the root pyproject.toml + uv.lock
# plus apps/worker (a workspace dependency isn't built here, but uv
# resolves the whole workspace graph even when syncing one package):
#   docker build -f apps/api/Dockerfile -t creatoriqx-api .

ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.12.23

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- builder: resolve and install only the api package's dependencies ----
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies-only layer: cached on the lockfile, invalidated only when
# a dependency actually changes, not on every source edit.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable --package creatoriqx-api

# Now the real source, then re-sync to install the project itself.
# apps/worker's own pyproject.toml is already present above (uv needs every
# workspace member declared in the root pyproject.toml to exist on disk),
# but creatoriqx-api does not depend on creatoriqx-worker, so its source is
# never copied into this image.
COPY apps/api apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --package creatoriqx-api

# --- final: slim runtime image, non-root ----------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie

RUN groupadd --system --gid 10001 creatoriqx \
    && useradd --system --uid 10001 --gid creatoriqx --no-create-home creatoriqx

COPY --from=builder --chown=creatoriqx:creatoriqx /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER creatoriqx
WORKDIR /app
EXPOSE 8000

CMD ["uvicorn", "creatoriqx_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

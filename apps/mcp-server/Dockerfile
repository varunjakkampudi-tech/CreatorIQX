# syntax=docker/dockerfile:1
#
# Production image for the mcp-server app (P0-070, ADR 0003's uv-workspace
# pattern, same as apps/api/Dockerfile and apps/worker/Dockerfile). Multi-stage,
# non-root, built from the uv workspace root following the official uv Docker
# guide: https://docs.astral.sh/uv/guides/integration/docker/
#
# Build context MUST be the repository root (see .dockerignore):
#   docker build -f apps/mcp-server/Dockerfile -t creatoriqx-mcp-server .

ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.12.23

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- builder: resolve and install only the mcp-server package's deps -----
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies-only layer, cached on the lockfile. mcp-server depends on
# neither creatoriqx-api nor creatoriqx-worker, but uv needs every workspace
# member declared in the root pyproject.toml to exist on disk (same reasoning
# apps/api/Dockerfile and apps/worker/Dockerfile already document), so their
# pyproject.toml files are copied even though their source never is.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/mcp-server/pyproject.toml apps/mcp-server/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable --package creatoriqx-mcp-server

# Now the real source, then re-sync to install the project itself.
COPY apps/mcp-server apps/mcp-server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --package creatoriqx-mcp-server

# --- final: slim runtime image, non-root ----------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie

RUN groupadd --system --gid 10001 creatoriqx \
    && useradd --system --uid 10001 --gid creatoriqx --no-create-home creatoriqx

COPY --from=builder --chown=creatoriqx:creatoriqx /app/.venv /app/.venv
# Same reasoning as apps/api/Dockerfile: the installed wheel is nowhere near
# packages/config, so ship the one file server.py needs and point
# PRODUCT_CONFIG_PATH (already env-overridable) at it.
COPY --chown=creatoriqx:creatoriqx packages/config/product.json /app/product-config/product.json

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRODUCT_CONFIG_PATH=/app/product-config/product.json \
    MCP_SERVER_HOST=0.0.0.0 \
    MCP_SERVER_PORT=8000

USER creatoriqx
WORKDIR /app
EXPOSE 8000

CMD ["python", "-m", "creatoriqx_mcp_server.server"]

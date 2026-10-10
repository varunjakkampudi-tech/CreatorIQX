# syntax=docker/dockerfile:1
#
# Production image for the web app (P0-021): Next.js App Router with
# output: "standalone" (apps/web/next.config.ts), so the final stage only
# needs .next/standalone + .next/static + public/, not full node_modules.
#
# Build context MUST be the repository root (see .dockerignore), because
# apps/web depends on the workspace packages packages/config and
# packages/api-client (pnpm workspace, pnpm-workspace.yaml):
#   docker build -f apps/web/Dockerfile -t creatoriqx-web .

ARG NODE_VERSION=22-slim

# --- deps: install the whole pnpm workspace's dependencies, frozen --------
FROM node:${NODE_VERSION} AS deps
# Keep in sync with package.json's "packageManager" field.
ARG PNPM_VERSION=12.10.1

RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/config/package.json packages/config/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# --- builder: build the Next.js app with standalone output ----------------
FROM node:${NODE_VERSION} AS builder
ARG PNPM_VERSION=12.10.1
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages ./packages
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web apps/web
COPY packages/config packages/config
COPY packages/api-client packages/api-client

# next.config.ts reads API_ORIGIN at build time (Next.js standalone output
# bakes rewrite destinations into the compiled server; the final stage never
# ships next.config.ts, so a runtime env var on the "web" service has no
# effect). docker-compose.yml passes this as a build arg so the container's
# /api rewrite points at the "api" service, not the next.config.ts default
# of 127.0.0.1:8000, which does not exist inside the web container.
ARG API_ORIGIN=http://127.0.0.1:8000
ENV API_ORIGIN=${API_ORIGIN}
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @creatoriqx/web build

# --- final: slim runtime image, non-root ----------------------------------
FROM node:${NODE_VERSION} AS runner

# Pick up Debian security patches published after this base image tag was
# built (Trivy image scan, ci-security.yml) - e.g. perl-base's
# CVE-2026-13221/-42496/-8376, fixed in a point release newer than the
# tag's own snapshot.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# The node:*-slim image already ships a non-root "node" user/group.
COPY --from=builder --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
# apps/web has no public/ directory yet (no screens exist before P0-090's
# wireframe approval, spec section 11) - add this COPY back once one does.

USER node
EXPOSE 3000

CMD ["node", "apps/web/server.js"]

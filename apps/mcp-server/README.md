# creatoriqx-mcp-server

Exposes CreatorIQX's capabilities to Claude over the Model Context Protocol
(spec §9 AI gateway and MCP design, ticket P0-070). This is the **scaffold**:
the official Python MCP SDK (`mcp`, verified at 2.3.0 - its first 2.x stable
release, superseding the older `FastMCP` class with `MCPServer`), wired up
and runnable, with one read-only tool proving it actually works end to end.
Module-specific tools (script, transcript, thumbnail, ...) arrive with their
own tickets later in Phase 1A onward - see `/skills/README.md` for the
SKILL.md format those will follow.

## Tools

- **`get_app_info`** (read-only): returns the product name (from
  `packages/config/product.json`, the same single source `creatoriqx-api`
  reads), this server's own version, and whether the CreatorIQX API is
  currently ready (a live `GET /readyz` against `API_BASE_URL`).

## Run locally

```
uv run --package creatoriqx-mcp-server python -m creatoriqx_mcp_server.server
```

Needs `.env`'s usual `py scripts/dev.py up` services if you want
`get_app_info`'s readiness check to report `true` (it still returns a
result, with `ready: false`, if the API isn't reachable). Then, with the
`cli` extra inspector:

```
uv run --package creatoriqx-mcp-server mcp dev src/creatoriqx_mcp_server/server.py
```

The Inspector opens in a browser; calling `get_app_info` with no arguments
should list the tool and return `"product_name": "CreatorIQX"`.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `MCP_SERVER_HOST` | `0.0.0.0` | Bind host for the `streamable-http` transport |
| `MCP_SERVER_PORT` | `8000` | Bind port |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Base URL `get_app_info` checks `/readyz` against |
| `PRODUCT_CONFIG_PATH` | `packages/config/product.json` (resolved from the repo root) | Same override `creatoriqx-api` supports, for the same reason: the packaged container doesn't have the whole repo tree |

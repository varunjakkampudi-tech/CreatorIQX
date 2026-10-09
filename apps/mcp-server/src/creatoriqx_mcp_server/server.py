"""The CreatorIQX MCP server (ticket P0-070, spec §9 AI gateway and MCP design).

A scaffold, deliberately: the official MCP Python SDK (verified at 2.3.0,
the current stable release as of 2026-10-10 - its `MCPServer` class
supersedes the older `FastMCP` name from the SDK's 1.x line), wired up and
runnable, with one read-only tool as the one working example the Phase 0
depth rule asks for. Module-specific tools arrive later with their own
tickets, following `/skills/README.md`'s SKILL.md format.

Read-only by default (spec §9): this server exposes no tool that mutates
anything. A later mutating tool must still only ever produce a draft that
passes through the approval gate - never a direct side effect.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from creatoriqx_mcp_server import __version__

# Repository layout: apps/mcp-server/src/creatoriqx_mcp_server/server.py ->
# repo root is parents[4]. Mirrors creatoriqx_api.settings's identical
# resolution (same depth, same reason): a packaged container ships only this
# one file from packages/config, at PRODUCT_CONFIG_PATH, not the whole repo.
_DEFAULT_PRODUCT_CONFIG = (
    Path(__file__).resolve().parents[4] / "packages" / "config" / "product.json"
)


def _product_name() -> str:
    path = Path(os.environ.get("PRODUCT_CONFIG_PATH", str(_DEFAULT_PRODUCT_CONFIG)))
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("productName")
    if not name:
        raise ValueError(f"productName missing in {path}")
    return str(name)


PRODUCT_NAME = _product_name()

mcp = MCPServer(name=PRODUCT_NAME, version=__version__)


async def check_readiness(base_url: str) -> tuple[bool, str]:
    """``GET {base_url}/readyz``. Never raises: a down API is a normal result, not an error."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/readyz")
    except httpx.HTTPError as exc:
        return False, f"unreachable: {exc}"
    return response.status_code == 200, response.text


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
async def get_app_info() -> dict[str, object]:
    """Report the product name, this server's version, and whether the CreatorIQX API is ready."""
    api_base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
    ready, detail = await check_readiness(api_base_url)
    return {
        "product_name": PRODUCT_NAME,
        "version": __version__,
        "ready": ready,
        "readiness_detail": detail,
    }


def main() -> None:
    """Entry point for ``python -m creatoriqx_mcp_server.server`` (the Compose CMD)."""
    host = os.environ.get("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_SERVER_PORT", "8000"))
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()

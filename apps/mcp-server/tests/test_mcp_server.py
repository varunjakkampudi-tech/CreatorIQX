"""Unit tests for the CreatorIQX MCP server scaffold (P0-070).

No real network: ``check_readiness`` is exercised against a monkeypatched
``httpx.AsyncClient`` here, not a live API. The real end-to-end proof - the
MCP Inspector listing ``get_app_info`` and it returning the real product
name - is a manual check (recorded in ``docs/PROGRESS.md``), since the MCP
Inspector is an interactive browser tool, not something this test suite can
drive headlessly.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import TracebackType

import pytest

import creatoriqx_mcp_server
import creatoriqx_mcp_server.server as server_module
from creatoriqx_mcp_server.server import PRODUCT_NAME, check_readiness, get_app_info, mcp

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_version_matches_pyproject() -> None:
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert creatoriqx_mcp_server.__version__ == project["project"]["version"]


def test_product_name_is_creatoriqx() -> None:
    # The acceptance test's own words: "returns product name 'CreatorIQX'".
    assert PRODUCT_NAME == "CreatorIQX"


async def test_get_app_info_is_registered_as_a_tool() -> None:
    tools = await mcp.list_tools()
    names = [tool.name for tool in tools]
    assert "get_app_info" in names


async def test_get_app_info_tool_is_marked_read_only() -> None:
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "get_app_info")
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient: same ``async with ... get(url)`` shape."""

    def __init__(self, response: _FakeResponse | Exception, **_kwargs: object) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def get(self, _url: str) -> _FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


async def test_check_readiness_true_when_the_api_answers_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(_FakeResponse(200, '{"status":"ready"}'), **kwargs),
    )

    ready, detail = await check_readiness("http://api:8000")

    assert ready is True
    assert detail == '{"status":"ready"}'


async def test_check_readiness_false_on_a_non_200_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(_FakeResponse(503, "not ready"), **kwargs),
    )

    ready, detail = await check_readiness("http://api:8000")

    assert ready is False
    assert detail == "not ready"


async def test_check_readiness_false_and_no_raise_when_the_api_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        server_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(httpx.ConnectError("refused"), **kwargs),
    )

    ready, detail = await check_readiness("http://api:8000")

    assert ready is False
    assert "unreachable" in detail


async def test_get_app_info_reports_product_name_version_and_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(_FakeResponse(200, "ok"), **kwargs),
    )

    result = await get_app_info()

    assert result == {
        "product_name": "CreatorIQX",
        "version": creatoriqx_mcp_server.__version__,
        "ready": True,
        "readiness_detail": "ok",
    }

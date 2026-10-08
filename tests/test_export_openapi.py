"""Tests for the OpenAPI export and drift check (scripts/export_openapi.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def exporter() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "export_openapi", ROOT / "scripts" / "export_openapi.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_returns_an_openapi_document(exporter: ModuleType) -> None:
    schema = exporter._generate()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "CreatorIQX API"


def test_committed_document_is_in_sync(exporter: ModuleType) -> None:
    # This fails if someone changes a route without regenerating: the CI guard.
    assert exporter.check() is True


def test_check_detects_drift(
    exporter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "openapi.json"
    stale.write_text('{"openapi": "3.1.0", "stale": true}\n', encoding="utf-8")
    monkeypatch.setattr(exporter, "OUTPUT", stale)
    assert exporter.check() is False


def test_check_detects_missing_file(
    exporter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exporter, "OUTPUT", tmp_path / "does-not-exist.json")
    assert exporter.check() is False

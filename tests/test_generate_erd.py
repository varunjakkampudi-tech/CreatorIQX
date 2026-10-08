"""Tests for the data-model generator and drift check (scripts/generate_erd.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_erd", ROOT / "scripts" / "generate_erd.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_includes_every_registered_table(generator: ModuleType) -> None:
    rendered = generator._render()
    for table in ("audit_log", "usage_events", "outbox_events", "idempotency_keys", "memberships"):
        assert f"    {table} {{" in rendered


def test_render_lists_global_tables_without_workspace_id(generator: ModuleType) -> None:
    rendered = generator._render()
    assert "- `users`" in rendered
    assert "- `outbox_events`" in rendered


def test_render_marks_tenant_scoped_tables_in_the_ownership_table(generator: ModuleType) -> None:
    rendered = generator._render()
    assert "| `audit_log` | audit | yes |" in rendered
    assert "| `outbox_events` | jobs | no |" in rendered


def test_committed_document_is_in_sync(generator: ModuleType) -> None:
    # This fails if someone adds or changes a table without regenerating: the CI guard.
    assert generator.check() is True


def test_check_detects_drift(
    generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "DATA_MODEL.md"
    stale.write_text("# stale\n", encoding="utf-8")
    monkeypatch.setattr(generator, "OUTPUT", stale)
    assert generator.check() is False


def test_check_detects_missing_file(
    generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generator, "OUTPUT", tmp_path / "does-not-exist.md")
    assert generator.check() is False

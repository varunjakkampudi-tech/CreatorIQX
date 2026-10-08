"""Tests for the documentation deliverables check (scripts/check_docs.py)."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType


def _make_repo(root: Path, required: tuple[str, ...]) -> None:
    for rel in required:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# content\n", encoding="utf-8")


def test_complete_repo_has_no_missing_deliverables(check_docs: ModuleType, tmp_path: Path) -> None:
    _make_repo(tmp_path, check_docs.REQUIRED_FILES)
    assert check_docs.missing_deliverables(tmp_path) == []


def test_missing_and_empty_files_are_reported(check_docs: ModuleType, tmp_path: Path) -> None:
    _make_repo(tmp_path, check_docs.REQUIRED_FILES)
    (tmp_path / "docs" / "RUNBOOK.md").unlink()
    (tmp_path / "docs" / "TESTING.md").write_text("   \n", encoding="utf-8")
    assert check_docs.missing_deliverables(tmp_path) == ["docs/RUNBOOK.md", "docs/TESTING.md"]


def test_mermaid_blocks_are_extracted_per_file(check_docs: ModuleType, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "A.md").write_text(
        "text\n```mermaid\nflowchart LR\n  a --> b\n```\nmore\n```mermaid\npie\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("```python\nprint(1)\n```\n", encoding="utf-8")
    out = tmp_path / "out"
    assert check_docs.extract_mermaid(tmp_path, out) == 2
    names = sorted(p.name for p in out.iterdir())
    assert names == ["docs__A.md__0.mmd", "docs__A.md__1.mmd"]
    assert "a --> b" in (out / "docs__A.md__0.mmd").read_text(encoding="utf-8")


def test_real_repository_passes(check_docs: ModuleType) -> None:
    assert check_docs.missing_deliverables(check_docs.REPO_ROOT) == []

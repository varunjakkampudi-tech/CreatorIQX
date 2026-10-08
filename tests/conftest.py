"""Shared fixtures for repository-level tests (scripts and tooling)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str) -> ModuleType:
    """Import ``scripts/<name>.py`` as a module (scripts are not a package)."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def check_docs() -> ModuleType:
    return _load_script("check_docs")


@pytest.fixture(scope="session")
def check_coverage() -> ModuleType:
    return _load_script("check_coverage")


@pytest.fixture(scope="session")
def dev() -> ModuleType:
    return _load_script("dev")

"""Package-level checks for creatoriqx_api."""

from __future__ import annotations

import tomllib
from pathlib import Path

import creatoriqx_api

API_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_version_matches_pyproject() -> None:
    project = tomllib.loads((API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert creatoriqx_api.__version__ == project["project"]["version"]

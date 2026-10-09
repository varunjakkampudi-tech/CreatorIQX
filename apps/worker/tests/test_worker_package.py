"""Package-level checks for creatoriqx_worker."""

from __future__ import annotations

import tomllib
from pathlib import Path

import creatoriqx_worker

WORKER_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_version_matches_pyproject() -> None:
    project = tomllib.loads((WORKER_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert creatoriqx_worker.__version__ == project["project"]["version"]


def test_celery_app_is_importable_through_creatoriqx_api() -> None:
    """The worker starts by pointing Celery's CLI at creatoriqx-api's app, not its own."""
    from creatoriqx_api.modules.jobs.infrastructure.celery_app import celery_app

    assert celery_app.main == "creatoriqx"

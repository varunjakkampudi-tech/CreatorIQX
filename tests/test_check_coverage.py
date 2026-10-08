"""Tests for the domain/application coverage gate (scripts/check_coverage.py)."""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest


def _file(statements: int, covered: int) -> dict[str, dict[str, int]]:
    return {"summary": {"num_statements": statements, "covered_lines": covered}}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("apps/api/src/creatoriqx_api/modules/workspaces/domain/model.py", True),
        ("apps\\api\\src\\creatoriqx_api\\modules\\workspaces\\application\\svc.py", True),
        ("apps/api/src/creatoriqx_api/modules/workspaces/infrastructure/repo.py", False),
        ("apps/api/src/creatoriqx_api/main.py", False),
    ],
)
def test_is_core_detects_domain_and_application(
    check_coverage: ModuleType, path: str, expected: bool
) -> None:
    assert check_coverage.is_core(path) is expected


def test_no_core_files_means_gate_not_applicable(check_coverage: ModuleType) -> None:
    report = {"files": {"src/creatoriqx_api/main.py": _file(10, 2)}}
    assert check_coverage.core_coverage(report) == (None, 0)


def test_core_coverage_combines_only_core_files(check_coverage: ModuleType) -> None:
    report = {
        "files": {
            "m/domain/a.py": _file(10, 9),
            "m/application/b.py": _file(10, 8),
            "m/infrastructure/c.py": _file(100, 0),
        }
    }
    percent, count = check_coverage.core_coverage(report)
    assert count == 2
    assert percent == pytest.approx(85.0)


def test_report_without_files_section_is_rejected(check_coverage: ModuleType) -> None:
    with pytest.raises(ValueError, match="no 'files' section"):
        check_coverage.core_coverage({"totals": {}})


@pytest.mark.parametrize(("covered", "exit_code"), [(9, 0), (8, 1)])
def test_main_enforces_threshold(
    check_coverage: ModuleType, tmp_path: Path, covered: int, exit_code: int
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"files": {"m/domain/a.py": _file(10, covered)}}))
    assert check_coverage.main([str(report_path)]) == exit_code


def test_main_rejects_wrong_arguments(check_coverage: ModuleType) -> None:
    assert check_coverage.main([]) == 2

"""Tests for scripts/record_outcome.py (backlog outcome recorder)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROW = "| P0-042 | 0 | E5 | RLS | Desc | P0-041 | 2 h | Accept test | Pending | Test IDs |"


@pytest.fixture(scope="module")
def recorder() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "scripts" / "record_outcome.py"
    spec = importlib.util.spec_from_file_location("record_outcome", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_records_outcome_and_evidence(recorder: ModuleType) -> None:
    text = f"intro\n{ROW}\nend\n"
    result = recorder.record(text, "P0-042", "PASS", "Run 123 green")
    assert "| Accept test | **PASS** | Run 123 green |" in result
    assert result.startswith("intro\n")
    assert result.endswith("\nend\n")


@pytest.mark.parametrize(
    ("outcome", "evidence", "message"),
    [
        ("DONE", "x", "outcome must be one of"),
        ("PASS", "  ", "evidence is required"),
        ("PASS", "a | b", "must not contain"),
    ],
)
def test_rejects_invalid_input(
    recorder: ModuleType, outcome: str, evidence: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        recorder.record(ROW, "P0-042", outcome, evidence)


def test_unknown_ticket_is_rejected(recorder: ModuleType) -> None:
    with pytest.raises(ValueError, match="found 0"):
        recorder.record(ROW, "P0-999", "PASS", "x")


def test_real_backlog_has_one_row_per_known_ticket(recorder: ModuleType) -> None:
    text = recorder.BACKLOG.read_text(encoding="utf-8")
    for ticket in ("P0-011", "P0-013", "P0-100", "P0-110"):
        recorder.record(text, ticket, "PASS", "probe")

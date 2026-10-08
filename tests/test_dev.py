"""Tests for the developer task runner (scripts/dev.py)."""

from __future__ import annotations

from types import ModuleType

import pytest


def test_unknown_command_prints_usage(dev: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert dev.main(["no-such-command"]) == 2
    assert "Usage:" in capsys.readouterr().out


def test_missing_tool_is_reported_clearly(dev: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "REQUIRED_TOOLS", {"definitely-not-a-real-tool-ciq": (1, 0)})
    with pytest.raises(dev.TaskError, match="not installed or not on PATH"):
        dev.doctor()


def test_too_old_tool_fails_doctor(dev: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "REQUIRED_TOOLS", {"uv": (999, 0)})
    with pytest.raises(dev.TaskError, match=r"older than 999\.0"):
        dev.doctor()


def test_task_errors_become_exit_code_1(
    dev: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing() -> None:
        raise dev.TaskError("boom")

    monkeypatch.setitem(dev.COMMANDS, "fail", failing)
    assert dev.main(["fail"]) == 1
    assert "ERROR: boom" in capsys.readouterr().err

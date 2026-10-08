"""Enforce the layer coverage gate from spec section 12.

The global floor (70%) is enforced by coverage.py's ``fail_under``. This script
adds the stricter rule: code in ``domain`` and ``application`` packages must be
covered at 85% or more, measured over those files together.

Usage:
    python scripts/check_coverage.py coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CORE_LAYERS = ("domain", "application")
CORE_THRESHOLD = 85.0


def is_core(file_path: str) -> bool:
    """True if the file sits inside a domain or application package."""
    parts = Path(file_path.replace("\\", "/")).parts
    return any(layer in parts for layer in CORE_LAYERS)


def core_coverage(report: dict[str, object]) -> tuple[float | None, int]:
    """Return (percent covered, file count) for domain and application files.

    Percent is None when no such files exist yet.
    """
    files = report.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage report has no 'files' section")
    covered = total = count = 0
    for path, data in files.items():
        if not is_core(path):
            continue
        summary = data["summary"]
        covered += int(summary["covered_lines"]) + int(summary.get("covered_branches", 0))
        total += int(summary["num_statements"]) + int(summary.get("num_branches", 0))
        count += 1
    if count == 0:
        return None, 0
    return (100.0 if total == 0 else 100.0 * covered / total), count


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    percent, count = core_coverage(report)
    if percent is None:
        print("Layer coverage: no domain or application code yet; gate not applicable.")
        return 0
    print(
        f"Layer coverage: {percent:.1f}% across {count} domain/application file(s) "
        f"(need >= {CORE_THRESHOLD:.0f}%)."
    )
    return 0 if percent >= CORE_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Check documentation deliverables required by spec section 16.

Usage:
    python scripts/check_docs.py [--extract-mermaid OUT_DIR]

Exits non-zero if any required file is missing or empty. With
``--extract-mermaid`` it also writes every fenced ```mermaid block found in
Markdown files under ``docs/`` (and the repo root) to OUT_DIR as numbered
``.mmd`` files, so CI can render each one with the Mermaid CLI.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Spec section 16 deliverables, mapped to their paths in this repository.
REQUIRED_FILES: tuple[str, ...] = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs/ARCHITECTURE.md",
    "docs/DATA_MODEL.md",
    "docs/SECURITY.md",
    "docs/RUNBOOK.md",
    "docs/DEPLOYMENT.md",
    "docs/TESTING.md",
    "docs/PROMPTS.md",
    "docs/UX_GUIDELINES.md",
    "docs/YOUTUBE_CAPABILITIES.md",
    "docs/OPEN_QUESTIONS.md",
    "docs/PROGRESS.md",
    "docs/API.md",
    "docs/adr/README.md",
)

MERMAID_BLOCK = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def missing_deliverables(root: Path) -> list[str]:
    """Return required paths that are absent or empty."""
    problems: list[str] = []
    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            problems.append(rel)
    return problems


def extract_mermaid(root: Path, out_dir: Path) -> int:
    """Write each Mermaid block to OUT_DIR; return how many were written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(root.glob("*.md")) + sorted((root / "docs").rglob("*.md"))
    count = 0
    for source in sources:
        for index, match in enumerate(MERMAID_BLOCK.finditer(source.read_text(encoding="utf-8"))):
            name = f"{source.relative_to(root).as_posix().replace('/', '__')}__{index}.mmd"
            (out_dir / name).write_text(match.group(1), encoding="utf-8")
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-mermaid", type=Path, metavar="OUT_DIR")
    args = parser.parse_args(argv)

    problems = missing_deliverables(REPO_ROOT)
    for rel in problems:
        print(f"MISSING or empty deliverable: {rel}", file=sys.stderr)

    if args.extract_mermaid is not None:
        written = extract_mermaid(REPO_ROOT, args.extract_mermaid)
        print(f"Extracted {written} Mermaid block(s) to {args.extract_mermaid}")

    if problems:
        return 1
    print(f"All {len(REQUIRED_FILES)} documentation deliverables present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Record a ticket outcome in docs/backlog/PHASE_0.md, matching the row by ticket ID.

Usage:
    python scripts/record_outcome.py P0-011 PASS "Commit abc1234; evidence ..."

Outcome must be PASS, BLOCKED or FAIL (spec section 0, rule 8). Evidence is
required: a PASS without evidence is invalid.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKLOG = Path(__file__).resolve().parent.parent / "docs" / "backlog" / "PHASE_0.md"
OUTCOMES = ("PASS", "BLOCKED", "FAIL")


def record(text: str, ticket: str, outcome: str, evidence: str) -> str:
    """Return backlog text with the ticket row's last two cells replaced."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if not evidence.strip():
        raise ValueError("evidence is required")
    if "|" in evidence:
        raise ValueError("evidence must not contain '|' (it would break the table)")
    row = re.compile(
        rf"^(\| {re.escape(ticket)} \|(?:[^|\n]*\|){{7}}) [^|\n]* \| [^|\n]* \|$", re.M
    )
    new_text, count = row.subn(lambda m: f"{m.group(1)} **{outcome}** | {evidence} |", text)
    if count != 1:
        raise ValueError(f"expected exactly one row for {ticket}, found {count}")
    return new_text


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    ticket, outcome, evidence = argv
    try:
        updated = record(BACKLOG.read_text(encoding="utf-8"), ticket, outcome, evidence)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    BACKLOG.write_text(updated, encoding="utf-8", newline="\n")
    print(f"{ticket}: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

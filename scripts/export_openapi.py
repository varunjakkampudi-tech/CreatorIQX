"""Export the OpenAPI document; the committed copy is the API's source of truth.

    python scripts/export_openapi.py            # write packages/api-client/openapi.json
    python scripts/export_openapi.py --check    # fail if the committed copy is stale

The TypeScript client is generated from this file (P0-081), so CI runs --check
to guarantee the committed document always matches the code.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "packages" / "api-client" / "openapi.json"


def _generate() -> dict[str, Any]:
    """Build the app with placeholder settings and return its OpenAPI schema."""
    # Dependency-free placeholders: schema generation never connects anywhere.
    os.environ.setdefault("DATABASE_APP_URL", "postgresql+asyncpg://x:x@localhost:1/x")
    os.environ.setdefault("REDIS_URL", "redis://localhost:1/0")
    os.environ.setdefault("SESSION_SECRET", "openapi-export-placeholder-secret-32-chars")
    from creatoriqx_api.main import create_app  # imported late so env is set first

    schema: dict[str, Any] = create_app(checks=[]).openapi()
    return schema


def _serialize(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(_serialize(_generate()), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")


def check() -> bool:
    """Return True when the committed document matches freshly generated output."""
    expected = _serialize(_generate())
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if current == expected:
        print("OpenAPI document is up to date.")
        return True
    diff = difflib.unified_diff(
        current.splitlines(), expected.splitlines(), "committed", "generated", lineterm=""
    )
    print("OpenAPI document is STALE. Run: python scripts/export_openapi.py")
    print("\n".join(list(diff)[:40]))
    return False


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        return 0 if check() else 1
    if not argv:
        write()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

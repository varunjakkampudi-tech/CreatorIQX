"""CreatorIQX developer task runner (cross-platform replacement for a Makefile).

Usage:
    python scripts/dev.py <command>      (Windows: py scripts/dev.py <command>)

Commands:
    doctor       Check that required tools are installed at supported versions
    setup        doctor + create .env from .env.example if missing + install all dependencies
    check-docs   Verify spec section 16 documentation deliverables exist
    format       Format JS/JSON/Markdown/YAML with Prettier

Standard library only, so it runs before any dependency is installed.
Further commands (lint, test, up, down, migrate) are added by the tickets
that introduce the tools behind them; nothing here is a placeholder.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"

# Minimum supported versions (major, minor).
REQUIRED_TOOLS: dict[str, tuple[int, int]] = {
    "uv": (0, 12),
    "node": (22, 12),
    "pnpm": (12, 0),
    "docker": (27, 0),
}


class TaskError(RuntimeError):
    """A task failed with a message the developer can act on."""


def _resolve(tool: str) -> str:
    """Return the executable path for a tool, honoring Windows .cmd shims."""
    found = shutil.which(tool)
    if found is None:
        raise TaskError(f"'{tool}' is not installed or not on PATH. See README.md prerequisites.")
    return found


def run(*args: str) -> None:
    """Run a command from the repo root, streaming output; raise on failure."""
    executable = _resolve(args[0])
    print(f"> {' '.join(args)}", flush=True)
    completed = subprocess.run([executable, *args[1:]], cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise TaskError(f"'{' '.join(args)}' failed with exit code {completed.returncode}")


def _version_of(tool: str) -> tuple[int, int] | None:
    """Parse 'major.minor' from '<tool> --version'; None if unparseable."""
    output = subprocess.run(
        [_resolve(tool), "--version"], capture_output=True, text=True, check=False
    ).stdout
    match = re.search(r"(\d+)\.(\d+)", output)
    return (int(match.group(1)), int(match.group(2))) if match else None


def doctor() -> None:
    """Verify every required tool is present at a supported version."""
    problems: list[str] = []
    for tool, minimum in REQUIRED_TOOLS.items():
        try:
            found = _version_of(tool)
        except TaskError as exc:
            problems.append(str(exc))
            continue
        status = "ok" if found is not None and found >= minimum else "TOO OLD"
        shown = ".".join(map(str, found)) if found else "unknown"
        print(f"  {tool:<7} {shown:<8} (need >= {minimum[0]}.{minimum[1]})  {status}")
        if status != "ok":
            problems.append(f"{tool} {shown} is older than {minimum[0]}.{minimum[1]}")
    if problems:
        raise TaskError("Toolchain check failed:\n  " + "\n  ".join(problems))
    print("Toolchain OK.")


def setup() -> None:
    """One-command setup: toolchain check, .env, Python and JS dependencies."""
    doctor()
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if env_file.exists():
        print(".env already exists; left untouched.")
    else:
        shutil.copyfile(example, env_file)
        print("Created .env from .env.example. Fill in the empty secrets before running the app.")
    run("uv", "sync", "--all-packages", "--locked")
    run("pnpm", "install", "--frozen-lockfile")
    print("Setup complete.")


def check_docs() -> None:
    """Run the documentation deliverables check."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_docs.py")], cwd=ROOT, check=False
    )
    if completed.returncode != 0:
        raise TaskError("Documentation check failed.")


def format_code() -> None:
    """Format non-Python files with Prettier (Python formatting arrives with P0-011)."""
    run("pnpm", "run", "format")


COMMANDS: dict[str, Callable[[], None]] = {
    "doctor": doctor,
    "setup": setup,
    "check-docs": check_docs,
    "format": format_code,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    try:
        COMMANDS[argv[0]]()
    except TaskError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

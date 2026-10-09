"""CreatorIQX developer task runner (cross-platform replacement for a Makefile).

Usage:
    python scripts/dev.py <command>      (Windows: py scripts/dev.py <command>)

Commands:
    doctor       Check that required tools are installed at supported versions
    setup        doctor + create .env if missing + install dependencies + install git hooks
    check-docs   Verify spec section 16 documentation deliverables exist
    format       Format Python (Ruff) and JS/JSON/YAML (Prettier)
    lint         Ruff lint and format check, mypy strict, import-linter contracts
    test         pytest with coverage: 70% overall, 85% domain and application
    up           Start local services (PostgreSQL, Redis) and wait until healthy
    down         Stop local services (data volumes are kept)
    api          Run the API on http://127.0.0.1:8000 with auto-reload (needs `up`)
    openapi      Regenerate packages/api-client/openapi.json from the code
    erd          Regenerate docs/DATA_MODEL.md from the SQLAlchemy metadata
    migrate      Apply database migrations (owner role) to the configured DB
    up-full      One-command setup (P0-022): postgres, redis, api, worker, web as
                 containers (profile "full"), then `migrate` and `seed`
    down-full    Stop the full containerized stack (data volumes are kept)
    seed         Create the second demo workspace used for manual cross-tenant checks

Standard library only, so it runs before any dependency is installed.
Further commands (migrate and app services) are added by the tickets
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
    run("uv", "run", "pre-commit", "install")
    print("Setup complete.")


def check_docs() -> None:
    """Run the documentation deliverables check."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_docs.py")], cwd=ROOT, check=False
    )
    if completed.returncode != 0:
        raise TaskError("Documentation check failed.")


def format_code() -> None:
    """Format Python with Ruff and everything else Prettier handles."""
    run("uv", "run", "ruff", "check", "--fix", ".")
    run("uv", "run", "ruff", "format", ".")
    run("pnpm", "run", "format")


def _load_env() -> None:
    """Load KEY=VALUE lines from .env into the environment (does not override)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        raise TaskError(".env is missing. Run 'setup' first.")
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def migrate() -> None:
    """Apply migrations to the configured database using the owner role."""
    _load_env()
    run("uv", "run", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head")


def openapi() -> None:
    """Regenerate the committed OpenAPI document from the code."""
    run("uv", "run", "python", "scripts/export_openapi.py")


def erd() -> None:
    """Regenerate the committed data-model document from the SQLAlchemy metadata."""
    run("uv", "run", "python", "scripts/generate_erd.py")


def lint() -> None:
    """Every static check from spec section 17 Code quality and Architecture."""
    run("uv", "run", "ruff", "check", ".")
    run("uv", "run", "ruff", "format", "--check", ".")
    run("uv", "run", "mypy")
    run("uv", "run", "lint-imports")
    run("uv", "run", "python", "scripts/export_openapi.py", "--check")
    run("uv", "run", "python", "scripts/generate_erd.py", "--check")
    run("pnpm", "run", "format:check")


def test() -> None:
    """Run the test suite with both coverage gates."""
    report = ROOT / "coverage.json"
    run("uv", "run", "pytest", "--cov", "--cov-report=term-missing", f"--cov-report=json:{report}")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_coverage.py"), str(report)],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise TaskError("Domain and application coverage is below 85%.")


COMPOSE_FILE = ROOT / "infra" / "compose" / "docker-compose.yml"


def compose(*args: str) -> None:
    """Run docker compose with the repo's compose file and root .env."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        raise TaskError(".env is missing. Run 'setup' first (it creates one from .env.example).")
    run("docker", "compose", "--env-file", str(env_file), "-f", str(COMPOSE_FILE), *args)


def up() -> None:
    """Start local services and block until every health check passes."""
    compose("up", "--detach", "--wait", "--wait-timeout", "120")
    compose("ps")


def down() -> None:
    """Stop local services; named volumes (database data) are preserved."""
    compose("down")


def up_full() -> None:
    """One-command setup (P0-022): the full containerized stack, migrated and seeded.

    mcp-server is intentionally not part of this: it is P0-070's job, deferred
    to the start of Phase 1A (same scope note as P0-021's app images).
    """
    compose("--profile", "full", "up", "--detach", "--build", "--wait", "--wait-timeout", "180")
    compose("--profile", "full", "ps")
    migrate()
    seed()


def down_full() -> None:
    """Stop the full containerized stack; named volumes (database data) are preserved."""
    compose("--profile", "full", "down")


def seed() -> None:
    """Create the second demo workspace used for manual cross-tenant checks."""
    run("uv", "run", "python", str(ROOT / "scripts" / "seed_demo_workspace.py"))


def api() -> None:
    """Run the API locally with reload; settings come from the root .env."""
    if not (ROOT / ".env").exists():
        raise TaskError(".env is missing. Run 'setup' first.")
    run(
        "uv",
        "run",
        "uvicorn",
        "creatoriqx_api.main:create_app",
        "--factory",
        "--env-file",
        str(ROOT / ".env"),
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
        "--reload-dir",
        str(ROOT / "apps" / "api" / "src"),
    )


COMMANDS: dict[str, Callable[[], None]] = {
    "doctor": doctor,
    "setup": setup,
    "check-docs": check_docs,
    "format": format_code,
    "lint": lint,
    "test": test,
    "up": up,
    "down": down,
    "up-full": up_full,
    "down-full": down_full,
    "seed": seed,
    "api": api,
    "openapi": openapi,
    "erd": erd,
    "migrate": migrate,
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

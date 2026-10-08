"""Structured JSON logging with secret redaction (spec §10 Logging).

``configure_logging`` is called once at startup. Every log line is JSON and
carries the correlation id bound by the request middleware. A redaction
processor masks sensitive values as a backstop, so a stray log of a header or
token never emits the real value.
"""

from __future__ import annotations

import logging
import re
from typing import cast

import structlog
from structlog.typing import EventDict, WrappedLogger

from creatoriqx_api.settings import Settings

REDACTED = "[redacted]"

# Keys whose values must never be logged, matched case-insensitively anywhere
# in the key (so "authorization", "x-api-key", "refresh_token" all match).
_SENSITIVE_KEY = re.compile(
    r"authorization|cookie|token|secret|password|passwd|api[_-]?key|credential",
    re.IGNORECASE,
)
# Bearer tokens that slip into a free-text message are masked by value, too.
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)


def _redact(_logger: WrappedLogger, _name: str, event: EventDict) -> EventDict:
    """structlog processor: mask sensitive keys and bearer tokens."""
    for key, value in list(event.items()):
        if _SENSITIVE_KEY.search(key):
            event[key] = REDACTED
        elif isinstance(value, str):
            event[key] = _BEARER.sub("Bearer " + REDACTED, value)
    return event


def configure_logging(settings: Settings) -> None:
    """Install structlog as the one logging path. Idempotent."""
    level = logging.getLevelName(settings.log_level)
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,  # keep structlog.testing.capture_logs reliable
    )


def get_logger(*args: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(*args))

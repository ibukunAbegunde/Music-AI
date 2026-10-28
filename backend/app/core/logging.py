"""Structured logging setup."""

from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logger for console output; return app logger."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
    root.setLevel(level.upper())
    return logging.getLogger("music_ai")


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured-ish one-line event (job/project ids redaction-safe)."""
    parts = " ".join(f"{k}={v!r}" for k, v in fields.items())
    logger.info("%s %s", event, parts)

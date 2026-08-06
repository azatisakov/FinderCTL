from __future__ import annotations

import logging
import sys

from .config import LOG_DIR

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.WARNING) -> None:
    """Configure the root ``finderctl`` logger.

    All log records are emitted to **stderr** so stdout remains clean
    for CLI result output.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    logger = logging.getLogger("finderctl")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``finderctl`` namespace."""
    return logging.getLogger(f"finderctl.{name}")

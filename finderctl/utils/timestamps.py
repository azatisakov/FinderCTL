from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def format_backup_timestamp(dt: datetime) -> str:
    """Format a datetime as a backup filename timestamp.

    >>> format_backup_timestamp(datetime(2026, 8, 7, 1, 17, 31))
    '2026-08-07_01-17-31'
    """
    return dt.strftime("%Y-%m-%d_%H-%M-%S")


def parse_backup_timestamp(name: str) -> datetime | None:
    """Parse a timestamp from a backup filename.

    Returns ``None`` if the filename does not start with a valid
    timestamp prefix.
    """
    stem = Path(name).stem
    prefix = stem.split("_")[0] if "_" in stem else stem
    try:
        return datetime.strptime(prefix, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)

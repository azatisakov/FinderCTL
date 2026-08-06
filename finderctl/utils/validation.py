from __future__ import annotations

import re
from pathlib import Path

from ..config import BACKUP_LABEL_PATTERN

_LABEL_RE = re.compile(BACKUP_LABEL_PATTERN)


def validate_backup_label(label: str | None) -> str | None:
    """Validate a backup label; return it or raise ``ValueError``."""
    if label is None:
        return None
    if not _LABEL_RE.match(label):
        raise ValueError(
            f"Invalid backup label {label!r}. "
            "Use only letters, numbers, hyphens, and underscores (max 64)."
        )
    return label


def validate_folder_path(path: str) -> Path:
    """Validate that a path is a reasonable folder reference."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def sanitize_scope_folder(value: str) -> str:
    """Extract and validate a ``folder:<key>`` scope argument."""
    if not value.startswith("folder:"):
        raise ValueError(f"Expected 'folder:<key>', got {value!r}")
    key = value[len("folder:") :]
    if not re.match(r"^[A-Za-z0-9_\-]+$", key):
        raise ValueError(f"Invalid folder scope key: {key!r}")
    return key

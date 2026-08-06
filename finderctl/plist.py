from __future__ import annotations

from pathlib import Path
from typing import Any

from .infrastructure.plist_io import PlistReader, PlistWriter
from .models import SectionLocation
from .services.discovery import PlistSectionWalker


def read_plist(path: Path) -> dict[str, Any]:
    """Read a plist file and return its contents as a dict."""
    return PlistReader(path).read()


def write_plist(path: Path, data: dict[str, Any]) -> None:
    """Atomically write a dict as a binary plist to the given path."""
    PlistWriter(path).write_atomic(data)


def discover_sections(data: dict[str, Any]) -> list[SectionLocation]:
    """Recursively discover all view-settings sections in a plist tree."""
    return PlistSectionWalker().discover(data)

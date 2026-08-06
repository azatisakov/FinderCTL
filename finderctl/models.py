from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ViewSettings:
    """A single discovered view-settings section in the plist."""

    key_name: str
    properties: dict[str, Any]
    container: str | None


@dataclass(frozen=True, slots=True)
class FolderView:
    """All view-settings sections for one plist container."""

    folder_key: str
    settings: list[ViewSettings] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SectionLocation:
    """Address of a discovered plist section."""

    key_path: tuple[str, ...]
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Change:
    """A single field mutation for diff/reporting."""

    scope: str
    field: str
    before: Any
    after: Any
    key_path: tuple[str, ...]


class ApplyScope(Enum):
    """Scope for an `apply` operation."""

    DEFAULT = "default"
    ALL = "all"
    STANDARD = "standard"
    DESKTOP = "desktop"
    ICLOUD = "icloud"
    TRASH = "trash"
    PACKAGE = "package"
    SEARCH_RECENTS = "search-recents"
    MEETING_ROOM = "meeting-room"

    @classmethod
    def from_str(cls, value: str) -> ApplyScope:
        """Parse a scope string, returning a specific or DEFAULT scope."""
        if value == "all":
            return cls.ALL
        if value == "default":
            return cls.DEFAULT
        if value == "standard":
            return cls.STANDARD
        if value == "desktop":
            return cls.DESKTOP
        if value == "icloud":
            return cls.ICLOUD
        if value == "trash":
            return cls.TRASH
        if value == "package":
            return cls.PACKAGE
        if value == "search-recents":
            return cls.SEARCH_RECENTS
        if value == "meeting-room":
            return cls.MEETING_ROOM
        if value.startswith("folder:"):
            return cls.DEFAULT
        raise ValueError(f"Unknown scope: {value}")


@dataclass(frozen=True, slots=True)
class BackupRecord:
    """Metadata for a single backup file."""

    path: Path
    timestamp: datetime
    size_bytes: int
    sha256: str
    is_valid: bool
    label: str | None


@dataclass(frozen=True, slots=True)
class SystemState:
    """Snapshot of system + Finder + backup state."""

    finder_plist_path: Path
    found: bool
    readable: bool
    writable: bool
    macos_version: str
    finder_version: str | None
    plist_modified_at: datetime | None
    sections_discovered: int
    backup_count: int
    latest_backup: BackupRecord | None


class DiagnosisStatus(Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    FIXABLE = "fixable"


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """A single diagnostic check result."""

    name: str
    status: DiagnosisStatus
    detail: str | None = None
    repairable: bool = False


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Outcome of validating a settings change."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DSSettingsSnapshot:
    """A captured .DS_Store view-settings blob before patching."""

    folder: Path
    backup_path: Path
    sections_patched: int

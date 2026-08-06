from __future__ import annotations


class FinderCtlError(Exception):
    """Base exception for all FinderCTL errors."""


class ConfigurationError(FinderCtlError):
    """Raised when configuration is invalid or unsupported."""


class PlistError(FinderCtlError):
    """Base for plist I/O errors."""


class PlistNotFoundError(PlistError):
    """Raised when the Finder plist does not exist."""


class PlistPermissionError(PlistError):
    """Raised when the Finder plist is not readable/writable."""


class PlistParseError(PlistError):
    """Raised when the plist is corrupt or malformed."""


class BackupError(FinderCtlError):
    """Raised when backup creation, verification, or management fails."""


class RestoreError(FinderCtlError):
    """Raised when restore from a backup fails."""


class SettingsError(FinderCtlError):
    """Base for settings read/write errors."""


class ApplyError(SettingsError):
    """Raised when applying settings fails."""


class DiscoveryError(SettingsError):
    """Raised when plist section discovery encounters an unexpected structure."""


class FinderProcessError(FinderCtlError):
    """Raised when Finder process inspection or restart fails."""


class ValidationError(FinderCtlError):
    """Raised when user-supplied input fails validation."""


class CleanError(FinderCtlError):
    """Raised when backup cleanup fails."""


class DoctorError(FinderCtlError):
    """Raised when diagnostics detect a non-fixable issue."""


class DSSettingsError(FinderCtlError):
    """Base for .DS_Store view-settings errors."""


class DSStoreCorruptionError(DSSettingsError):
    """Raised when a .DS_Store B-tree parse or write fails."""


class DSStoreNotFoundError(DSSettingsError):
    """Raised when a .DS_Store file does not exist."""


class DSRevertibleError(DSSettingsError):
    """Raised when a .DS_Store patch fails but the backup is intact."""

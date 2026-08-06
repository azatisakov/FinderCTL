from __future__ import annotations

import pytest

from finderctl.exceptions import (
    ApplyError,
    BackupError,
    CleanError,
    DiscoveryError,
    DoctorError,
    DSRevertibleError,
    DSSettingsError,
    DSStoreCorruptionError,
    DSStoreNotFoundError,
    FinderCtlError,
    FinderProcessError,
    PlistError,
    PlistNotFoundError,
    PlistParseError,
    PlistPermissionError,
    RestoreError,
    SettingsError,
    ValidationError,
)


def test_all_exceptions_inherit_from_fider_ctl_error() -> None:
    """Every custom exception must inherit from FinderCtlError."""
    exceptions = [
        ApplyError,
        BackupError,
        CleanError,
        DSRevertibleError,
        DSStoreCorruptionError,
        DSStoreNotFoundError,
        DSSettingsError,
        DiscoveryError,
        DoctorError,
        FinderProcessError,
        PlistError,
        PlistNotFoundError,
        PlistParseError,
        PlistPermissionError,
        RestoreError,
        SettingsError,
        ValidationError,
    ]
    for exc_cls in exceptions:
        assert issubclass(exc_cls, FinderCtlError), (
            f"{exc_cls.__name__} does not inherit from FinderCtlError"
        )


def test_all_exceptions_can_be_raised() -> None:
    """All exceptions should be raisable with a message."""
    instances = [
        FinderCtlError("base"),
        ApplyError("apply"),
        BackupError("backup"),
        DSRevertibleError("revertible"),
        DSStoreCorruptionError("corruption"),
        DSStoreNotFoundError("not found"),
        DSSettingsError("ds"),
        DiscoveryError("discovery"),
        PlistNotFoundError("plist nf"),
        PlistParseError("plist parse"),
        ValidationError("validation"),
    ]
    for inst in instances:
        with pytest.raises(FinderCtlError):
            raise inst


def test_dsstore_errors_inherited_from_dssettings() -> None:
    """DS_Store-specific exceptions inherit from DSSettingsError."""
    assert issubclass(DSStoreCorruptionError, DSSettingsError)
    assert issubclass(DSStoreNotFoundError, DSSettingsError)
    assert issubclass(DSRevertibleError, DSSettingsError)


def test_plist_errors_inherited_from_plist_error() -> None:
    """Plist-specific exceptions inherit from PlistError."""
    assert issubclass(PlistNotFoundError, PlistError)
    assert issubclass(PlistParseError, PlistError)
    assert issubclass(PlistPermissionError, PlistError)


def test_settings_errors_inherited_from_settings_error() -> None:
    """Settings errors inherit from SettingsError."""
    assert issubclass(ApplyError, SettingsError)


def test_exceptions_preserve_message() -> None:
    """Exception messages are preserved."""
    exc = BackupError("custom message")
    assert "custom message" in str(exc)

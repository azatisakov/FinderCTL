from __future__ import annotations

import pytest

from finderctl.models import (
    ApplyScope,
    BackupRecord,
    Change,
    Diagnosis,
    DiagnosisStatus,
    DSSettingsSnapshot,
    FolderView,
    SectionLocation,
    SystemState,
    ValidationReport,
    ViewSettings,
)


def test_apply_scope_from_str() -> None:
    assert ApplyScope.from_str("all") == ApplyScope.ALL
    assert ApplyScope.from_str("default") == ApplyScope.DEFAULT
    assert ApplyScope.from_str("standard") == ApplyScope.STANDARD
    assert ApplyScope.from_str("desktop") == ApplyScope.DESKTOP
    assert ApplyScope.from_str("icloud") == ApplyScope.ICLOUD
    assert ApplyScope.from_str("trash") == ApplyScope.TRASH
    assert ApplyScope.from_str("package") == ApplyScope.PACKAGE
    assert ApplyScope.from_str("search-recents") == ApplyScope.SEARCH_RECENTS
    assert ApplyScope.from_str("meeting-room") == ApplyScope.MEETING_ROOM


def test_apply_scope_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown scope"):
        ApplyScope.from_str("invalid_scope")


def test_view_settings_is_frozen() -> None:
    vs = ViewSettings(key_name="test", properties={"a": 1}, container="root")
    with pytest.raises(AttributeError):
        vs.key_name = "other"  # type: ignore[misc]


def test_folder_view_is_frozen() -> None:
    fv = FolderView(folder_key="test", settings=[])
    with pytest.raises(AttributeError):
        fv.folder_key = "other"  # type: ignore[misc]


def test_section_location_is_frozen() -> None:
    loc = SectionLocation(key_path=("a", "b"), data={"x": 1})
    with pytest.raises(AttributeError):
        loc.key_path = ("c",)  # type: ignore[misc]


def test_change_is_immutable() -> None:
    change = Change(
        scope="test",
        field="sortColumn",
        before="name",
        after="dateModified",
        key_path=("test",),
    )
    assert change.scope == "test"
    assert change.field == "sortColumn"
    assert change.before == "name"
    assert change.after == "dateModified"


def test_backup_record_fields() -> None:
    import datetime
    from pathlib import Path

    record = BackupRecord(
        path=Path("/tmp/test.plist"),
        timestamp=datetime.datetime.now(),
        size_bytes=1024,
        sha256="abc123",
        is_valid=True,
        label="test",
    )
    assert record.path == Path("/tmp/test.plist")
    assert record.size_bytes == 1024
    assert record.is_valid is True
    assert record.label == "test"


def test_diagnosis_status_enum() -> None:
    assert DiagnosisStatus.OK.value == "ok"
    assert DiagnosisStatus.WARN.value == "warn"
    assert DiagnosisStatus.ERROR.value == "error"
    assert DiagnosisStatus.FIXABLE.value == "fixable"


def test_diagnosis_is_frozen() -> None:
    d = Diagnosis(name="test", status=DiagnosisStatus.OK, detail="ok")
    assert d.status == DiagnosisStatus.OK
    with pytest.raises(AttributeError):
        d.status = DiagnosisStatus.ERROR  # type: ignore[misc]


def test_validation_report() -> None:
    report = ValidationReport(
        is_valid=False,
        errors=["error1"],
        warnings=["warn1"],
    )
    assert report.is_valid is False
    assert "error1" in report.errors
    assert "warn1" in report.warnings


def test_system_state_fields() -> None:
    import datetime
    from pathlib import Path

    state = SystemState(
        finder_plist_path=Path("/test.plist"),
        found=True,
        readable=True,
        writable=True,
        macos_version="26.6",
        finder_version="26.4",
        plist_modified_at=datetime.datetime.now(),
        sections_discovered=20,
        backup_count=5,
        latest_backup=None,
    )
    assert state.found is True
    assert state.sections_discovered == 20
    assert state.backup_count == 5
    assert state.latest_backup is None


def test_dssettings_snapshot() -> None:
    from pathlib import Path

    snap = DSSettingsSnapshot(
        folder=Path("/test"),
        backup_path=Path("/test/.DS_Store.bak"),
        sections_patched=3,
    )
    assert snap.sections_patched == 3

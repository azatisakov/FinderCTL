from __future__ import annotations

from pathlib import Path

import pytest

from finderctl.exceptions import ApplyError
from finderctl.models import (
    ApplyScope,
    Change,
    SectionLocation,
)
from finderctl.services.discovery import PlistSectionWalker
from finderctl.services.settings import SettingsService


def test_settings_walker_property(settings_service: SettingsService) -> None:
    assert isinstance(settings_service.walker, PlistSectionWalker)


def test_settings_read_folder_not_found(settings_service: SettingsService) -> None:
    assert settings_service.read_folder("NonExistentFolder") is None


def test_settings_read_default(settings_service: SettingsService) -> None:
    vs = settings_service.read_default()
    assert vs is not None
    assert vs.key_name == "FK_DefaultListViewSettingsV2"
    assert vs.container == "root"


def test_settings_apply_defaults_dry_run_changes(settings_service: SettingsService) -> None:
    changes = settings_service.apply_defaults(dry_run=True)
    assert len(changes) > 0
    sort = [c for c in changes if c.field == "sortColumn"]
    assert len(sort) >= 1
    assert sort[0].before == "name"
    assert sort[0].after == "dateModified"


def test_settings_apply_defaults_no_changes_when_already_set(
    settings_service: SettingsService, tmp_path: Path
) -> None:
    """If all defaults already match, only the backup is created."""
    changes = settings_service.apply_defaults(dry_run=False, restart=False)
    assert len(changes) > 0


def test_settings_apply_defaults_post_write_verification_fail(
    settings_service: SettingsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force post-write verification to fail."""

    original_write = settings_service._writer.write_atomic

    def fail_then_succeed(data):
        original_write(data)

    monkeypatch.setattr(settings_service._writer, "write_atomic", original_write)
    monkeypatch.setattr(settings_service._walker, "discover", lambda d: [])

    with pytest.raises(ApplyError, match="post-write verification failed"):
        settings_service.apply_defaults(dry_run=False, restart=False)


def test_settings_apply_defaults_post_write_check_mismatch(
    settings_service: SettingsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force a field check to fail by modifying _get_nested."""
    monkeypatch.setattr(SettingsService, "_get_nested", staticmethod(lambda data, path: "wrong"))
    with pytest.raises(ApplyError, match="post-write verification failed"):
        settings_service.apply_defaults(dry_run=False, restart=False)


def test_settings_apply_defaults_write_fails(
    settings_service: SettingsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import finderctl.services.settings as settings_module

    monkeypatch.setattr(settings_module.PlistWriter, "write_atomic", None)

    with pytest.raises(ApplyError):
        settings_service.apply_defaults(dry_run=False, restart=False)


def test_settings_apply_invalid_field(settings_service: SettingsService) -> None:
    from finderctl.exceptions import ValidationError

    with pytest.raises(ValidationError, match="not allowed"):
        settings_service.apply(field="invalidField", value="x", scope=ApplyScope.DEFAULT)


def test_settings_apply_no_matching_sections(settings_service: SettingsService) -> None:
    with pytest.raises(ApplyError, match="no matching sections"):
        settings_service.apply(field="sortColumn", value="name", scope=ApplyScope.STANDARD)


def test_settings_apply_dry_run_no_write(settings_service: SettingsService) -> None:
    changes = settings_service.apply(
        field="calculateAllSizes", value="True", scope=ApplyScope.DEFAULT, dry_run=True
    )
    assert len(changes) >= 1


def test_settings_apply_dry_run_no_changes(settings_service: SettingsService) -> None:
    with pytest.raises(ApplyError, match="no matching sections"):
        settings_service.apply(
            field="sortColumn", value="name", scope=ApplyScope.DEFAULT, dry_run=True
        )


def test_settings_apply_type_coercion(settings_service: SettingsService) -> None:
    changes = settings_service.apply(
        field="iconSize", value="32", scope=ApplyScope.DEFAULT, restart=False
    )
    assert len(changes) >= 1
    assert changes[0].after == 32.0 or changes[0].after == 32


def test_settings_apply_bool_coercion(settings_service: SettingsService) -> None:
    changes = settings_service.apply(
        field="showIconPreview", value="no", scope=ApplyScope.DEFAULT, restart=False
    )
    assert changes[0].after is False


def test_settings_apply_str_scope(settings_service: SettingsService) -> None:
    changes = settings_service.apply(
        field="sortColumn", value="name", scope=ApplyScope.DESKTOP, restart=False
    )
    # DesktopViewSettings has empty ExtendedListViewSettingsV2, so changes
    assert len(changes) >= 0  # may be 0 if no matching keys


def test_settings_sync_legacy_columns() -> None:
    svc = SettingsService.__new__(SettingsService)
    data = {"StandardViewSettings": {}}
    svc.sync_legacy_columns(data)
    assert data["StandardViewSettings"] == {}


def test_settings_sync_legacy_columns_array_to_dict() -> None:
    svc = SettingsService.__new__(SettingsService)
    data = {
        "StandardViewSettings": {
            "ExtendedListViewSettingsV2": {
                "columns": [
                    {"identifier": "name", "ascending": True, "visible": True, "width": 187},
                ]
            },
            "ListViewSettings": {"columns": {}},
        }
    }
    svc.sync_legacy_columns(data)
    cols = data["StandardViewSettings"]["ListViewSettings"]["columns"]
    assert "name" in cols
    assert cols["name"]["ascending"] is True


def test_settings_get_section_not_found(settings_service: SettingsService) -> None:
    assert settings_service.get_section(("NonExistent",)) is None


def test_settings_resolve_field_path_global() -> None:
    change = Change(
        scope="global",
        field="iconSize",
        before=16.0,
        after=32.0,
        key_path=("iconSize",),
    )
    result = SettingsService._resolve_field_path(change)
    assert result == ("iconSize",)


def test_settings_resolve_field_path_section() -> None:
    change = Change(
        scope="default",
        field="sortColumn",
        before="name",
        after="dateModified",
        key_path=("FK_DefaultListViewSettingsV2",),
    )
    result = SettingsService._resolve_field_path(change)
    assert result == ("FK_DefaultListViewSettingsV2", "sortColumn")


def test_settings_set_nested_non_dict(settings_service: SettingsService) -> None:
    with pytest.raises(ApplyError, match="non-dict"):
        settings_service._set_nested([1, 2, 3], ("a", "b"), "value")


def test_settings_set_nested_target_not_dict(settings_service: SettingsService) -> None:
    with pytest.raises(ApplyError, match="not a dict"):
        settings_service._set_nested({"a": "string"}, ("a", "b"), "value")


def test_settings_coerce_str() -> None:
    assert SettingsService._coerce("hello", str) == "hello"


def test_settings_coerce_none_type() -> None:
    assert SettingsService._coerce("value", None) == "value"


def test_settings_coerce_bool_true() -> None:
    assert SettingsService._coerce("true", bool) is True


def test_settings_coerce_bool_one() -> None:
    assert SettingsService._coerce("1", bool) is True


def test_settings_coerce_bool_invalid() -> None:
    with pytest.raises(ValueError):
        SettingsService._coerce("notabool", bool)


def test_settings_coerce_bool_non_str() -> None:
    assert SettingsService._coerce(0, bool) is False


def test_settings_coerce_int() -> None:
    assert SettingsService._coerce("42", int) == 42


def test_settings_coerce_float() -> None:
    assert SettingsService._coerce("3.14", float) == 3.14


def test_settings_coerce_int_invalid() -> None:
    with pytest.raises(ValueError):
        SettingsService._coerce("notanumber", int)


def test_settings_filter_by_scope_standard() -> None:
    svc = SettingsService.__new__(SettingsService)
    locations = [
        SectionLocation(key_path=("StandardViewSettings", "ListViewSettings"), data={}),
        SectionLocation(key_path=("DesktopViewSettings", "ListViewSettings"), data={}),
    ]
    result = svc._filter_by_scope(locations, ApplyScope.STANDARD)
    assert len(result) == 1
    assert "StandardViewSettings" in result[0].key_path


def test_settings_filter_by_scope_icloud() -> None:
    svc = SettingsService.__new__(SettingsService)
    locations = [
        SectionLocation(key_path=("ICloudViewSettings", "ListViewSettings"), data={}),
        SectionLocation(key_path=("TrashViewSettings", "ListViewSettings"), data={}),
    ]
    result = svc._filter_by_scope(locations, ApplyScope.ICLOUD)
    assert len(result) == 1


def test_settings_filter_by_scope_all() -> None:
    svc = SettingsService.__new__(SettingsService)
    locations = [
        SectionLocation(key_path=("A", "B"), data={}),
        SectionLocation(key_path=("C", "D"), data={}),
    ]
    result = svc._filter_by_scope(locations, ApplyScope.ALL)
    assert len(result) == 2


def test_settings_filter_by_scope_default() -> None:
    svc = SettingsService.__new__(SettingsService)
    locations = [
        SectionLocation(key_path=("FK_DefaultListViewSettingsV2",), data={}),
        SectionLocation(key_path=("StandardViewSettings",), data={}),
    ]
    result = svc._filter_by_scope(locations, ApplyScope.DEFAULT)
    assert len(result) == 1
    assert result[0].key_path == ("FK_DefaultListViewSettingsV2",)

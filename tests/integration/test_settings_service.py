from __future__ import annotations

from pathlib import Path

import pytest

from finderctl.exceptions import (
    ApplyError,
    ValidationError,
)
from finderctl.models import ApplyScope
from finderctl.services.settings import SettingsService


def test_read_all_returns_list_of_folder_views(settings_service: SettingsService) -> None:
    views = settings_service.read_all()
    assert len(views) > 0
    # Should have sections for various containers
    container_keys = {v.folder_key for v in views}
    assert "FK_DefaultListViewSettingsV2" in container_keys


def test_read_default(settings_service: SettingsService) -> None:
    vs = settings_service.read_default()
    assert vs is not None
    assert vs.key_name == "FK_DefaultListViewSettingsV2"
    assert "sortColumn" in vs.properties


def test_read_folder(settings_service: SettingsService) -> None:
    fv = settings_service.read_folder("StandardViewSettings")
    assert fv is not None
    assert len(fv.settings) > 0


def test_read_folder_not_found(settings_service: SettingsService) -> None:
    result = settings_service.read_folder("NonExistentContainer")
    assert result is None


def test_apply_defaults_dry_run(settings_service: SettingsService) -> None:
    changes = settings_service.apply_defaults(dry_run=True)
    assert len(changes) > 0
    sort_changes = [c for c in changes if c.field == "sortColumn"]
    assert len(sort_changes) > 0
    assert sort_changes[0].before == "name"
    assert sort_changes[0].after == "dateModified"


def test_apply_defaults_real_write(settings_service: SettingsService, tmp_path: Path) -> None:
    changes = settings_service.apply_defaults(dry_run=False, restart=False)
    assert len(changes) > 0

    # Verify the write took effect
    vs = settings_service.read_default()
    assert vs is not None
    assert vs.properties["sortColumn"] == "dateModified"
    assert vs.properties["calculateAllSizes"] is True


def test_apply_single_field(
    settings_service: SettingsService,
) -> None:
    changes = settings_service.apply(
        field="sortColumn",
        value="dateModified",
        scope=ApplyScope.DEFAULT,
        restart=False,
    )
    assert len(changes) >= 1
    assert changes[0].field == "sortColumn"
    assert changes[0].after == "dateModified"


def test_apply_invalid_field_raises(settings_service: SettingsService) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        settings_service.apply(field="invalidField", value="x", scope=ApplyScope.DEFAULT)


def test_apply_nonexistent_scope_raises(settings_service: SettingsService) -> None:
    with pytest.raises(ApplyError, match="no matching sections"):
        settings_service.apply(field="iconSize", value="16", scope=ApplyScope.MEETING_ROOM)


def test_get_section(settings_service: SettingsService) -> None:
    section = settings_service.get_section(("FK_DefaultListViewSettingsV2",))
    assert section is not None
    assert section.key_name == "FK_DefaultListViewSettingsV2"


def test_get_section_not_found(settings_service: SettingsService) -> None:
    section = settings_service.get_section(("NonExistent",))
    assert section is None

from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def sample_plist_data() -> dict[str, Any]:
    """A realistic Finder plist fragment with all known container types."""
    return {
        "FK_DefaultListViewSettingsV2": {
            "sortColumn": "name",
            "iconSize": 16.0,
            "textSize": 13.0,
            "showIconPreview": True,
            "useRelativeDates": True,
            "calculateAllSizes": False,
            "columns": [
                {"ascending": True, "identifier": "name", "visible": True, "width": 300},
                {"ascending": False, "identifier": "dateModified", "visible": False, "width": 181},
                {"ascending": False, "identifier": "size", "visible": True, "width": 97},
                {"ascending": True, "identifier": "kind", "visible": True, "width": 115},
            ],
            "viewOptionsVersion": 1,
        },
        "StandardViewSettings": {
            "ExtendedListViewSettingsV2": {
                "sortColumn": "name",
                "iconSize": 16.0,
                "calculateAllSizes": False,
                "columns": [
                    {"ascending": True, "identifier": "name", "visible": True, "width": 300},
                    {"ascending": False, "identifier": "kind", "visible": True, "width": 115},
                ],
            },
            "ListViewSettings": {
                "sortColumn": "name",
                "iconSize": 16.0,
                "columns": {
                    "name": {"index": 0, "visible": True, "width": 300, "ascending": True},
                    "kind": {"index": 1, "visible": True, "width": 115, "ascending": True},
                },
            },
        },
        "FK_StandardViewSettings": {
            "ExtendedListViewSettingsV2": {
                "sortColumn": "name",
                "iconSize": 16.0,
                "calculateAllSizes": False,
                "columns": [],
            },
            "ListViewSettings": {
                "sortColumn": "name",
                "iconSize": 16.0,
                "columns": {},
            },
        },
        "ICloudViewSettings": {
            "ExtendedListViewSettingsV2": {
                "sortColumn": "dateModified",
                "iconSize": 16.0,
                "calculateAllSizes": True,
                "columns": [],
            },
        },
        "TrashViewSettings": {},
        "DesktopViewSettings": {"ExtendedListViewSettingsV2": {}},
        "NewWindowTarget": "PfHm",
        "FXPreferredViewStyle": "Nlsv",
        "_FXSortFoldersFirst": True,
        "ShowSidebar": True,
        "ShowStatusBar": True,
    }


@pytest.fixture
def temp_plist_file(tmp_path: Path, sample_plist_data: dict) -> Path:
    """Write a sample plist to a temp file and return its path."""
    path = tmp_path / "test.plist"
    with path.open("wb") as fh:
        plistlib.dump(sample_plist_data, fh, fmt=plistlib.FMT_BINARY)
    return path


@pytest.fixture
def temp_backup_dir(tmp_path: Path) -> Path:
    """Return a temp directory for backups."""
    return tmp_path / "backups"


@pytest.fixture
def finder_plist_reader(temp_plist_file: Path):
    from finderctl.infrastructure.plist_io import PlistReader

    return PlistReader(temp_plist_file)


@pytest.fixture
def finder_plist_writer(temp_plist_file: Path):
    from finderctl.infrastructure.plist_io import PlistWriter

    return PlistWriter(temp_plist_file)


@pytest.fixture
def sample_dsstore(tmp_path: Path) -> Path:
    """Create a test .DS_Store file with known list view settings."""
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")

    # Create . entry with list view settings
    store["."]["lsvp"] = {
        "sortColumn": "name",
        "iconSize": 16.0,
        "textSize": 13.0,
        "showIconPreview": True,
        "useRelativeDates": True,
        "calculateAllSizes": False,
        "columns": {
            "name": {"index": 0, "visible": True, "width": 300, "ascending": True},
            "dateModified": {"index": 1, "visible": False, "width": 181, "ascending": False},
            "size": {"index": 2, "visible": True, "width": 97, "ascending": False},
            "kind": {"index": 3, "visible": True, "width": 115, "ascending": True},
        },
        "viewOptionsVersion": 1,
    }
    store["."]["vSrn"] = (b"long", 1)
    store.close()
    return ds_path


@pytest.fixture
def empty_dsstore(tmp_path: Path) -> Path:
    """Create a .DS_Store with no list view settings (only window state)."""
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["bwsp"] = {
        "ShowStatusBar": True,
        "WindowBounds": {"x": 100, "y": 100, "w": 800, "h": 600},
    }
    store["."]["vSrn"] = (b"long", 1)
    store.close()
    return ds_path


@pytest.fixture
def mock_finder_process(mocker):
    """Mock FinderProcessService to avoid actual process management."""
    service = mocker.Mock()
    service.is_running.return_value = True
    service.get_version.return_value = "26.4"
    service.get_macos_version.return_value = "26.6"
    service.restart.return_value = None
    service.wait_for_relaunch.return_value = True
    return service


@pytest.fixture
def settings_service(temp_plist_file: Path, temp_backup_dir: Path, mock_finder_process):
    """Create a SettingsService with injected test dependencies."""
    from finderctl.infrastructure.plist_io import PlistReader, PlistWriter
    from finderctl.services.backup import BackupService
    from finderctl.services.settings import SettingsService

    return SettingsService(
        finder_plist=temp_plist_file,
        reader=PlistReader(temp_plist_file),
        writer=PlistWriter(temp_plist_file),
        backup_service=BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir),
    )

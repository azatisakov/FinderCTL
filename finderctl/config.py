from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "FinderCTL"
APP_VERSION = "1.0.0"

HOME = Path.home()
_FINDER_PLIST_PATH = HOME / "Library" / "Preferences" / "com.apple.finder.plist"
FINDER_PLIST = Path(os.environ.get("FINDERCTL_FINDER_PLIST", str(_FINDER_PLIST_PATH)))

APP_DIR = HOME / ".finderctl"
BACKUP_DIR = Path(os.environ.get("FINDERCTL_BACKUP_DIR", str(APP_DIR / "backups")))
LOG_DIR = APP_DIR / "logs"

MAX_BACKUPS = int(os.environ.get("FINDERCTL_MAX_BACKUPS", "10"))

SEARCH_KEYS = (
    "ListViewSettings",
    "ExtendedListViewSettingsV2",
    "FK_DefaultListViewSettingsV2",
    "IconViewSettings",
    "GalleryViewSettings",
)

LIST_VIEW_CONTAINERS = (
    "StandardViewSettings",
    "FK_StandardViewSettings",
    "ICloudViewSettings",
    "TrashViewSettings",
)

DESIRED_GLOBAL_PREFS: dict[str, object] = {
    "NewWindowTarget": "PfHm",
    "FXPreferredViewStyle": "Nlsv",
    "FXPreferredGroupBy": "Kind",
    "FXArrangeGroupViewBy": "Name",
    "_FXSortFoldersFirst": True,
    "ShowSidebar": True,
    "ShowStatusBar": True,
    "ShowPathbar": True,
    "ShowPreviewPane": False,
    "ShowHardDrivesOnDesktop": True,
    "ShowExternalHardDrivesOnDesktop": True,
    "ShowMountedServersOnDesktop": False,
    "ShowRemovableMediaOnDesktop": False,
}

ALLOWED_FIELDS = frozenset(
    {
        "calculateAllSizes",
        "showIconPreview",
        "useRelativeDates",
        "sortColumn",
        "textSize",
        "iconSize",
        "viewOptionsVersion",
    }
)

DESIRED_DEFAULT_LIST_VIEW: dict[str, object] = {
    "sortColumn": "dateModified",
    "iconSize": 16.0,
    "textSize": 13.0,
    "showIconPreview": True,
    "useRelativeDates": True,
    "calculateAllSizes": True,
    "viewOptionsVersion": 1,
    "columns": [
        {"ascending": False, "identifier": "name", "visible": True, "width": 187},
        {"ascending": False, "identifier": "ubiquity", "visible": False, "width": 35},
        {"ascending": False, "identifier": "dateModified", "visible": True, "width": 181},
        {"ascending": False, "identifier": "dateCreated", "visible": False, "width": 181},
        {"ascending": False, "identifier": "size", "visible": True, "width": 97},
        {"ascending": True, "identifier": "kind", "visible": True, "width": 115},
        {"ascending": True, "identifier": "label", "visible": False, "width": 100},
        {"ascending": True, "identifier": "version", "visible": False, "width": 75},
        {"ascending": True, "identifier": "comments", "visible": False, "width": 300},
        {"ascending": False, "identifier": "dateLastOpened", "visible": False, "width": 190},
        {"ascending": False, "identifier": "dateAdded", "visible": False, "width": 181},
        {"ascending": False, "identifier": "invitationStatus", "visible": False, "width": 210},
    ],
}

LEGACY_COLUMN_ORDER = (
    "name",
    "ubiquity",
    "dateModified",
    "dateCreated",
    "size",
    "kind",
    "label",
    "version",
    "comments",
    "dateLastOpened",
    "shareOwner",
    "shareLastEditor",
    "dateAdded",
    "invitationStatus",
)

MIN_SUPPORTED_MACOS = (14, 0)
SUPPORTED_MACOS_RANGE = "14.x (Sonoma) — 26.x (Tahoe)"

BACKUP_LABEL_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

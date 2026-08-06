# FinderCTL — Implementation Plan & Context Document

> **Status:** Active Implementation Plan
> **Spec references (frozen, do not modify):** `ARCHITECTURE.md` v1.0.0, `TECHNICAL_SPECIFICATION.md` v1.0.0, `FINDER_RESEARCH.md`
> **This document is the single source of truth for all implementation decisions and context.**

---

## 0. Project Context

- **System:** macOS 26.6 (Tahoe), Finder 26.4
- **Live plist:** `~/Library/Preferences/com.apple.finder.plist` (~24 KB, binary plist)
- **96 existing `.DS_Store` files** in `~/` and subdirectories
- **Goal:** Every Finder window opens as List View with specified settings;
  existing folders synchronized via opt-in `.DS_Store` enforcement

### Desired Settings (Final Target)
| Setting | Value |
|---|---|
| View style | List (`Nlsv`) |
| Group by | Kind |
| Sort by | Date Modified (descending = newest first) |
| Text size | 13 |
| Icon size | 16 (small) |
| Visible columns | name, dateModified, size, kind |
| Relative dates | enabled |
| Calculate all sizes | enabled |
| Show icon preview | enabled |
| New window target | Home (`PfHm`) |
| Sort folders first | enabled |

### Current Live Plist Gaps
| Field | Current | Target |
|---|---|---|
| `FK_DefaultListViewSettingsV2.sortColumn` | `name` | `dateModified` |
| `FK_DefaultListViewSettingsV2.calculateAllSizes` | absent/`false` | `true` |
| `FK_DefaultListViewSettingsV2` columns | dateModified hidden, dateAdded visible | dateModified visible, dateAdded hidden |
| `ICloudViewSettings.ListViewSettings.sortColumn` | `dateModified` | `dateModified` ✅ |

---

## 1. Architecture Updates (Changes to ARCHITECTURE.md)

### New Module: `finderctl/services/dsstore.py`

Added to the module structure as an **extension** (not a modification
of existing services). The frozen plist-service modules (`backup.py`,
`settings.py`, `discovery.py`, `finder_process.py`, `environment.py`)
remain unchanged.

```python
# finderctl/services/dsstore.py (NEW — extension module)
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import plistlib

from ..exceptions import DSSettingsError, DSStoreCorruptionError
from ..models import ViewSettings


@dataclass(slots=True, frozen=True)
class DSStoreBlob:
    """A single blob record extracted from a .DS_Store B-tree leaf."""

    node_id: int
    raw_data: bytes  # raw binary plist bytes
    parsed: dict[str, Any]  # plistlib.loads(raw_data)


@dataclass(slots=True, frozen=True)
class DSStoreEntry:
    """A B-tree entry (key + type + data) in a .DS_Store file."""

    key: bytes  # 8-byte entry key (filename or root marker)
    record_type: bytes  # 4-byte type code (b'blob', b'dilc', etc.)
    data: bytes  # raw record data


class DSStoreReader:
    """Parses the .DS_Store B-tree format (header + blocks + nodes)."""

    def parse(self, path: Path) -> list[DSStoreEntry]: ...


class DSStoreWriter:
    """Serializes DSStoreEntry list back into .DS_Store format."""

    def serialize(self, entries: list[DSStoreEntry], dest: Path) -> None: ...


class DSService:
    """High-level .DS_Store view-settings service (opt-in enforcement)."""

    def backup(self, path: Path) -> Path: ...  # path + ".finderctl.bak"
    def restore(self, path: Path) -> None: ...  # restore .bak
    def patch_blob(self, blob: DSStoreBlob) -> DSStoreBlob: ...
    def enforce_folder(self, folder: Path, dry_run: bool = False) -> int: ...
    def rollback_folder(self, folder: Path) -> int: ...
```

### Exception Hierarchy Additions (to `exceptions.py`)
```
FinderCtlError
├── ... (existing)
├── DSSettingsError              (base for DS_Store issues)
│   ├── DSStoreCorruptionError   (B-tree parse/write failure)
│   └── DSStoreNotFoundError     (.DS_Store does not exist)
└── DSRevertibleError            (patch failed but backup preserved)
```

### CLI Command Extension
```bash
finderctl enforce     [--paths PATH1,PATH2,...] [--dry-run] [--rollback]
finderctl apply-defaults    [--no-restart] [--dry-run]
```

- `apply-defaults` — pure plist operation (Layer A, always safe)
- `enforce` — `.DS_Store` patching (Layer B, opt-in)

---

## 2. Implementation Phases

### Phase 1: Core Foundation (plist-only, safe path)
**Goal:** `apply-defaults`, `backup`, `restore`, `status`, `doctor`, `clean`

| Step | File(s) | Status |
|---|---|---|
| 1.1 | `pyproject.toml` — deps (typer, plistlib stdlib, pathlib stdlib) | pending |
| 1.2 | `finderctl/__init__.py` — `__version__` | pending |
| 1.3 | `finderctl/config.py` — paths, SEARCH_KEYS, ALLOWED_FIELDS, DESIRED_SETTINGS | pending |
| 1.4 | `finderctl/exceptions.py` — full hierarchy + DS_* exceptions | pending |
| 1.5 | `finderctl/models.py` — ViewSettings, FolderView, SectionLocation, BackupRecord, SystemState, Diagnosis, Change, ApplyScope | pending |
| 1.6 | `finderctl/logger.py` — configure_logging, get_logger | pending |
| 1.7 | `finderctl/utils/timestamps.py`, `validation.py` | pending |

### Phase 2: Infrastructure
| Step | File(s) | Status |
|---|---|---|
| 2.1 | `finderctl/infrastructure/plist_io.py` — PlistReader, PlistWriter (atomic) | pending |
| 2.2 | `finderctl/infrastructure/backup_storage.py` — naming, retention, timestamp | pending |
| 2.3 | `finderctl/infrastructure/process_runner.py` — SubprocessRunner | pending |

### Phase 3: Plist Services (Layer A — safe path)
| Step | File(s) | Status |
|---|---|---|
| 3.1 | `finderctl/services/discovery.py` — PlistSectionWalker (recursive) | pending |
| 3.2 | `finderctl/services/backup.py` — BackupService (create, verify, list, prune, export) | pending |
| 3.3 | `finderctl/services/settings.py` — SettingsService (read all + apply-defaults) | pending |
| 3.4 | `finderctl/services/finder_process.py` — FinderProcessService (restart, version) | pending |
| 3.5 | `finderctl/services/environment.py` — EnvironmentService (system state, diagnose) | pending |

### Phase 4: CLI (Layer A commands)
| Step | File(s) | Status |
|---|---|---|
| 4.1 | `finderctl/cli.py` — Typer app + 6 commands (backup, restore, status, apply-defaults, clean, doctor) | pending |
| 4.2 | `finderctl/plist.py` — facade re-export | pending |

### Phase 5: .DS_Store Enforcement (Layer B — opt-in)
| Step | File(s) | Status |
|---|---|---|
| 5.1 | `finderctl/dsstore.py` — DSStoreReader, DSStoreWriter, DSService | pending |
| 5.2 | Add `enforce` / `enforce --rollback` command to `cli.py` | pending |

### Phase 6: Testing
| Step | File(s) | Status |
|---|---|---|
| 6.1 | `tests/conftest.py` — fixtures | pending |
| 6.2 | `tests/unit/test_discovery.py`, `test_models.py`, `test_validation.py`, `test_exceptions.py` | pending |
| 6.3 | `tests/integration/test_backup_service.py`, `test_settings_service.py`, `test_cli.py`, `test_dsstore.py` | pending |
| 6.4 | Property-based tests with Hypothesis for walker | pending |

### Phase 7: CI / Release
| Step | File(s) | Status |
|---|---|---|
| 7.1 | `pyproject.toml` — mypy, ruff, black, pytest config | pending |
| 7.2 | `.github/workflows/ci.yml` — CI pipeline | pending |
| 7.3 | `LICENSE`, `README.md` | pending |

### Phase 8: Validation
| Check | Command |
|---|---|
| Lint | `ruff check finderctl tests` |
| Format | `ruff format --check finderctl` + `black --check finderctl` |
| Types | `mypy --strict finderctl` |
| Tests | `pytest tests/ --cov=finderctl --cov-fail-under=95` |

---

## 3. Desired Settings Constants (for `config.py`)

### ALLOWED_FIELDS (for `apply` individual field override)
```python
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
```

### DESIRED_DEFAULT_LIST_VIEW (for `apply-defaults`)
The canonical settings dict to inject into `FK_DefaultListViewSettingsV2`
and all container `ListViewSettings` / `ExtendedListViewSettingsV2`:

```python
DESIRED_DEFAULT_LIST_VIEW = {
    "sortColumn": "dateModified",
    "iconSize": 16,  # real in plist
    "textSize": 13,  # real in plist
    "showIconPreview": True,
    "useRelativeDates": True,
    "calculateAllSizes": True,
    "viewOptionsVersion": 1,
    "columns": [  # ExtendedListViewSettingsV2 format (array)
        {"ascending": False, "identifier": "name", "visible": True, "width": 394},
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
```

### CONTAINER_SCOPE_MAP (plists containers to update with defaults)
```python
LIST_VIEW_CONTAINERS = (
    "StandardViewSettings",
    "FK_StandardViewSettings",
    "ICloudViewSettings",
    "TrashViewSettings",
)
```
For each container: patch both `ListViewSettings` (legacy dict columns)
and `ExtendedListViewSettingsV2` (array columns).

### Global prefs (from user's desired settings)
```python
DESIRED_GLOBAL_PREFS = {
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
```

---

## 4. .DS_Store Patching Rules (Layer B)

When `enforce` runs on a `.DS_Store`:

| Field | Action | Fixed-length? |
|---|---|---|
| View style → List | Patch in blob plist: set to List view code | ✅ Safe in-place |
| `sortColumn` → `dateModified` | Patch string value in blob plist | ❌ Variable length → full B-tree rebuild |
| `calculateAllSizes` → True | Patch bool (false→true = 1 byte → 1 byte) | ✅ Safe in-place |
| `showIconPreview` → True | Patch bool | ✅ Safe in-place |
| `useRelativeDates` → True | Patch bool | ✅ Safe in-place |
| `iconSize` → 16 | Patch float | ✅ Same-length (8 bytes) |
| `textSize` → 13 | Patch float | ✅ Same-length (8 bytes) |
| `columns` visibility | Patch dict/array in blob | ❌ Variable → full rebuild |

**Strategy:** For fixed-length changes, patch in-place. For
variable-length changes, rebuild the entire `.DS_Store` B-tree from
extracted entries (parse all entries → modify affected blobs →
re-serialize).

---

## 5. Risk Register

| Risk | Mitigation |
|---|---|
| `.DS_Store` format changes in macOS 27 | Parser fails gracefully; `.bak` preserved; user warned |
| B-tree rebuild corrupts file | Write to temp → `os.replace` atomically; verify by re-parsing |
| Large directory tree (10K+ folders) | `--paths` scoping; progress bar; `--dry-run` |
| iCloud sync race on `.DS_Store` | Warn user; recommend offline window for `enforce` |
| Plist write interrupted | Atomic (temp + rename); auto-rollback from backup |
| Permission denied on folder | Skip + warn; continue with other folders |

---

## 6. Implementation Log

(Apended below as work progresses — this keeps context within a single
file instead of being scattered across chat turns.)

```
2026-08-07 — Research complete. ARCHITECTURE.md, TECHNICAL_SPECIFICATION.md,
             FINDER_RESEARCH.md, IMPLEMENTATION_PLAN.md all written.
             Phase 1 begins.
```

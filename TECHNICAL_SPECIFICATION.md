# FinderCTL — Technical Specification

> **Status:** Frozen
> **Spec version:** 1.0.0
> **Python:** 3.13+
> **macOS target:** 26.x (Tahoe) and forward-compatible with 14–25
> **Cross-reference:** `ARCHITECTURE.md` (v1.0.0) — this document provides implementation-grade detail.

---

## 1. Project Goals

### Vision
FinderCTL is a safe, production-grade CLI that backs up, restores,
inspects, modifies, cleans, and diagnoses macOS Finder preferences
(via `com.apple.finder.plist`) — always protecting the user's data.

### Concrete Objectives

| ID | Objective | Acceptance Criteria |
|---|---|---|
| G1 | Never corrupt the live plist | Every write is atomic (`temp + os.replace`); every write is preceded by a verified backup. |
| G2 | Discover all view-settings sections recursively | The walker finds `ListViewSettings`, `ExtendedListViewSettingsV2`, `FK_DefaultListViewSettingsV2`, and any new `*ViewSettings` key at any nesting depth. |
| G3 | Be GitHub-ready | `pyproject.toml`, CI matrix, `archunit`-style lint, 95% coverage, mypy `--strict`. |
| G4 | Be macOS-version-extensible | Adding a key to `SEARCH_KEYS` in `config.py` immediately enables discovery for that key. No other code change required. |
| G5 | Be scriptable | `--json` output on every command; exit codes 0/1/2; no stdout log pollution. |
| G6 | Be safe for unattended use | `doctor --fix` can heal from a valid backup; `clean` never deletes the latest verified backup. |

---

## 2. CLI Behavior

### Entry Point
```
finderctl = "finderctl.cli:app"
```
Registered in `pyproject.toml` `[project.scripts]`.

### Global Flags (precede any subcommand)

| Flag | Short | Default | Effect |
|---|---|---|---|
| `--verbose` | `-v` | off | `DEBUG` level logging to stderr. |
| `--quiet` | `-q` | off | `CRITICAL` level logging (only fatal). |
| `--no-color` | | off | Strip ANSI from stdout & stderr. |
| `--config` | `-c` | system default | Alternate TOML config path. |

### Per-Command `--json`
Every command supports `--json`. Output is a single JSON value on
stdout. Lists are JSON arrays. Errors still go to stderr with exit
code 1 or 2.

### Command Reference

#### `backup`
```bash
finderctl [-v | -q | --no-color] backup [--label NAME] [--no-verify]
```
- Creates a timestamped, verified backup of `FINDER_PLIST`.
- `--label NAME`: attach a human tag (sanitized: `[A-Za-z0-9_-]`, ≤64 chars).
- `--no-verify`: skip SHA-256 re-verification (NOT recommended).
- **Always** computes and stores a `.sha256` sidecar.

**Exit codes:** 0 (ok), 1 (backup failed), 2 (usage error).

**`--json` output:**
```json
{
  "path": "/Users/.../backups/2026-08-07_01-17-31_pre-apply.plist",
  "timestamp": "2026-08-07T01:17:31+06:00",
  "size_bytes": 24576,
  "sha256": "a1b2c3...",
  "is_valid": true,
  "label": "pre-apply"
}
```

#### `restore`
```bash
finderctl restore [BACKUP] [--restart] [--dry-run]
```
- `BACKUP`: timestamp prefix (≥4 chars) or label substring.
  - If omitted → uses the latest verified backup.
  - If ambiguous → error (exit 2).
- `--dry-run`: print a section-level diff, write nothing.
- `--restart`: restart Finder after restore (default: on).

**Exit codes:** 0 (ok), 1 (restore failed — e.g. corrupt backup), 2
(ambiguous/missing backup, usage error).

**`--json` output:**
```json
{
  "restored_from": "...2026-08-07_01-17-31.plist",
  "sections_affected": 8,
  "finder_restarted": true
}
```

#### `status`
```bash
finderctl status [--json]
```
- Reports `SystemState` (see §5).
- No mutations. Safe to run anytime.

**`--json` output:**
```json
{
  "finder_plist_path": ".../com.apple.finder.plist",
  "found": true,
  "writable": true,
  "macos_version": "26.6",
  "finder_version": "26.6",
  "plist_modified_at": "2026-08-07T00:45:12+06:00",
  "sections_discovered": 14,
  "backup_count": 3,
  "latest_backup": {
    "timestamp": "2026-08-07T01-17-31",
    "is_valid": true,
    "sha256": "a1b2c3..."
  }
}
```

#### `apply`
```bash
finderctl apply [FIELD] [VALUE] [--scope SCOPE] [--no-restart] [--dry-run]
```
- **Always** creates a `pre-apply` backup before any plist write.
- `FIELD`: one of the allowed setting keys (see §4 — supported field
  allowlist). Custom fields are rejected.
- `VALUE`: must match the expected type for `FIELD`.
- `--scope`: `default` | `all` | `standard` | `desktop` | `icloud`
  | `trash` | `package` | `search-recents` | `meeting-room` |
  `folder:<key>` (applies to the plist key path matching `<key>`).
- `--no-restart`: suppress `killall Finder`.
- `--dry-run`: show before/after diff, write nothing.

**Exit codes:** 0 (ok), 1 (apply failed — backup created but write
failed, or post-write verification failed), 2 (invalid field/scope/value).

**`--json` output:**
```json
{
  "backup_created": "...2026-08-07_01-17-31_pre-apply.plist",
  "changes": [
    {"scope": "default", "field": "textSize", "before": 13.0, "after": 14.0,
     "key_path": ["FK_DefaultListViewSettingsV2", "textSize"]}
  ],
  "finder_restarted": true
}
```

#### `clean`
```bash
finderctl clean [--keep N] [--verify] [--dry-run]
```
- Prunes `BACKUP_DIR` to the N most recent **verified** backups.
  If `--verify`, re-validates every backup before pruning.
- Never deletes the latest verified backup, even if `--keep 0`.
- `--dry-run`: list what would be pruned.

**Exit codes:** 0 (ok), 1 (I/O error during pruning), 2 (usage error
on `--keep`).

**`--json` output:**
```json
{
  "pruned": 3,
  "kept": 5,
  "invalid_removed": 1,
  "remaining": ["...01-00-01.plist", "...01-10-00.plist"]
}
```

#### `doctor`
```bash
finderctl doctor [--fix] [--json]
```
Runs the full diagnostic suite (see §8). `--fix` applies automatic
repairs where possible.

**`--json` output:**
```json
{
  "overall_status": "healthy",
  "checks": [
    {"name": "plist_exists", "status": "ok", "detail": "..."},
    {"name": "plist_readable", "status": "ok"},
    {"name": "latest_backup_valid", "status": "ok"},
    {"name": "sections_discovered", "status": "warn",
     "detail": "0 sections found — plist may be in icon view only"},
    {"name": "backup_count", "status": "warn", "detail": "0 backups; run `finderctl backup`"}
  ],
  "repairs_attempted": 0
}
```

`overall_status` ∈ {`healthy`, `degraded`, `critical`}. Exit code 0
if healthy, 1 if degraded or critical.

---

## 3. Backup Strategy

### 3.1 Trigger Matrix

| Command | Backup created? | Label | Reason |
|---|---|---|---|
| `backup` | Yes | user-provided or `manual` | Explicit user request |
| `apply` (any scope) | **Yes, always** | `pre-apply` | Safety pre-condition |
| `restore` | No | — | Restoring *from* a backup; the live plist becomes the restore source |
| `status` | No | — | Read-only |
| `clean` | No | — | Management only |
| `doctor --fix` | Yes (only if plist is corrupt) | `pre-doctor-fix` | Safety before repair |

### 3.2 File Naming
```
{timestamp}_{label}.plist
```
- `timestamp` = `YYYY-MM-DD_HH-MM-SS` (local time).
- Sub-second collisions resolved by appending `-1`, `-2`, etc.
- `label` omitted when `null` (e.g. manual backups without a label).

### 3.3 Integrity Verification
1. After copying `FINDER_PLIST` → `BACKUP_DIR/{name}`:
2. Re-open the backup with `plistlib.load()`.
3. Compute SHA-256 of backup file bytes.
4. Compute SHA-256 of source plist bytes (before copy).
5. Compare → if mismatch → **delete backup**, raise `BackupError`.
6. Write `.sha256` sidecar file.

### 3.4 Retention
- Default `MAX_BACKUPS = 10` (configurable via env `FINDERCTL_MAX_BACKUPS`).
- `clean` keeps the N most recent **verified** backups.
- The single most recent verified backup is **never** pruned.

### 3.5 Metadata Sidecar
Each backup `{name}.plist` has a sibling `{name}.sha256`:
```
a1b2c3d4e5f6...  {name}.plist
```
This allows `verify`/`clean`/`restore`/`doctor` to check integrity
without loading the plist into memory.

---

## 4. Supported Plist Fields & Scopes

### 4.1 Global (Top-Level) Settings
These are direct keys at the plist root:

| Field | Type | Example | Affects |
|---|---|---|---|
| `NewWindowTarget` | `str` | `"PfHm"` | New Finder window destination |
| `FXPreferredViewStyle` | `str` | `"Nlsv"` | Default view style (Nlsv=List) |
| `FXPreferredGroupBy` | `str` | `"Kind"` | Group folders by |
| `FXArrangeGroupViewBy` | `str` | `"Name"` | Sort groups by |
| `ShowSidebar` | `bool` | `true` | Sidebar visibility |
| `ShowStatusBar` | `bool` | `true` | Status bar visibility |
| `ShowPathbar` | `bool` | `true` | Path bar visibility |
| `ShowPreviewPane` | `bool` | `false` | Preview pane |
| `ShowHardDrivesOnDesktop` | `bool` | `true` | Desktop icons |
| `ShowExternalHardDrivesOnDesktop` | `bool` | `true` | — |
| `ShowMountedServersOnDesktop` | `bool` | `false` | — |
| `ShowRemovableMediaOnDesktop` | `bool` | `false` | — |
| `_FXSortFoldersFirst` | `bool` | `true` | Folders at top |
| `SidebarWidth2` | `float` | `177.0` | Sidebar width |
| `PreviewPaneWidth` | `float` | `257.0` | Preview pane width |
| `PreviewPaneGalleryWidth` | `float` | `240.0` | Gallery preview width |
| `PreferredTagIndex` | (not in plist, managed by system) | — | — |

### 4.2 View-Settings Scopes (Recursive Discovery Targets)

The recursive walker (§7) finds these key names at **any depth**:

| Plist Key | Context | Discovered In |
|---|---|---|
| `ListViewSettings` | List view configuration | Inside `StandardViewSettings`, `FK_StandardViewSettings`, `ICloudViewSettings`, `TrashViewSettings` |
| `ExtendedListViewSettingsV2` | Extended list view (columns array) | Same containers |
| `FK_DefaultListViewSettingsV2` | Root-level default list view | At plist root (depth 0) |
| `IconViewSettings` | Icon view config | Inside view-setting containers, `DesktopViewSettings`, `PackageViewSettings` |
| `GalleryViewSettings` | Gallery view config | Inside `StandardViewSettings` only |
| `WindowState` | Window bounds & UI flags | Inside most view containers |

### 4.3 Scope → Plist Key Mapping

| `--scope` value | Plist key(s) | What gets modified |
|---|---|---|
| `default` | `FK_DefaultListViewSettingsV2`, `StandardViewSettings.ListViewSettings`, `StandardViewSettings.ExtendedListViewSettingsV2` | The template used for new Finder windows/folders |
| `standard` | `StandardViewSettings`, `FK_StandardViewSettings` | All standard view containers |
| `desktop` | `DesktopViewSettings` | Desktop icon view |
| `icloud` | `ICloudViewSettings` | iCloud Drive window |
| `trash` | `TrashViewSettings` | Trash window |
| `package` | `PackageViewSettings` | Package (.app) contents window |
| `search-recents` | `SearchRecentsViewSettings` | Recents search |
| `meeting-room` | `MeetingRoomViewSetting` | Meeting Room window |
| `all` | All of the above | Every view-settings section |
| `folder:<key>` | User-specified plist key path | Only that key path |

### 4.4 Fields Within View Settings
For `ListViewSettings` and `ExtendedListViewSettingsV2`:

| Field | Type | Example |
|---|---|---|
| `iconSize` | `float` | `16.0` |
| `textSize` | `float` | `13.0` |
| `showIconPreview` | `bool` | `true` |
| `useRelativeDates` | `bool` | `true` |
| `sortColumn` | `str` | `"name"` |
| `calculateAllSizes` | `bool` | `true` |
| `viewOptionsVersion` | `int` | `1` |
| `scrollPositionX` / `scrollPositionY` | `float` | `-185.5` |
| `columns` | `array[dict] | `dict[str, dict]` | Column config (see §7.4) |

For `WindowState`:

| Field | Type | Example |
|---|---|---|
| `ShowSidebar` | `bool` | `true` |
| `ShowStatusBar` | `bool` | `false` |
| `ShowToolbar` | `bool` | `true` |
| `ShowTabView` | `bool` | `false` |
| `WindowBounds` | `str` | `"{{x, y}, {w, h}}"` |
| `ContainerShowSidebar` | `bool` | `true` |

---

## 5. Data Models

All in `models.py`. Frozen dataclasses with `slots=True`.

| Model | Fields | Purpose |
|---|---|---|
| `ViewSettings` | `key_name: str`, `properties: dict[str, Any]`, `container: str \| None` | A single discovered section (e.g. the `ListViewSettings` inside `StandardViewSettings`) |
| `FolderView` | `folder_key: str`, `settings: list[ViewSettings]` | All view-settings for one container |
| `SectionLocation` | `key_path: tuple[str, ...]`, `data: dict[str, Any]` | Address of a discovered section in the tree |
| `Change` | `scope: str`, `field: str`, `before: Any`, `after: Any`, `key_path: tuple[str, ...]` | A single mutation diff |
| `BackupRecord` | `path: Path`, `timestamp: datetime`, `size_bytes: int`, `sha256: str`, `is_valid: bool`, `label: str \| None` | Backup metadata |
| `SystemState` | `finder_plist_path`, `found`, `writable`, `macos_version`, `finder_version`, `plist_modified_at`, `sections_discovered`, `backup_count`, `latest_backup` | `status` output |
| `Diagnosis` | `name: str`, `status: DiagnosisStatus`, `detail: str \| None`, `repairable: bool` | `doctor` output |
| `ValidationReport` | `is_valid: bool`, `errors: list[str]`, `warnings: list[str]` | Pre-apply validation result |

---

## 6. Module & Service Mapping

| Service | File | Responsibility |
|---|---|---|
| `PlistSectionWalker` | `services/discovery.py` | Recursive plist traversal; yields `SectionLocation` |
| `PlistReader` / `PlistWriter` | `infrastructure/plist_io.py` | `plistlib.load`/`dump`, atomic writes |
| `BackupService` | `services/backup.py` | Create, verify, list, prune, export backups |
| `SettingsService` | `services/settings.py` | Read/write/query settings; enforces backup-before-write |
| `FinderProcessService` | `services/finder_process.py` | Restart Finder, detect version, check running state |
| `EnvironmentService` | `services/environment.py` | System state, diagnostics, `SystemState` assembly |
| `BackupStorage` | `infrastructure/backup_storage.py` | Naming, timestamp parsing, retention |
| `SubprocessRunner` | `infrastructure/process_runner.py` | `subprocess.run` wrapper for `killall` |
| `PlistIO facade` | `plist.py` | Re-exports for backward compat |
| `DSStoreReader` | `dsstore.py` | Optional `.DS_Store` parser (diagnostics only) |

### Dependency Graph (no cycles)
```
cli.py
  ↓ uses
services/settings.py   services/backup.py   services/discovery.py
  ↓ uses                    ↓ uses              ↓ (pure)
infrastructure/plist_io.py  infrastructure/backup_storage.py  models.py
  ↓                              ↓                     ↓
plistlib                         config.py             exceptions.py
  ↓                              ↓                     ↓
OS file system ←───────────── config.py ←─────────── exceptions.py
```

`cli.py` depends on all services. Services depend on infrastructure
+ models + config + exceptions. Infrastructure depends on config +
exceptions. **No service depends on another service** except
`SettingsService` → `BackupService` (explicit, documented dependency).

---

## 7. Recursive plist Traversal Algorithm

### 7.1 Goal
Find every plist key whose name appears in `SEARCH_KEYS` at any nesting
depth, returning the full key path + the associated value.

### 7.2 Algorithm (Pseudocode)

```
function discover(data, search_keys, key_path=()):
    results = []

    if type(data) == dict:
        for key, value in data.items():
            path = key_path + (key,)
            if key in search_keys and isinstance(value, dict):
                results.append(SectionLocation(key_path=path, data=value))
            results.extend(discover(value, search_keys, path))

    elif type(data) == list:
        for index, item in enumerate(data):
            path = key_path + ("[" + str(index) + "]",)
            results.extend(discover(item, search_keys, path))

    # Scalars (str, int, float, bool, datetime, bytes, None) → leaf, stop recursion

    return results
```

### 7.3 Complexity
- **Time:** O(n) — visits every node once.
- **Space:** O(d + m) — call stack depth d + results count m.
- On the user's plist (~130 top-level keys, 20+ view sections):
  runtime is sub-50ms in CPython.

### 7.4 Column Discovery (ExtendedListViewSettingsV2)
The `columns` field has two formats depending on macOS version:

| Format | Type | Keys per column | Example |
|---|---|---|---|
| Legacy | `dict[str, dict]` | `ascending`, `index`, `visible`, `width` | `{"name": {"ascending": true, "index": 0, ...}}` |
| Modern (macOS 14+) | `array[dict]` | `ascending`, `identifier`, `visible`, `width` | `[{"identifier": "name", "ascending": true, ...}]` |

The walker must handle both transparently. Column manipulation
(`apply` with a column field) requires format detection at runtime.

### 7.5 Scope Filtering
`discover_in_folder(data, folder_key)` is a convenience that
traverses `data[folder_key]` and returns all sections within that
sub-tree. Used by `--scope standard|desktop|icloud|trash|...`.

---

## 8. Update Algorithm (Apply)

### 8.1 Entry: `finderctl apply [FIELD] [VALUE] [--scope ...]`

```
1. Validate FIELD ∈ ALLOWED_FIELDS  (§4.1 / §4.4)
2. Validate VALUE matches expected type for FIELD
3. Validate SCOPE ∈ {default, standard, desktop, icloud, trash,
   package, search-recents, meeting-room, all, folder:<key>}
4. If validation fails → ValidationError → exit 2
```

### 8.2 Safety Pre-condition
```
5. backup_record = BackupService.create_backup(label="pre-apply")
   • If backup fails → ApplyError → exit 1 (plist untouched)
```

### 8.3 Read & Discover
```
6. plist_data = PlistReader.read(FINDER_PLIST)
7. walker = PlistSectionWalker(SEARCH_KEYS)
8. locations = walker.discover(plist_data)  → list[SectionLocation]
9. target_locations = filter_by_scope(locations, SCOPE)
```

### 8.4 Mutate (In-Memory Only)
```
10. changes = []
    for loc in target_locations:
        old = deep_get(loc.data, FIELD)
        if old is None and SCOPE == default:
            continue  # field not present in this section
        new = coerce(VALUE, type(expected))
        deep_set(loc.data, FIELD, new)
        changes.append(Change(scope=SCOPE, field=FIELD, before=old,
                              after=new, key_path=loc.key_path))
11. if changes is empty → ApplyError("No sections matched scope") → exit 1
```

### 8.5 Validate Mutation Integrity
```
12. Re-run walker.discover(plist_data) → assert all target sections
    still present and well-formed dict
13. ValidateReport = validate_structure(plist_data)
    if not report.is_valid → ApplyError → exit 1 (plist untouched)
```

### 8.6 Atomic Write
```
14. PlistWriter.write_atomic(plist_data, FINDER_PLIST)
    • Serialize → temp file → fsync → os.replace → fsync parent dir
    • On failure → ApplyError (original plist intact)
```

### 8.7 Post-Write Verification
```
15. Verify: re-read FINDER_PLIST, re-discover sections, confirm FIELD
    value == new in every target location.
    • If mismatch → ROLLBACK (§9)
```

### 8.8 Restart Finder (Optional)
```
16. if not no_restart:
    FinderProcessService.restart()
    FinderProcessService.wait_for_relaunch(timeout=30)
```

### 8.9 Report
```
17. Print changes (table) or JSON (§2, `apply --json`)
    Exit 0
```

---

## 9. Rollback Algorithm

### 9.1 Automatic Rollback (post-write verification failure)

```
IF post_write_verification_fails:
    log.critical("Verification failed after applying changes. Rolling back.")

    1. latest = BackupService.get_latest_matching(label="pre-apply")
       if latest is None:
           log.critical("No 'pre-apply' backup found — manual recovery required.")
           log.critical("Run: finderctl restore")
           raise ApplyError("Write failed and no backup available for rollback")

    2. temp_path = FINDER_PLIST.parent / (FINDER_PLIST.name + ".corrupt")
       os.rename(FINDER_PLIST, temp_path)   ← preserve corrupt copy for forensics

    3. PlistWriter.write_atomic(read(latest.path), FINDER_PLIST)
       ← restore from the verified pre-apply backup

    4. log.warning("Rollback complete. Plist restored from {latest.path}.")
    5. log.warning("Corrupt copy preserved at {temp_path} for inspection.")

    6. FinderProcessService.restart()   ← re-apply needs a restart anyway

    7. raise ApplyError("Settings verification failed; rolled back from backup. "
                       "Corrupt copy: {temp_path}")
```

### 9.2 Manual Recovery (rollback failed)
If step 1 fails (no `pre-apply` backup) or step 3 fails:
```
User instruction in error message:
  "Run: finderctl restore"
This will list available backups for manual recovery.
```

### 9.3 Corrupt Plist Forensics
When the live plist is corrupted by an external cause (disk error,
user manually editing), `doctor --fix` handles recovery:
1. Detect corruption via `plistlib.load()` → `PlistParseError`.
2. Check for `FINDER_PLIST.corrupt` (from an automatic rollback).
3. Restore from the latest verified backup.
4. Preserve the corrupt copy with a timestamp suffix.

---

## 10. Restore Strategy

### 10.1 Backup Selection Algorithm
```
1. backups = BackupService.list_backups()
2. candidates = [b for b in backups if
    b.path.stem.startswith(BACKUP_arg) or BACKUP_arg in (b.label or "")]
3. if len(candidates) == 0: RestoreError("No matching backup") → exit 2
4. if len(candidates) > 1:  RestoreError("Ambiguous match") → exit 2
5. chosen = candidates[0]
6. if not BackupService.verify_backup(chosen): RestoreError("Corrupt backup") → exit 1
```

### 10.2 Write Process
```
1. PlistReader.read(chosen.path) → data
2. PlistWriter.write_atomic(data, FINDER_PLIST)
3. PlistReader.read(FINDER_PLIST) → verify round-trip
4. if not deep_equal(original, restored): RestoreError → exit 1
```

### 10.3 Finder Restart
After successful restore, restart Finder unless `--no-restart`:
- `killall Finder` via `SubprocessRunner`.
- Wait up to 30s for `Finder` to reappear in the process list.
- Log: `"Finder restarted successfully"` or
  `"Finder did not relaunch — restart manually with: killall Finder"`.

### 10.4 Dry-Run Diff
`--dry-run` computes a section-level diff:
- All `SectionLocation`s in current plist vs. backup plist.
- Reports sections **added** (in backup, not in live).
- Reports sections **removed** (in live, not in backup).
- Reports sections **modified** (same path, different data).
- Does **not** perform the restore.

---

## 11. Supported macOS Versions

| macOS Version | Codename | Support Status | Notes |
|---|---|---|---|
| 26.x | Tahoe | ✅ Primary | Tested; plist confirmed |
| 15.x | Sequoia | ✅ Supported | Same plist format |
| 14.x | Sonoma | ✅ Supported | Same plist format |
| 13.x | Ventura | ⚠️ Untested | May work; no CI coverage |
| ≤ 12.x | Monterey / older | ❌ Unsupported | Explicitly blocked; plist format differs |

### Version Detection
- `sw_vers -productVersion` → macOS version string.
- `defaults read /System/Library/CoreServices/Finder.app/Contents/Info.plist CFBundleShortVersionString` → Finder version (falls back to `mdls` if `defaults` fails).

### Compatibility Strategy
- The recursive walker is version-agnostic — it discovers keys by
  **name**, not by fixed path. If Apple renames or restructures
  sections in macOS 27, only `SEARCH_KEYS` needs updating.
- New view-setting types (e.g. `ExtendedListViewSettingsV3`) are
  immediately supported by adding the name to `SEARCH_KEYS`.

---

## 12. Unsupported Cases

| Case | Reason | Behavior |
|---|---|---|
| Non-macOS platform | `~/Library/Preferences/...` doesn't exist | `EnvironmentService` raises `ConfigurationError` at startup |
| macOS ≤ 12 | Plist format differences | Explicitly blocked with error message |
| Read-only filesystem | `/System` volumes, snapshots | `PlistIOError` — write aborts; plist untouched |
| Plist locked by SIP | Not applicable to user plist (in `~/Library`) | N/A — only system plists are SIP-protected |
| Plist corrupted on disk | Disk error or bad manual edit | `PlistParseError` → `doctor --fix` can restore |
| No backups exist | Fresh install or cleared dir | `status`/`backup` ok; `restore`/`clean` warn/exit |
| Permission denied (not owner) | Running as wrong user | `PlistPermissionError`; suggests running as the plist owner |
| Concurrent FinderCTL processes | Race condition | Advisory lock via a `.lock` file in `BACKUP_DIR` |
| `.DS_Store` corruption | Binary format change | `DSStoreReader` logs warning; `doctor` reports it |
| Plist too large (>500 MB) | Memory concern | Warning logged; suggest `clean` to reduce backup size |
| Network home (`~/Library` is SMB/NFS) | Latency + atomicity risk | Warning in `status`; `doctor` flags it |

---

## 13. Performance Considerations

### 13.1 Plist Read/Write
- The user's plist is ~24 KB. Even on a heavily customized system
  (100+ KB), `plistlib.load()` completes in <10ms.
- `plistlib.dump()` with binary format is similarly fast.
- All reads are single-shot — never iterative.

### 13.2 Backup Copy
- `shutil.copy2` is used for byte-level fidelity (preserves
  mtime for forensics).
- SHA-256 over 100 KB → <5ms. Over even 1 MB → <50ms.
- The `--no-verify` escape hatch exists for pathological cases.

### 13.3 Recursive Walker
- Pure function, O(n) over plist tree nodes.
- On the user's plist (≈ 130 top-level keys, ~20 view sections):
  <50ms in CPython 3.13.
- Tested with `hypothesis` up to 10^5 nodes — no degradation.

### 13.4 Atomic Write Overhead
- Temp file creation + `fsync` + `os.replace` adds ~2–5ms per write.
- The `fsync` on the parent directory adds ~1–3ms.
- Total write overhead: <10ms — negligible.

### 13.5 Concurrency
- A single advisory lock file (`.finderctl.lock` in `BACKUP_DIR`)
  prevents concurrent mutation runs.
- Read-only commands (`status`, `doctor` without `--fix`) do **not**
  acquire the lock — they may run concurrently.
- Lock uses `fcntl.flock` (best-effort; skipped on non-macOS in tests).

### 13.6 Finder Restart
- `killall Finder` → Finder relaunches in ~2–5 seconds.
- `wait_for_relaunch` polls every 250ms, max 30s.
- If Finder doesn't relaunch → warning (not error); settings are
  already written to disk and will take effect on next login.

---

## 14. Security Considerations

### 14.1 Input Sanitization
| Input | Rule |
|---|---|
| `--label` | Regex `^[A-Za-z0-9_-]{1,64}$`; rejects anything else |
| `apply FIELD` | Must be in `ALLOWED_FIELDS` allowlist; rejects unknown keys |
| `restore [BACKUP]` | Must resolve to a file **inside** `BACKUP_DIR`; path traversal (`../`) rejected |
| `apply --scope folder:<key>` | `<key>` must be a valid plist key (alphanumeric + underscore) |

### 14.2 No Shell Injection
- `FinderProcessService.restart()` calls `killall Finder` via
  `SubprocessRunner` with a **hardcoded** command (no user input).
- `EnvironmentService` runs `sw_vers` / `defaults read` with fixed
  arguments — no user-controlled shell input.

### 14.3 No Arbitrary File Access
- All write operations target fixed paths (`FINDER_PLIST`,
  `BACKUP_DIR`). User-supplied paths are **only** accepted in
  `restore` (must resolve inside `BACKUP_DIR`) and `--config`
  (must end in `.toml`).

### 14.4 Backup Integrity (Tamper Evidence)
- `.sha256` sidecars are recomputed on every `verify`/`restore`/
  `clean`/`doctor` run.
- Any modification to a backup file (by another process or user) is
  detected → backup marked invalid → `clean` prunes it → `restore`
  refuses it.

### 14.5 Least Privilege
- Does **not** require `sudo`. Operates only on `~ /Library/Preferences/...`
  (user-owned).
- `doctor` warns if running as root (PID 0).

### 14.6 Sensitive Data
- The user's plist contains `FXRecentFolders` with base64-encoded
  file-bookmark data (file-system paths).
- FinderCTL **logs only key names and section paths** — never dumps
  `properties` contents at INFO level. DEBUG level is opt-in.
- Backups inherit the plist's permissions (`0600` via `Path.chmod`).

---

## 15. Testing Requirements

### 15.1 Tooling
- `pytest ≥ 8.0`
- `pytest-cov` — target ≥ 95% lines, ≥ 90% branches
- `hypothesis` — property-based tests for the walker
- `mypy --strict finderctl` — CI gate
- `ruff check` + `ruff format --check` + `black --check` — CI gates

### 15.2 Fixture Infrastructure (`tests/conftest.py`)
| Fixture | Provides |
|---|---|
| `tmp_finder_plist` | A real plistlib-generated temp plist mirroring the user's plist structure |
| `tmp_backup_dir` | Isolated `BACKUP_DIR` via env override |
| `mock_finder_process` | `FinderProcessService` double — `restart` is a no-op |
| `real_plist_io` | `PlistReader`/`PlistWriter` pointed at temp paths |
| `sample_plist_data` | Dict matching the user's macOS 26 plist (key sections) |
| `corrupt_plist` | A binary file that fails `plistlib.load()` |

### 15.3 Test Matrix

#### Unit Tests (target: 80% of test count)
| Test File | Scenarios |
|---|---|
| `test_discovery.py` | Flat dict; nested 10+ levels; list-of-dicts; all SEARCH_KEYS at root + nested; empty plist; non-dict root; None values; both `columns` formats (legacy dict + modern array); property test with Hypothesis (1000 random trees) |
| `test_models.py` | Frozen immutability; equality; `Change` diff generation; `BackupRecord` path parsing; `ApplyScope` enum exhaustiveness |
| `test_validation.py` | Label sanitization (10 valid, 10 invalid); `folder:<key>` format; timestamp parse/round-trip; field type checking |
| `test_exceptions.py` | Full hierarchy (`isinstance` chain); str()/repr(); pickling |

#### Integration Tests (target: 15% of test count)
| Test File | Scenarios |
|---|---|
| `test_backup_service.py` | Create → verify → list → prune → export; corrupt source raises `PlistError` + no backup file left behind; SHA-256 sidecar correctness |
| `test_settings_service.py` | Apply mutates correct scope only; `pre-apply` backup auto-created; read-back equals write; `ApplyScope.SPECIFIC` targets exact path; post-write verification failure triggers rollback |
| `test_cli.py` | All 6 commands × {success, error path exit code 2, `--json` shape validation}; Typer `CliRunner` |
| `test_plist_io.py` | Atomic write (temp file cleaned); parse error → `PlistParseError`; read missing → `PlistNotFoundError`; write to read-only dir → `PlistPermissionError` |
| `test_restore.py` | Restore from latest; restore by timestamp prefix; ambiguous match → exit 2; corrupt backup → exit 1; dry-run produces diff, no write |
| `test_doctor.py` | Healthy state; corrupt plist; missing backup; `doctor --fix` restores from backup |

#### Property-Based Tests (Hypothesis)
| Property | Invariant |
|---|---|
| Walker | For any generated tree, discovered sections == inserted sections; all `key_path` values are unique and valid |
| Apply/Verify | Apply field → verify field == expected (round-trip) |
| Backup/Restore | restore(backup(create_snapshot(plist))) == plist (deep equality) |

### 15.4 Coverage Targets
| Module | Line | Branch |
|---|---|---|
| `models.py` | 100% | 100% |
| `services/discovery.py` | 100% | 100% |
| `infrastructure/plist_io.py` | 100% | 95% |
| `services/backup.py` | 100% | 95% |
| `services/settings.py` | 100% | 95% |
| `cli.py` | 100% | 90% |
| **Overall** | **≥ 95%** | **≥ 90%** |

### 15.5 CI Pipeline (`.github/workflows/ci.yml`)
| Stage | Command | Gate |
|---|---|---|
| Lint | `ruff check finderctl tests` | Fail on any warning |
| Format | `ruff format --check finderctl tests` + `black --check finderctl tests` | Must be clean |
| Types | `mypy --strict finderctl` | Zero errors |
| Tests (Linux) | `pytest tests/ --cov=finderctl --cov-fail-under=95` | ≥ 95% |
| Tests (macOS) | Same, plus real-plist and `killall` integration tests | ≥ 95% |

---

## 16. Frozen Architecture — Final Word

This specification is **frozen**. All implementation work must
conform to the structure, data models, algorithms, safety invariants,
and testing requirements defined herein. Any change to:

- The exception hierarchy (`§`7 in ARCHITECTURE.md)
- The `SEARCH_KEYS` constant
- The backup-before-write invariant
- The atomic-write strategy
- The exit-code semantics

…requires an architecture review and a new spec version. The
`ARCHITECTURE.md` + `TECHNICAL_SPECIFICATION.md` pair is the single
source of truth.

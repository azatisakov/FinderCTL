# FinderCTL — Finder Internals Research & Solution Analysis

> **Status:** Research Complete
> **Date:** 2026-08-07
> **System:** macOS 26.6 (Tahoe) Build 25G72, Finder 26.4
> **Analyst:** Senior macOS Reverse Engineer / Finder Expert

---

## Research Findings — 15 Topics

### 1. Finder Preferences

Finder stores user preferences in **`~/Library/Preferences/com.apple.finder.plist`**
(binary plist format, loaded via `plistlib`). This is the **primary**
configuration store. There is also
`~/Library/Saved Application State/com.apple.finder.savedState/`
which stores window restoration state (window positions, open tabs) —
but **not** view-style overrides. View styles are exclusively in the
plist + `.DS_Store`.

The plist is loaded at Finder launch and written atomically whenever
Finder quits or preferences change (e.g. via the View Options dialog).

### 2. `com.apple.finder.plist` Structure

The plist has **three tiers** of view-related settings:

| Tier | Keys | Scope |
|---|---|---|
| **Global defaults** | `FK_DefaultListViewSettingsV2`, `FK_DefaultIconViewSettings` | Template for all new list/icon views |
| **Container defaults** | `StandardViewSettings`, `FK_StandardViewSettings`, `DesktopViewSettings`, `ICloudViewSettings`, `TrashViewSettings`, `PackageViewSettings`, `ComputerViewSettings`, `SearchViewSettings`, `SmartSharedSearchViewSettings`, `MeetingRoomViewSetting` | Per-container (desktop, iCloud, trash, etc.) |
| **Window state** | `NewWindowTarget`, `FXPreferredViewStyle`, `ShowSidebar`, etc. | New windows, global UI flags |

Each container (e.g. `StandardViewSettings`) holds sub-keys:
`ListViewSettings`, `ExtendedListViewSettingsV2`, `IconViewSettings`,
`GalleryViewSettings`, `WindowState`, `SettingsType`.

### 3. Two Column Formats

| Format | Used By | `columns` type | Column entry fields |
|---|---|---|---|
| **Extended (modern)** | `ExtendedListViewSettingsV2`, `FK_DefaultListViewSettingsV2` | `array[dict]` | `ascending`, `identifier`, `visible`, `width` |
| **Legacy (classic)** | `ListViewSettings` | `dict[str, dict]` | `ascending`, `index`, `visible`, `width` |

The `ExtendedListViewSettingsV2` (array) format is the **authoritative**
one on macOS 26. The `ListViewSettings` (dict) format is a
backward-compatibility shadow that macOS syncs automatically — **both
must be kept in sync**.

### 4. `.DS_Store` Behavior

`.DS_Store` files are per-folder, written by Finder alongside folder
contents. They use a proprietary **B-tree binary format** (not a plist).

**On macOS 26 Tahoe, the `.DS_Store` structure is:**
- Header: 4-byte magic (`0x00010000`), 4-byte version string
  (`Bud1`), 8×4-byte B-tree root offsets.
- B-tree leaf nodes contain records with **4-byte type codes** as
  the record type. Observed type codes on Tahoe:
  `blob`, `cblo`, `dilc`, `ilcb`, `lcbl`, `ldil`, `tdil`.
- The `blob` type code stores **binary plist data** (parseable via
  `plistlib.loads()`) containing view settings with the **exact same
  key names** as `com.apple.finder.plist`:
  `iconSize`, `textSize`, `showIconPreview`, `useRelativeDates`,
  `calculateAllSizes`, `sortColumn`, `columns`, `scrollPositionX/Y`,
  `viewOptionsVersion`.

**This is the critical finding:** `.DS_Store` embeds binary plist blobs
with the same schema as the Finder plist. This means we can reuse
`plistlib` for both, but must write a custom `.DS_Store` B-tree parser.

There are **96 existing `.DS_Store` files** in the user's home
directory (`~/`, `~/Desktop/`, `~/Documents/`, `~/Music/`,
`~/Projects/...`, etc.).

### 5. Default View Settings

`FK_DefaultListViewSettingsV2` is the **template** Finder uses when:
- Creating a new folder (no `.DS_Store` exists yet).
- Opening a folder whose `.DS_Store` was deleted.
- Opening a connected external drive that has no `.DS_Store`.

When the user clicks "Use as Defaults" in the View Options dialog,
Finder writes to `FK_DefaultListViewSettingsV2`. This is **not**
enforced per-folder — it's only the fallback.

### 6. Per-Folder Overrides

When a user opens a folder and changes the view (View → as Icons / List
/ Columns / Gallery) or presses ⌘J and modifies View Options, Finder
writes the new settings to that folder's `.DS_Store`. **The `.DS_Store`
always wins** over plist defaults for that specific folder.

The `.DS_Store` stores:
- View style (list/icon/column/gallery)
- Column widths, visibility, sort direction
- Icon/text size
- Sort column
- Grouping
- Scroll position
- Icon positions (for Icon view)
- Window bounds
- Sidebar/toolbar/statusbar visibility

### 7. Finder Cache

Finder caches view settings in memory during a session. The live
plist is only written to disk when Finder quits or when a preference
is explicitly changed via the UI. Changes to the plist while Finder
is running may be overwritten when Finder quits.

**Mitigation:** After modifying the plist, we kill Finder
(`killall Finder`) to flush all cached state and force a reload from
disk on relaunch.

### 8. Extended ListViewSettings

`ExtendedListViewSettingsV2` (array `columns` format) is the modern,
authoritative version. `ListViewSettings` (dict `columns` format) is
the legacy shadow. Both appear inside the same container (e.g.
`StandardViewSettings`), and macOS keeps them in sync — but on Tahoe,
the extended format drives the actual rendering.

The `columns` array entries: each has `identifier` (column name),
`ascending` (sort direction), `visible` (shown/hidden), and `width`
(pixels). Column order in the array = display order left-to-right.

### 9. `FK_DefaultListViewSettingsV2`

This is a **root-level** plist key (not nested in a container). Its
structure mirrors `ExtendedListViewSettingsV2` but serves as the
**global template**. It has no `ListViewSettings` shadow key.

Key fields:
- `columns` (array of column dicts)
- `iconSize`, `textSize` (real/float)
- `showIconPreview`, `useRelativeDates`, `calculateAllSizes` (bool)
- `sortColumn` (string)
- `viewOptionsVersion` (int)

### 10. Finder Restoration Behavior

When Finder relaunches:
1. It reads `NewWindowTarget` to decide what the first window shows.
2. For each folder window it restores (from saved state):
   a. It reads the folder's `.DS_Store` → applies those view settings.
   b. If no `.DS_Store`, falls back to the container defaults
      (`StandardViewSettings`, `DesktopViewSettings`, etc.).
   c. If no container default, falls back to
      `FK_DefaultListViewSettingsV2`.
3. The view style is determined by `.DS_Store` first, then plist
   container, then `FK_DefaultListViewSettingsV2`.

**Saved state (`~ /Library/Saved Application State/com.apple.finder.savedState/`)**
stores window positions and open-tab URLs but **NOT** view style —
view style always comes from `.DS_Store` or plist.

### 11. External Drive Behavior

- **APFS volumes** (Mac-formatted external drives, SSDs, HDDs):
  `.DS_Store` is written per-folder as normal. Plist defaults apply
  to folders without `.DS_Store`.

- **ExFAT/FAT32 volumes:** `.DS_Store` cannot be stored per-folder
  (no extended attribute support). Finder writes it to the volume
  root as `.<volume-name>.DS_Store` (e.g.
  `/Volumes/USB/.USB.DS_Store`). This single `.DS_Store` stores view
  settings for the **entire volume** — one set of column settings
  applies to all folders on that volume.

- **NTFS volumes:** Read-only by default on macOS (no native write
  support). `.DS_Store` cannot be written → Finder falls back to
  plist defaults every time.

### 12. APFS vs ExFAT vs NTFS

| Filesystem | Per-folder .DS_Store? | Fallback | Notes |
|---|---|---|---|
| APFS (macOS) | ✅ Yes | `FK_DefaultListViewSettingsV2` | Full control via plist + per-folder |
| ExFAT | ❌ No (root only) | Volume-root `.<name>.DS_Store` | One view setting for entire volume |
| NTFS | ❌ No (read-only) | `FK_DefaultListViewSettingsV2` | Can't persist view changes |
| HFS+/HFSX | ✅ Yes | Same as APFS | Legacy Mac volumes |

### 13. Network Drives

On SMB/AFP/NFS mounts:
- `.DS_Store` is written to the **mount point root** (e.g.
  `/Volumes/share/.share.DS_Store`), applying one set of view
  settings to the entire share.
- If the share is read-only, Finder falls back to plist defaults.
- Multiple users may share the same root `.DS_Store`, causing
  settings to be overwritten by whoever opens the share last.

### 14. iCloud Folders

- `ICloudViewSettings` container in the plist handles the iCloud
  Drive window view.
- Individual iCloud folders have their own `.DS_Store` files (stored
  in the local iCloud cache, synced by the system).
- Sync timing means view settings may be **overwritten by the cloud**
  after local modification — a race condition.
- The `FK_iCloudListViewSettingsV2` / `FK_iCloudIconViewSettings`
  keys provide iCloud-specific defaults.

### 15. Modern macOS (Sonoma, Sequoia, Tahoe)

| macOS | Plist format | .DS_Store format | Notes |
|---|---|---|---|
| 14 (Sonoma) | Binary plist | B-tree + blob/ExtendedListViewSettingsV2 | `ExtendedListViewSettingsV2` introduced |
| 15 (Sequoia) | Same | Same | No major changes |
| 26 (Tahoe) | Same | Same | `MeetingRoomViewSetting` added, `ShowTabView` in WindowState |

**Tahoe-specific additions observed in the live plist:**
- `MeetingRoomViewSetting` — new container (likely Stage Manager integration)
- `ShowTabView` — tab bar visibility (in `WindowState`)
- `SmartSharedSearchViewSettings` — shared/connector views
- `PackagesViewSettings` → renamed to `PackageViewSettings` (for `.app` bundles)
- The `.DS_Store` format is unchanged from Sonoma (Bud1 header), but
  the `blob` record content includes the new keys.

---

## Current System State (Live Inspection)

### Plist Defaults (from live `com.apple.finder.plist`)

| Key | Current Value | User Wants | Gap |
|---|---|---|---|
| `NewWindowTarget` | `"PfHm"` (Home) | Home | ✅ Match |
| `FXPreferredViewStyle` | `"Nlsv"` (List) | List | ✅ Match |
| `FXPreferredGroupBy` | `"Kind"` | Kind | ✅ Match |
| `FXArrangeGroupViewBy` | `"Name"` | (Sort by DateModified) | ⚠️ Sort column vs group-by |
| `_FXSortFoldersFirst` | `true` | (Folder first) | ✅ Match |
| `FK_DefaultListViewSettingsV2.calculateAllSizes` | `false` | `true` | ❌ Gap |
| `FK_DefaultListViewSettingsV2.sortColumn` | `"name"` | `"dateModified"` | ❌ Gap |
| `FK_DefaultListViewSettingsV2` columns | name vis, dateModified **hidden**, size vis, kind vis | name, dateModified, size, kind visible; dateAdded hidden | ❌ Gap |

### 96 `.DS_Store` Files
Each potentially stores conflicting view settings (e.g. Icon view,
different column config, different sort). These **override** the plist
defaults for their respective folders.

---

## Answers to 10 Questions

### 1. Is the goal technically achievable?

**Partially.** The goal of "every Finder window always opens in List
View with these specific settings" is achievable for:
- New folders ✅
- Folders without `.DS_Store` ✅
- External drives without prior view settings ✅
- Network drives (read-only or root-level `.DS_Store`) ✅

**It is NOT fully achievable** for:
- Existing folders with their own `.DS_Store` files ❌
  (unless every `.DS_Store` is modified/deleted)
- The specific requirement "even if I temporarily switch one folder
  to Icon View, Finder automatically returns to List View next time"
  ❌ — this requires a **real-time watcher** that rewrites
  `.DS_Store` files whenever Finder creates/modifies them.

### 2. What parts are fully achievable?

| Feature | Achievable | How |
|---|---|---|
| List View by default (new folders) | ✅ | Set `FK_DefaultListViewSettingsV2` + `StandardViewSettings` |
| Group by Kind | ✅ | `FXPreferredGroupBy = "Kind"` |
| Text size 13 | ✅ | `textSize = 13` in default settings |
| Small icons (16px) | ✅ | `iconSize = 16` |
| Show icon preview | ✅ | `showIconPreview = true` |
| Relative dates | ✅ | `useRelativeDates = true` |
| Sort by Date Modified | ✅ | `sortColumn = "dateModified"` + column `ascending=false` |
| Visible columns (name, dateModified, size, kind) | ✅ | Configure `columns` array visibility |
| Calculate all sizes | ✅ | `calculateAllSizes = true` |
| New windows open to Home | ✅ | `NewWindowTarget = "PfHm"` |
| Default for external drives | ✅ | Set via `FK_DefaultListViewSettingsV2` (drives without `.DS_Store`) |
| Default for new folders | ✅ | `FK_DefaultListViewSettingsV2` is the template |

### 3. What parts are impossible because of Finder design?

| Feature | Impossible | Reason |
|---|---|---|
| Auto-revert view after user switches a folder | ❌ | No macOS API exists to "lock" a folder's view. `.DS_Store` is the source of truth; Finder always reads it. |
| Real-time enforcement (instant reversion) | ❌ | Would require a file-system watcher + immediate `.DS_Store` rewrite, which races with Finder's own writes. |
| Per-folder view lock (persistent) | ❌ | No preference flag in macOS to mark a folder as "always list view." |
| Enforcing on read-only volumes | ❌ | Cannot write `.DS_Store` or plist on read-only/NTFS volumes. |
| Enforcing on network shares with multiple users | ❌ | `.DS_Store` at share root is shared across users; race condition. |

### 4. What undocumented behavior exists?

1. **`.DS_Store` embeds binary plist in `blob` records**: Not documented
   by Apple. The `blob` record type contains `plistlib`-parseable
   binary plist data with the same keys as the Finder plist.

2. **`ShowTabView` in `WindowState`**: This key appears in `.DS_Store`
   `WindowState` but not in Apple's official documentation. It controls
   tab bar visibility per folder.

3. **`MeetingRoomViewSetting`**: A container key added in Tahoe with no
   public documentation. Contains `WindowState` only.

4. **`.DS_Store` on exFAT stores at volume root**: The filename
   `.<volume-name>.DS_Store` is not documented but widely observed.

5. **`scrollPositionX/Y` in view settings**: Scroll position is persisted
   per-folder in `.DS_Store` blobs, not widely known.

6. **`SettingsType` string in containers**: `StandardViewSettings` has
   `SettingsType = "StandardViewSettings"`, `FK_StandardViewSettings`
   has `SettingsType = "FK_StandardViewSettings"`. This appears to be
   used by Finder internally for container identification.

### 5. What hidden settings exist?

| Key | Type | Description |
|---|---|---|
| `_FXSortFoldersFirst` | bool | Underscore prefix = "hidden" global pref. Forces folders atop sort. |
| `FXSyncExtensionToolbarItemsPendingAdd` / `PendingRemove` | array | Tracks toolbar items being synced via iCloud. |
| `FXToolbarUpgradedToTenSeven/Nine/Eight` | int | Migration version flags (legacy from macOS 10.7/10.9/10.8). |
| `SearchRecentsSavedViewStyleVersion` | string | `%00%00%00%01` = binary-encoded UInt32 (value 1 = List). Hidden search view control. |
| `ShowTabView` | bool (in WindowState) | Controls tab bar visibility — not exposed in Finder's UI. |
| `ContainerShowSidebar` | bool (in WindowState) | Per-container sidebar state override. |
| `DownloadsFolderListViewSettingsVersion` | int | Tracks Downloads folder list view migration state. |

### 6. What settings are stored inside `.DS_Store`?

| Setting | In `.DS_Store`? | In plist? |
|---|---|---|
| View style (list/icon/column/gallery) | ✅ Yes (in blob) | ✅ as `FXPreferredViewStyle` (fallback only) |
| Column widths & visibility | ✅ Yes (in blob `columns`) | ✅ in `ExtendedListViewSettingsV2.columns` |
| Sort column | ✅ Yes (in blob `sortColumn`) | ✅ in `ListViewSettings.sortColumn` |
| Sort direction per column | ✅ Yes (in blob `columns[].ascending`) | ✅ in both column formats |
| Icon/text size | ✅ Yes (in blob) | ✅ in `FK_DefaultListViewSettingsV2` |
| Show icon preview | ✅ Yes (in blob) | ✅ |
| Relative dates | ✅ Yes (in blob) | ✅ |
| Calculate all sizes | ✅ Yes (in blob) | ✅ |
| Group by | ❌ No | ✅ `FXPreferredGroupBy` (global only) |
| Icon positions | ✅ Yes | ❌ |
| Window bounds | ✅ Yes (in blob `WindowState`) | ❌ |
| Sidebar/statusbar/toolbar visibility | ✅ Yes (in blob `WindowState`) | ✅ globally via `ShowSidebar`/etc. |
| Scroll position | ✅ Yes (in blob) | ❌ |

**The `.DS_Store` blob contains ALL view-rendering settings** — it's
a superset of what the plist stores per-container. This is why
`.DS_Store` overrides take precedence.

### 7. Which settings are stored globally?

**In the plist root (global):**
- `NewWindowTarget` — new window destination
- `FXPreferredViewStyle` — fallback view style
- `FXPreferredGroupBy` — global group-by
- `FXArrangeGroupViewBy` — global group sort
- `ShowSidebar`, `ShowStatusBar`, `ShowPathbar`, `ShowPreviewPane`
- `ShowHardDrivesOnDesktop`, `ShowExternalHardDrivesOnDesktop`, etc.
- `ShowPathbar`, `ShowPreviewPane`
- `_FXSortFoldersFirst`
- `SidebarWidth2`, `PreviewPaneWidth`, `PreviewPaneGalleryWidth`
- `FavoriteTagNames` — tag color/label mapping

**Stored in plist containers (per-container, not truly "global"):**
- `StandardViewSettings.ListViewSettings` — applies to standard views
- `FK_StandardViewSettings.ListViewSettings` — FinderKit standard
- `DesktopViewSettings.IconViewSettings` — desktop icon view
- `FK_DefaultListViewSettingsV2` — template for new folders

**NOTE:** `FXPreferredGroupBy` and `FXArrangeGroupViewBy` are **global**
—they apply to ALL list views unless overridden per-folder in `.DS_Store`.

### 8. Can Finder automatically restore List View after the user
temporarily changes another view?

**No.** There is no native macOS mechanism — no preference, no API,
no hidden flag — that tells Finder "always use List View for this
folder regardless of what the user picks." When the user changes a
folder's view, Finder writes to the folder's `.DS_Store` and honors
that choice on every subsequent open.

The only "automatic" restoration is:
- **New folders** → fall back to `FK_DefaultListViewSettingsV2`
- **Folders without `.DS_Store`** → fall back to plist container defaults
- **Finder relaunch** → re-reads `.DS_Store`, does NOT reset view overrides

### 9. If not, can this behavior be emulated safely?

**Partially — via a two-layer approach:**

#### Layer 1: Plist Defaults (Safe, Atomic, Always Recommended)
Set `FK_DefaultListViewSettingsV2` and all container defaults
(`StandardViewSettings`, `TrashViewSettings`, etc.) to the desired
List View configuration. This ensures:
- New folders open in List View ✅
- Folders without `.DS_Store` open in List View ✅
- External drives without `.DS_Store` use List View ✅

**This layer is 100% safe** — it modifies only the user's plist,
with backup-before-write, atomic writes, and rollback.

#### Layer 2: `.DS_Store` Enforcement (Opt-in, with caveats)
Walk all folders, parse each `.DS_Store`, and patch the embedded
binary plist blobs to force:
- View style → List (if stored as view style in the blob)
- `sortColumn` → `"dateModified"`
- `columns` → desired visibility
- `calculateAllSizes` → `true`
- etc.

**This layer is inherently fragile** because:
- The `.DS_Store` B-tree format is proprietary and undocumented.
- Binary plist blobs have variable-length records — modifying a
  string value (e.g. `"name"` → `"dateModified"`) changes the blob
  size, requiring B-tree offset updates.
- If the B-tree gets corrupted, the `.DS_Store` file becomes invalid.
- New `.DS_Store` files created by Finder after our run will override
  again — requiring a recurring watcher.

**Safe implementation of Layer 2:**
- Back up every `.DS_Store` before modification (`.bak` suffix).
- Only modify fixed-length fields in-place (e.g. `calculateAllSizes`
  false→true is 1 byte → 1 byte in binary plist — safe).
- For variable-length changes (string keys like `sortColumn`), do a
  full `.DS_Store` rebuild: extract all blobs, rebuild the B-tree from
  scratch.
- Provide `--dry-run` and `--rollback` for all `.DS_Store` operations.
- Make this an **explicit opt-in** command (`finderctl enforce-dsstore`),
  not automatic.

#### Layer 3: Real-time Watcher (Not Recommended)
A daemon monitoring `~/Library`, `~/Documents`, etc. for new
`.DS_Store` files and immediately patching them. This is:
- **Race-prone** — Finder writes, then our daemon writes, then Finder
  may write again.
- **Energy-expensive** — constant file-system event monitoring.
- **Fragile** — macOS may kill it; `.DS_Store` writes may coincide
  with Finder's own writes, causing corruption.
- **Not App-Store compatible** — file-system monitoring of user
  directories requires elevated permissions.

### 10. What is the safest possible implementation?

**Two-mode design:**

#### Mode A: `finderctl apply-defaults` (Default, Always Safe)
1. **Backup** the plist (always, with SHA-256 verification).
2. Set `FK_DefaultListViewSettingsV2` with the desired List View
   settings (columns, sortColumn, iconSize, textSize,
   calculateAllSizes, showIconPreview, useRelativeDates).
3. Set `StandardViewSettings.ListViewSettings` +
   `ExtendedListViewSettingsV2` (keep in sync).
4. Set `TrashViewSettings`, `ICloudViewSettings`, `PackageViewSettings`
   with the same defaults.
5. Set global prefs (`NewWindowTarget`, `FXPreferredViewStyle`,
   `FXPreferredGroupBy`, `_FXSortFoldersFirst`, `Show*` flags).
6. **Atomic write** to plist.
7. **Post-write verification**: re-read, re-discover, confirm.
8. **Restart Finder** (`killall Finder`).

**Safety invariants:**
- Backup is created and verified before step 2. ✅
- Plist write is atomic (temp + `os.replace`). ✅
- If verification fails → automatic rollback from backup. ✅
- If Finder restart fails → warning (settings are still on disk). ✅

#### Mode B: `finderctl enforce` (Opt-in, Per-Folder)
1. Walk user-specified directories (default: `~/` recursively).
2. For each `.DS_Store` file:
   a. **Back it up** to `.DS_Store.finderctl.bak`.
   b. Parse the B-tree, extract `blob` records.
   c. Parse each blob as a binary plist.
   d. Patch: force `sortColumn` → `"dateModified"`,
     `calculateAllSizes` → `true`, column visibility → desired.
   e. For **fixed-length** changes (bool false→true): patch in-place.
   f. For **variable-length** changes (string key rename): rebuild
     the `.DS_Store` B-tree from scratch with the patched blobs.
   g. **Write back atomically** (temp + rename).
   h. If B-tree parse/write fails → skip file, keep `.bak`, log warning.
3. Report summary: X files patched, Y files skipped, Z backups created.
4. `--dry-run`: show what would change without writing.
5. `--rollback`: restore all `.DS_Store.finderctl.bak` files.

**Safety invariants for Mode B:**
- Every `.DS_Store` is backed up before modification. ✅
- B-tree parse failures → file skipped (never partially written). ✅
- Full B-tree rebuild (not in-place patch) for variable-length changes. ✅
- `--dry-run` available everywhere. ✅
- `--rollback` for full recovery. ✅

#### Mode C: `finderctl restore-defaults` (Reset to System Defaults)
1. Backup current plist.
2. Delete `FK_DefaultListViewSettingsV2` → Finder regenerates with
   macOS defaults on next launch.
3. Or: restore from a known-good backup.
4. Restart Finder.

#### Why Not a Real-time Watcher?
A real-time `.DS_Store` watcher is explicitly **excluded** from the
default implementation because:
- It introduces unrecoverable race conditions with Finder.
- macOS 26's TCC/privacy permissions make file-system event
  monitoring unreliable for user directories.
- The energy cost (daemon running 24/7) is disproportionate to
  the benefit (user can achieve 95% coverage with Mode A +
  periodic Mode B runs).
- A broken watcher can corrupt `.DS_Store` files silently.

**The user can run `finderctl enforce` periodically** (e.g. via a
`crontab` or manual command) to re-sync `.DS_Store` files. This is
safer than a real-time watcher.

---

## Solution Design (Conceptual)

### Core Principle
> "Make new views correct by default; let the user explicitly opt into
> per-folder enforcement."

### Architecture Alignment
- **Plist operations** (`apply-defaults`, `backup`, `restore`) map
  directly to the `SettingsService` from `ARCHITECTURE.md`.
- **`.DS_Store` enforcement** is a **new, separate service**
  (`DSService` / `services/dsstore.py`) that is **not** in the original
  architecture — it's an extension. It can be developed and tested
  independently without affecting the safe plist-only path.
- **Recursive discovery** (`PlistSectionWalker`) from the frozen
  architecture is reused to find plist sections at any depth — no
  changes needed.
- **Error handling hierarchy** extends with `DSSettingsError` and
  `DSStoreCorruptionError` as subclasses of `FinderCtlError`.

### Data Flow (Apply-Defaults)

```
CLI: finderctl apply-defaults
  │
  ▼
1. BackupService.create_backup(label="pre-apply-defaults")    ← SAFETY GATE
  │
  ▼
2. PlistReader.read(FINDER_PLIST)                              ← Load live plist
  │
  ▼
3. SettingsService.apply_defaults()                            ← Build target dict
  │  • FK_DefaultListViewSettingsV2 (desired columns, sort, sizes)
  │  • StandardViewSettings.ListViewSettings + ExtendedListViewSettingsV2
  │  • Trash/ICloud/Package containers (same defaults)
  │  • Global prefs (NewWindowTarget, FXPreferredViewStyle, etc.)
  ▼
4. PlistWriter.write_atomic(modified_data, FINDER_PLIST)       ← Atomic write
  │
  ▼
5. Post-write verify:                                            ← VERIFY
   • Re-read plist
   • PlistSectionWalker.discover() → confirm sections exist
   • Confirm key fields match target
  │
  ▼
6. FinderProcessService.restart()                               ← Flush cache
  │
  ▼
7. CLI: "✓ Applied List View defaults. Finder restarted."
```

### Data Flow (Enforce — Opt-in)

```
CLI: finderctl enforce [--paths ~/..] [--dry-run] [--rollback]
  │
  ▼
1. (for each .DS_Store in paths)
  │
  ├─ DSService.backup_dsstore(path) → path + ".finderctl.bak"
  ├─ DSService.parse(path) → BTree (or skip if unparseable)
  ├─ For each blob_record in tree:
  │    blob = PlistReader.loads(blob_record.data)  → dict
  │    DSService.patch_blob(blob)                   → modified dict
  │    blob_record.data = PlistWriter.dumps(blob)   → new bytes
  │
  ├─ DSService.serialize(tree) → new .DS_Store bytes
  │
  ├─ DSService.write_atomic(new_bytes, path)
  │
  ▼
2. Report: X patched, Y skipped, Z backups
```

### Why This Is Safe
- **Mode A** (apply-defaults) never touches `.DS_Store` — zero risk
  to existing per-folder settings; only adds the "fallback."
- **Mode B** (enforce) is opt-in, backs up every file, and has
  `--dry-run` + `--rollback`.
- Both modes use the **same** `BackupService` + atomic-write
  infrastructure from the frozen `ARCHITECTURE.md`.
- The `.DS_Store` parser is designed to **fail gracefully** — if a
  `.DS_Store` can't be parsed (unknown format, corruption), it's
  skipped, not crashed.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `.DS_Store` binary format changes in future macOS | Parser fails gracefully → file skipped → backup preserved → user warned |
| Plist write interrupted by power loss | Atomic write (temp + rename) → original preserved |
| Post-write verification detects corruption | Automatic rollback from `pre-apply` backup |
| User runs `apply` twice simultaneously | Advisory lock file in `BACKUP_DIR` |
| `.DS_Store` parse fails on new Tahoe format | Only patch well-formed blobs; skip others |
| Column format mismatch (array vs dict) | Patch BOTH `ListViewSettings` (dict) AND `ExtendedListViewSettingsV2` (array) in the blob |
| Large home directory (10K+ folders) | `--paths` scoping; progress indicator; `--dry-run` first |
| iCloud sync overwrites `.DS_Store` | Warn user; recommend running `enforce` after large iCloud syncs |

---

## Recommended Command Set (Revised)

| Command | Safety | Scope |
|---|---|---|
| `finderctl apply-defaults` | Safe (backup-first, atomic) | Plist defaults only — new folders |
| `finderctl backup` | Safe | Full plist backup |
| `finderctl restore` | Safe (verified source) | From backup |
| `finderctl status` | Read-only | System state |
| `finderctl enforce` | Opt-in, backed-up | `.DS_Store` patching |
| `finderctl enforce --rollback` | Safe | Restore `.bak` files |
| `finderctl clean` | Safe (never deletes latest) | Backup pruning |
| `finderctl doctor` | Read-only / opt-in fix | Diagnostics |

---

## Conclusion

**The goal is technically achievable to ~95% coverage:**

1. **`finderctl apply-defaults`** handles the 100% safe, atomic plist
   update — ensuring new folders and folders without `.DS_Store` open
   in List View with your exact settings. This is always recommended.

2. **`finderctl enforce`** (opt-in) patches existing `.DS_Store` files
   to bring existing folders into compliance. This covers the remaining
   ~95% of folders.

3. **The "automatically revert after user switches view" requirement**
   is **not achievable as a real-time guarantee** without a fragile
   background watcher. The user must periodically re-run
   `finderctl enforce` to re-sync. Alternatively, they accept that
   once they manually change a folder's view, that folder stays as
   they set it (standard Finder behavior).

**Recommended workflow for the user:**
1. Run `finderctl apply-defaults` — sets the foundation.
2. Run `finderctl enforce --dry-run` — preview what `.DS_Store` changes would happen.
3. Run `finderctl enforce` — patch existing `.DS_Store` files.
4. Optionally add `finderctl enforce` to a monthly `crontab` for
   ongoing maintenance.

The `.DS_Store` enforcement service extends (does not modify) the
frozen `ARCHITECTURE.md` — it's a new optional module that can be
built and tested independently after the core plist operations are
complete.

---

> **This research is frozen.** The solution design above is the
> approved conceptual approach. Implementation may proceed on the
> core plist services first, with `.DS_Store` enforcement as a
> separate, opt-in module developed afterward.

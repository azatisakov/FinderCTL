# FinderCTL

Manage macOS Finder preferences safely with atomic backups, SHA-256 verification, and dry-run previews.

## Installation

```bash
uv sync
source .venv/bin/activate
```

## Commands

| Command | Description |
|--------|-------------|
| `finderctl status [--json]` | Show current Finder plist status, macOS/Finder versions, backup count |
| `finderctl backup [--label NAME] [--no-verify] [--json]` | Create a verified backup of the Finder plist |
| `finderctl restore [LABEL] [--restart/--no-restart] [--dry-run] [--json]` | Restore from a backup by label or latest |
| `finderctl apply FIELD VALUE [--scope SCOPE] [--no-restart] [--dry-run] [--json]` | Apply a single setting to a scoped container |
| `finderctl apply-defaults [--no-restart] [--dry-run] [--json]` | Apply full default List View configuration |
| `finderctl clean [--keep N] [--verify] [--dry-run] [--json]` | Prune old/invalid backups |
| `finderctl doctor [--fix] [--json]` | Run diagnostics on plist, backups, Finder process |
| `finderctl enforce [-p PATH] [--dry-run] [--rollback] [--json]` | Enforce List View settings across `.DS_Store` files (opt-in) |

### Global options

| Flag | Description |
|------|-------------|
| `--verbose / -v` | Enable debug logging to stderr |
| `--quiet / -q` | Suppress all but critical output |
| `--json` | Emit JSON to stdout instead of human-readable text |
| `--config / -c PATH` | Alternate config file path |

## Configuration

All defaults are defined in `finderctl/config.py`:

### `DESIRED_GLOBAL_PREFS`
Global Finder preferences applied to all containers:
```python
{
    "NewWindowTarget": "PfHm",         # Open new windows in Home folder
    "FXPreferredViewStyle": "Nlsv",     # Default to List view
    "_FXSortFoldersFirst": True,        # Sort folders before files
    "ShowSidebar": True,
    "ShowStatusBar": True,
    ...
}
```

### `DESIRED_DEFAULT_LIST_VIEW`
List View settings template applied to every container:
```python
{
    "sortColumn": "dateModified",       # Sort by modification date
    "calculateAllSizes": True,           # Show calculated folder sizes
    "columns": [                        # 12 standard columns
        {"identifier": "name", "visible": True, "width": 187},
        {"identifier": "dateModified", "visible": True, "width": 181},
        ...
    ],
}
```

### `ALLOWED_FIELDS`
Fields permitted for `finderctl apply`:
```python
{"sortColumn", "calculateAllSizes", "showIconPreview",
 "useRelativeDates", "textSize", "iconSize", "viewOptionsVersion"}
```

### `LIST_VIEW_CONTAINERS`
Containers affected by `apply-defaults`:
```python
("StandardViewSettings", "FK_StandardViewSettings",
 "ICloudViewSettings", "TrashViewSettings")
```

## Changing Defaults

1. Edit the desired dict in `finderctl/config.py`
2. Preview changes:
   ```bash
   finderctl apply-defaults --dry-run --json
   ```
3. Apply:
   ```bash
   finderctl apply-defaults --json
   ```

A backup is automatically created before every write.

## Apply Single Setting

```bash
# Scope options: default|all|standard|desktop|icloud|trash|package|folder:<key>
finderctl apply --scope all sortColumn dateModified --no-restart
```

## Backup Management

```bash
finderctl backup --label pre-change
finderctl clean --keep 5 --verify   # Keep 5 most recent, re-verify before pruning
finderctl restore pre-change        # Restore by label
```

Backups are stored in `~/.finderctl/backups/` with `.sha256` sidecar files.

## DS_Store Enforcement (Layer B)

Opt-in command for patching `.DS_Store` files across a folder hierarchy:

```bash
finderctl enforce -p ~/Documents --dry-run --json
finderctl enforce -p ~/Documents        # Apply changes
finderctl enforce -p ~/Documents --rollback  # Restore from .finderctl.bak
```

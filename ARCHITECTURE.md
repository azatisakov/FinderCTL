# FinderCTL — Architecture Specification

> **Status:** Frozen
> **Python:** 3.13+
> **Last updated:** 2026-08-07

---

## 1. Overview

FinderCTL is a production-grade CLI utility that manages macOS Finder
preferences and view settings safely. It operates on the Finder
`com.apple.finder.plist` file, manipulating `ListViewSettings`,
`ExtendedListViewSettingsV2`, and `FK_DefaultListViewSettingsV2`
sections without ever modifying the live plist before a verified
backup exists.

### Goals

- Safe — never mutate the live plist without a prior backup.
- Discover — recursively find every view-settings section in the plist.
- Extensible — easy to add new settings types or commands for future
  macOS versions.
- Production — full type safety, structured logging, comprehensive
  error handling, and a complete test suite.
- GitHub-ready — reproducible tooling, CI configuration, and
  contribution guidelines.

### Non-goals

- Editing Finder UI in real-time via AppleScript/UI-Scripting.
- Managing non-plist Finder configuration (e.g. dock, gestures).
- Cross-platform support (macOS only by design).

---

## 2. Architecture Principles

| Principle | Application |
|---|---|
| **Single Responsibility** | Each module, class, and service has one reason to change. |
| **Open/Closed** | Commands are registered via Typer; new commands plug in without modifying the core. New `PlistKey` matchers extend discovery without changing the walker. |
| **Liskov Substitution** | All service interfaces are abstract; concrete implementations are freely swappable (e.g. a mock plist store in tests). |
| **Interface Segregation** | Narrow, focused interfaces (`BackupService` ≠ `SettingsService` ≠ `FinderProcessService`). |
| **Dependency Inversion** | High-level use-cases depend on abstract ports; infrastructure implements them. |
| **Fail Fast** | Errors surface immediately; the live plist is never modified before a backup is verified. |

---

## 3. Target Module Structure

```
finderctl/
├── __init__.py              # Package metadata (__version__, __all__)
├── cli.py                   # Typer app + command registration + entry point
├── config.py                # Paths, constants, defaults (frozen at module load)
├── exceptions.py            # Full exception hierarchy
├── models.py                # Immutable domain models / value objects
├── logger.py                # Logging configuration (structlog-style or stdlib)
│
├── services/
│   ├── __init__.py
│   ├── backup.py            # Backup lifecycle: create, list, verify, prune
│   ├── settings.py          # Settings CRUD: read, write, query, apply
│   ├── discovery.py         # Recursive plist section discovery (walker)
│   ├── finder_process.py    # Finder process: restart, kill, version detection
│   └── environment.py       # System info: macOS version, Finder version, paths
│
├── infrastructure/
│   ├── __init__.py
│   ├── plist_io.py          # Low-level plistlib read/write (sync I/O)
│   ├── backup_storage.py     # Backup file naming, path generation, pruning
│   └── process_runner.py    # subprocess abstractions for `killall`, `defaults`
│
├── utils/
│   ├── __init__.py
│   ├── timestamps.py        # Timestamp formatting / parsing for backups
│   └── validation.py        # Input validators (backup names, paths)
│
├── dsstore.py               # DS_Store parsing utilities (legacy / future use)
└── plist.py                 # Public plist helper facade (re-exports from infra)
tests/
├── __init__.py
├── conftest.py               # Pytest fixtures (temp plists, mock Finder)
├── unit/
│   ├── test_models.py
│   ├── test_discovery.py
│   ├── test_validation.py
│   └── test_exceptions.py
├── integration/
│   ├── test_backup_service.py
│   ├── test_settings_service.py
│   ├── test_cli.py
│   └── test_plist_io.py
└── fixtures/
    ├── sample_plist.json     # Serialized plist fixture
    └── corrupted_plist.plist  # For error-path tests
```

---

## 4. Module Responsibilities

### `finderctl/__init__.py`
Houses `__version__`, `__all__`, and a lazy-import guard so that
`import finderctl` is side-effect free (no logging config on import).

### `finderctl/cli.py`
Typer application factory `create_app()` that registers all six
commands. Each command is a thin orchestrator: parse args → call the
appropriate service → format output → exit with a status code. The
entry point `app = create_app()` is wired to the `[project.scripts]`
console script in `pyproject.toml`.

### `finderctl/config.py`
Frozen constants loaded at import time using `pathlib.Path`. Contains:
- `APP_NAME`, `APP_VERSION`
- `HOME`, `FINDER_PLIST`, `BACKUP_DIR`, `XML_DIR`, `LOG_DIR`
- `DEFAULT_SETTINGS` (the default view-settings dict)
- `SEARCH_KEYS` — tuple of plist key names to discover recursively
- `MAX_BACKUPS` — retention limit for the `clean` command
- Environment-variable overrides for all paths (for testing)

### `finderctl/exceptions.py`
Full exception hierarchy (see §7). Every domain error is a subclass of
`FinderCtlError`. Infrastructure errors (`PlistIOError`) are distinct
from domain errors (`ApplyError`).

### `finderctl/models.py`
Immutable dataclasses / frozen value objects: `ViewSettings`,
`FolderView`, `BackupRecord`, `SystemState`, `ValidationReport`.
All carry `__post_init__` validation. No I/O.

### `finderctl/logger.py`
`configure_logging(level, stream)` — sets up structured logging with
`rich` or `logging`. Exposes a module-level `get_logger()` factory
that returns a child logger prefixed with `"finderctl"`.

### `finderctl/services/backup.py`
`BackupService` — creates, lists, verifies, and prunes backups.
**Guarantee:** backup creation always verifies the copy by re-reading
it before reporting success.

### `finderctl/services/settings.py`
`SettingsService` — reads, writes, and applies Finder view settings
via the `PlistStore` port. Enforces the **safety contract**: every
public write method calls `BackupService.create_backup()` first.

### `finderctl/services/discovery.py`
`PlistSectionWalker` — recursively traverses any nested `dict`/`list`
structure produced by `plistlib.load()` and yields every path that
matches a `SEARCH_KEYS` entry. Returns `SectionLocation` value
objects (key path + data).

### `finderctl/services/finder_process.py`
`FinderProcessService` — detects macOS/Finder version, restarts
Finder (`killall Finder`), waits for relaunch, and reports process
state. Used only by `apply` to trigger a refresh.

### `finderctl/services/environment.py`
`EnvironmentService` — resolves system paths, checks that the
Finder plist exists and is readable, detects virtualization/sandbox
constraints. Returns `SystemState`.

### `finderctl/infrastructure/plist_io.py`
`PlistFileReader` / `PlistFileWriter` — thin wrappers around
`plistlib.load()` / `plistlib.dump()` with atomic-write semantics
(write to temp file → `os.replace`). Raises `PlistIOError` on any
I/O failure.

### `finderctl/infrastructure/backup_storage.py`
`BackupNaming` — generates deterministic timestamp-based filenames,
parses timestamps from existing backup files, and enforces
`MAX_BACKUPS` retention.

### `finderctl/infrastructure/process_runner.py`
`SubprocessRunner` — a minimal `subprocess.run` wrapper with
timeout, capturing, and structured error translation. Used by
`FinderProcessService`.

### `finderctl/utils/timestamps.py`, `validation.py`
Pure helper functions: `format_backup_timestamp()`,
`parse_backup_timestamp()`, `validate_backup_name()`,
`validate_folder_path()`.

### `finderctl/dsstore.py`, `finderctl/plist.py`
`plist.py` is a public facade re-exporting high-level helpers from
`infrastructure.plist_io` and `services.discovery` for backward
compatibility. `dsstore.py` provides optional `.DS_Store` parsing
for future scope creep.

---

## 5. Domain Models

All models live in `models.py` and are **frozen dataclasses** with
`slots=True` where supported. They are pure data — no I/O, no
validation against live system state.

```python
@dataclass(frozen=True, slots=True)
class ViewSettings:
    """A single Finder view-settings dictionary (the value at a
    SEARCH_KEYS node in the plist)."""

    key_name: str  # "ListViewSettings" | "ExtendedListViewSettingsV2" | etc.
    properties: dict[str, Any]  # raw plist dict for this section
    container: str | None  # the enclosing folder/bookmark key, if any


@dataclass(frozen=True, slots=True)
class FolderView:
    """A folder's complete set of view settings across all known
    SEARCH_KEYS, discovered at a specific plist path."""

    folder_key: str  # the plist key representing the folder
    settings: list[ViewSettings]  # one entry per discovered SEARCH_KEYS node


@dataclass(frozen=True, slots=True)
class SectionLocation:
    """Result of recursive discovery — identifies where a section
    lives in the plist tree."""

    key_path: tuple[str, ...]  # e.g. ("Root", "Folder0", "ListViewSettings")
    data: dict[str, Any]  # the section's dict value


@dataclass(frozen=True, slots=True)
class BackupRecord:
    """Metadata for a single backup file."""

    path: Path
    timestamp: datetime
    size_bytes: int
    sha256: str
    is_valid: bool  # verified at creation or during `clean`/`doctor`


@dataclass(frozen=True, slots=True)
class SystemState:
    """Snapshot of the current system / Finder / plist state."""

    finder_plist_exists: bool
    finder_plist_readable: bool
    finder_running: bool
    macos_version: str
    finder_version: str | None
    plist_modified_at: datetime | None
    backup_count: int
    latest_backup: BackupRecord | None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Outcome of validating a proposed settings change."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
```

---

## 6. Service Layer & Public Interfaces

### 6.1 `BackupService`  (`services/backup.py`)

```python
class BackupService:
    def __init__(self, reader: PlistReader, storage: BackupStorage) -> None: ...

    def create_backup(self, *, label: str | None = None) -> BackupRecord: ...
    def list_backups(self) -> list[BackupRecord]: ...
    def verify_backup(self, record: BackupRecord) -> bool: ...
    def get_latest(self) -> BackupRecord | None: ...
    def prune(self, keep: int = MAX_BACKUPS) -> list[BackupRecord]: ...
    def export(self, dest: Path) -> Path: ...
```

**Contract:** `create_backup` reads the live plist via `PlistReader`,
writes an atomic copy to `BACKUP_DIR`, computes a SHA-256 hash, and
verifies the written file by re-reading and re-hashing it. Only then
does it return a `BackupRecord` with `is_valid=True`.

### 6.2 `SettingsService`  (`services/settings.py`)

```python
class SettingsService:
    def __init__(
        self,
        reader: PlistReader,
        writer: PlistWriter,
        backup: BackupService,
    ) -> None: ...

    def read_all(self) -> list[FolderView]: ...
    def read_default(self) -> ViewSettings | None: ...
    def read_folder(self, folder_key: str) -> FolderView | None: ...
    def apply(
        self,
        changes: dict[str, Any],
        *,
        scope: ApplyScope = ApplyScope.DEFAULT,
        restart: bool = True,
    ) -> None: ...
    def get_section(self, key_path: tuple[str, ...]) -> ViewSettings | None: ...
```

**Safety contract:** Every mutating method (`apply`) begins by
calling `backup.create_backup()`. If the backup fails, the exception
propagates and no plist write occurs. `ApplyScope` is an enum:
`DEFAULT`, `ALL_FOLDERS`, `SPECIFIC(str)`.

### 6.3 `PlistSectionWalker`  (`services/discovery.py`)

```python
class PlistSectionWalker:
    def __init__(self, search_keys: tuple[str, ...] = SEARCH_KEYS) -> None: ...

    def discover(self, data: Any) -> list[SectionLocation]: ...
    def discover_in_folder(self, data: Any, folder_key: str) -> list[SectionLocation]: ...
```

**Algorithm:**
1. Recursively traverse the plist tree (dicts and lists).
2. For every dict, check if any key is in `search_keys`.
3. When a match is found, record the `key_path` (path from root to
   the matched key) and the value.
4. Yield `SectionLocation` objects.

This is **pure functions** — no I/O. The walker accepts any
`plistlib`-loaded object.

### 6.4 `FinderProcessService`  (`services/finder_process.py`)

```python
class FinderProcessService:
    def __init__(self, runner: SubprocessRunner) -> None: ...

    def is_firing(self) -> bool: ...
    def restart(self) -> None: ...
    def wait_for_relaunch(self, timeout: float = 30.0) -> bool: ...
    def get_version(self) -> str | None: ...
```

### 6.5 `EnvironmentService`  (`services/environment.py`)

```python
class EnvironmentService:
    def __init__(self, reader: PlistReader, backup: BackupService) -> None: ...

    def get_system_state(self) -> SystemState: ...
    def diagnose(self) -> list[Diagnosis]: ...
```

---

## 7. CLI Commands

Defined in `cli.py` using Typer. Each command maps to a service
method and returns `None` on success, raising `FinderCtlError` on
failure (handled by a global callback that prints to stderr and exits
with code 1).

### `backup`
```bash
finderctl backup [--label NAME] [--no-verify]
```
- Creates a timestamped backup of `FINDER_PLIST`.
- `--label` attaches a human-readable tag.
- `--no-verify` skips SHA-256 re-verification (not recommended).
- Prints: backup path, size, SHA-256, validity.

### `restore`
```bash
finderctl restore [BACKUP_NAME] [--restart] [--dry-run]
```
- `BACKUP_NAME` matches a timestamp prefix or full filename.
- `--dry-run` shows the diff without writing.
- Restores from `BACKUP_DIR` → `FINDER_PLIST` (atomic replace).
- `--restart` triggers `FinderProcessService.restart()`.

### `status`
```bash
finderctl status [--json]
```
- Prints `SystemState` as a human-readable table or JSON.
- Shows: plist existence/readability, Finder running state, macOS +
  Finder versions, backup count, latest backup info.

### `apply`
```bash
finderctl apply [FIELD] [VALUE] [--scope PATH] [--no-restart]
```
- **Always backs up first** (delegates to `SettingsService.apply`).
- Modifies the plist at the specified scope (default / all / specific).
- `--no-restart` suppresses Finder restart.
- Prints a diff of before/after.

### `clean`
```bash
finderctl clean [--keep N] [--verify]
```
- Prunes backups in `BACKUP_DIR` down to `keep` (default
  `MAX_BACKUPS`).
- `--verify` re-validates every backup before pruning.
- Removes corrupt/invalid backups.

### `doctor`
```bash
finderctl doctor [--fix] [--json]
```
- Runs diagnostic checks: plist integrity, backup validity, Finder
  process state, permissions.
- `--fix` attempts automatic repair (re-creates plist from latest
  valid backup if corrupt).
- `--json` for machine-readable output (useful in CI).

### Global options
```bash
finderctl [--verbose | --quiet] [--config PATH] [--no-color] <command> ...
```
- `--verbose` / `--quiet`: logging level control.
- `--config`: path to alternate `config.py`-compatible override (TOML).
- `--no-color`: disables colored output (for CI logs).

---

## 8. Data Flow & Workflows

### 8.1 Standard apply workflow (backup → modify → restart)

```
CLI apply
  │
  ▼
SettingsService.apply()                 ← enforces safety
  │  1. BackupService.create_backup()   ← guarantees backup exists first
  │       ↓
  │       PlistReader.read()             → plistlib.load()
  │       BackupStorage.write_atomic()   → temp file + os.replace + sha256
  │       BackupService.verify_backup()  ← re-read + re-hash
  │  2. PlistReader.read()               → full plist loaded into memory
  │  3. PlistSectionWalker.discover()    → all FolderView objects found
  │  4. Apply mutation                   → in-memory dict changes
  │  5. PlistWriter.write()              → atomic write to FINDER_PLIST
  │  6. (if restart) FinderProcessService.restart()
  ▼
CLI formats output → exit 0
```

### 8.2 restore workflow

```
CLI restore
  │
  ▼
BackupService.verify_backup()            ← validate source backup
  │
  ▼
PlistWriter.write_atomic()               → copy backup → FINDER_PLIST
  │
  ▼
FinderProcessService.restart()            ← optional
  │
  ▼
CLI confirms success → exit 0
```

### 8.3 status workflow

```
CLI status
  │
  ▼
EnvironmentService.get_system_state()
  ├─ PlistReader.read() exists? readable?
  ├─ FinderProcessService.is_firing() + get_version()
  ├─ BackupService.list_backups() → count + latest
  │
  ▼
SystemState dataclass
  │
  ▼
CLI renders (table / JSON) → exit 0
```

### 8.4 clean workflow

```
CLI clean
  │
  ▼
BackupService.list_backups()
  │
  ▼
BackupService.prune(keep=N, verify=...)
  ├─ verify each BackupRecord
  ├─ delete invalid / excess files
  │
  ▼
CLI summary of pruned records → exit 0
```

### 8.5 doctor workflow

```
CLI doctor
  │
  ▼
EnvironmentService.diagnose()
  ├─ Check plist exists & readable
  ├─ PlistSectionWalker.discover() → must yield ≥ 1 section
  ├─ BackupService.list_backups() → verify latest
  ├─ Check permissions (read/write on plist + backup dir)
  ├─ Check Finder process state
  │
  ▼
list[Diagnosis]                           ← severity: OK / WARN / ERROR / FIXABLE
  │
  ▼
(if --fix) apply repairs
  │
  ▼
CLI renders report → exit (0 if all OK, 1 if any ERROR)
```

---

## 9. Error Handling

### Exception hierarchy (`exceptions.py`)

```
FinderCtlError                      (base — all catchable as one)
├── ConfigurationError              (bad config, missing env)
├── PlistError                      (base for plist I/O)
│   ├── PlistNotFoundError          (FINDER_PLIST missing)
│   ├── PlistPermissionError        (unreadable / unwritable)
│   └── PlistParseError             (corrupt / malformed plist)
├── BackupError                     (backup create/verify/prune failure)
├── RestoreError                    (restore source missing / corrupt)
├── ApplyError                      (settings mutation failure)
├── SettingsError                   (read/query failure)
├── DiscoveryError                  (plist structure unexpected)
├── FinderProcessError              (restart / version detection failure)
└── ValidationError                 (bad CLI input: invalid scope, name, etc.)
```

### Handling strategy

- **CLI layer (`cli.py`):** a single `@app.callback()` or `main()`
  wrapper catches `FinderCtlError`, prints a concise message to
  stderr, and calls `sys.exit(1)`. Unexpected exceptions (non-
  `FinderCtlError`) are logged at `CRITICAL` and re-raised as
  `FinderCtlError` with a sanitized message.
- **Service layer:** raises domain exceptions with enough context
  for the CLI layer to surface useful messages. Never catches and
  silently swallows.
- **Infrastructure layer:** translates raw `OSError` /
  `plistlib.InvalidFileException` into typed `PlistIOError` subtypes.
- **Exit codes:** `0` = success, `1` = domain error, `2` =
  configuration/usage error.

---

## 10. Logging Strategy

- **Library:** Python `logging` (stdlib) — dependency-free, mypy/
  Ruff/Black friendly. Optionally structured via `structlog` if added
  as a dependency (non-requirement).
- **Configuration:** `logger.configure(level: LogLevel, stream: Path | None)`.
  - Default level: `WARNING` for `finderctl.*` loggers.
  - `--verbose` → `DEBUG`.
  - `--quiet` → `CRITICAL`.
- **Channels:**
  - `finderctl.cli` — user-facing command lifecycle.
  - `finderctl.services.*` — per-service operation traces.
  - `finderctl.infrastructure.*` — low-level I/O diagnostics.
- **Format:** `timestamp  LEVEL  logger_name  message` with optional
  `extra` dict for structured fields (backup name, key path, etc.).
- **No stdout pollution:** all logs go to **stderr**; stdout is
  reserved for CLI output (JSON, tables, paths). This keeps
  `finderctl status --json | jq` clean.

---

## 11. Testing Strategy

### Tooling
- **Runner:** `pytest` (≥8.x).
- **Coverage:** `pytest-cov` — `--cov=finderctl --cov-fail-under=95`.
- **Type checking:** `mypy --strict` (CI gate).
- **Lint/format:** `ruff check`, `ruff format` (CI gate).

### Fixture strategy
- `tests/conftest.py` provides:
  - `tmp_finder_plist` — a real plistlib-generated temp plist with
    nested `ListViewSettings` blocks.
  - `tmp_backup_dir` — isolated `BACKUP_DIR` override.
  - `mock_finder_process` — replaces `FindureProcessService` with a no-op.
  - `real_plist_reader` / `real_plist_writer` — thin infra adapters
    pointing at temp paths.

### Test matrix

| Layer | File | Coverage |
|---|---|---|
| Unit — discovery | `test_discovery.py` | Recursive walker: flat dict, deeply nested dict, list-of-dicts, multiple SEARCH_KEYS, empty plist, non-plist input. |
| Unit — models | `test_models.py` | Frozen immutability, `SectionLocation` equality, `ApplyScope` enum, `ViewSettings` validation. |
| Unit — validation | `test_validation.py` | Backup name regex, folder path validation, timestamp parsing round-trip. |
| Unit — exceptions | `test_exceptions.py` | Hierarchy correctness, str representation. |
| Integration — backup | `test_backup_service.py` | Create → verify → list → prune → export; corrupted source triggers `PlistError`. |
| Integration — settings | `test_settings_service.py` | Apply mutates plist; backup auto-created; read-back matches; `ApplyScope.SPECIFIC` targets correct section. |
| Integration — CLI | `test_cli.py` | Typer `CliRunner` for all six commands: `--help`, success path, error path (exit code 1), `--json` output shape. |
| Integration — I/O | `test_plist_io.py` | Atomic write + replace, parse error → `PlistParseError`, read missing file → `PlistNotFoundError`. |

### Property-based testing
- `hypothesis` for the recursive walker: generate arbitrary nested
  dict/list structures with random `SEARCH_KEYS` insertions and assert
  deterministic, complete discovery.

---

## 12. Extensibility

### Adding a new macOS.plist key
1. Add the key name to `SEARCH_KEYS` in `config.py`.
2. The `PlistSectionWalker` automatically discovers it — no walker
   code change required.

### Adding a new CLI command
1. Create a function in `cli.py` decorated with `@app.command()`.
2. Use `typer.Option` / `typer.Argument` for typed params.
3. Inject services via the Typer context or direct construction
   (DI not required — services are cheap to construct).

### Adding a new view-settings format
1. Add a new value object to `models.py`.
2. Add a parser function in `discovery.py` (or a dedicated
   `parsers/` subpackage) that transforms a raw plist dict into the
   new model.

### Environment-variable overrides
All paths in `config.py` check `os.environ` first, enabling:
- CI testing without touching real plist paths.
- Sandbox/dev deployment with custom locations.

---

## 13. Development & Release

### Tooling (`pyproject.toml`)
```toml
[project]
name = "finderctl"
requires-python = ">=3.13"
dependencies = ["typer>=0.12"]

[project.optional-dependencies]
dev = ["ruff", "black", "mypy", "pytest", "pytest-cov", "hypothesis", "rich"]

[project.scripts]
finderctl = "finderctl.cli:app"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.black]
line-length = 100

[tool.mypy]
strict = true
```

### CI pipeline (`.github/workflows/ci.yml`)
1. `ruff check .` → lint.
2. `ruff format --check .` → formatting.
3. `mypy --strict finderctl` → type safety.
4. `pytest --cov=finderctl --cov-fail-under=95` → tests.

### Release
- Semantic versioning (`__version__` in `__init__.py`).
- GitHub release workflow builds the wheel and publishes to PyPI.

---

## 14. Safety Invariants (Frozen Guarantees)

| # | Invariant | Enforced by |
|---|---|---|
| 1 | Never modify `FINDER_PLIST` without a prior verified backup. | `SettingsService.apply()` → `BackupService.create_backup()` (first line, checked). |
| 2 | Backup copy is verified (SHA-256 re-read) before reporting success. | `BackupService.create_backup()` → `verify_backup()`. |
| 3 | Plist writes are atomic (temp file + `os.replace`). | `PlistFileWriter` → `write_atomic()`. |
| 4 | `FinderProcessService.restart()` only fires after a successful plist write. | `SettingsService.apply()` ordering: write → *then* restart. |
| 5 | Discovery never mutates the input tree. | `PlistSectionWalker.discover()` is a pure read-only traversal. |
| 6 | CLI never prints log output to stdout. | `logger.configure()` → stderr stream only. |

---

## 15. Frozen Architecture — Summary

| Concern | Decision |
|---|---|
| Language | Python 3.13+ |
| CLI framework | Typer |
| Plist library | `plistlib` (stdlib) |
| Path library | `pathlib` (stdlib only) |
| Logging | `logging` (stdlib), stderr |
| Test runner | `pytest` + `pytest-cov` |
| Type checker | `mypy --strict` |
| Linter | `ruff` (check + format) |
| Formatter | `black` (compatible) |
| Architecture | Domain → Application/Services → Infrastructure → CLI |
| Dependency injection | Constructor injection (no framework) |
| Entry point | `finderctl.cli:app` (Typer) |
| Exit codes | 0 = ok, 1 = domain error, 2 = usage/config error |

> **This document is frozen.** Any deviation from the structure,
> models, or service contracts above requires an architecture review
> and an amended specification version.

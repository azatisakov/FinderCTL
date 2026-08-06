from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ..config import (
    DESIRED_DEFAULT_LIST_VIEW,
    DESIRED_GLOBAL_PREFS,
    FINDER_PLIST,
    LIST_VIEW_CONTAINERS,
)
from ..exceptions import (
    ApplyError,
    ValidationError,
)
from ..infrastructure.plist_io import PlistReader, PlistWriter
from ..logger import get_logger
from ..models import (
    ApplyScope,
    Change,
    FolderView,
    SectionLocation,
    ViewSettings,
)
from .backup import BackupService
from .discovery import PlistSectionWalker

logger = get_logger("services.settings")


class SettingsService:
    """Reads, writes, and applies Finder view settings safely.

    **Safety contract:** Every mutating method calls
    :meth:`BackupService.create_backup` **before** any plist write.
    If the backup fails, the exception propagates and no write occurs.
    """

    def __init__(
        self,
        finder_plist: Path | None = None,
        reader: PlistReader | None = None,
        writer: PlistWriter | None = None,
        backup_service: BackupService | None = None,
    ) -> None:
        plist_path = finder_plist or FINDER_PLIST
        self._reader = reader or PlistReader(plist_path)
        self._writer = writer or PlistWriter(plist_path)
        self._backup = backup_service or BackupService(finder_plist=plist_path)
        self._walker = PlistSectionWalker()

    @property
    def walker(self) -> PlistSectionWalker:
        return self._walker

    def read_all(self) -> list[FolderView]:
        """Discover all view-settings containers and their sections."""
        data = self._reader.read()
        locations = self._walker.discover(data)

        # Group by immediate parent container
        by_container: dict[str, list[SectionLocation]] = {}
        for loc in locations:
            container = loc.key_path[0] if loc.key_path else "root"
            by_container.setdefault(container, []).append(loc)

        views: list[FolderView] = []
        for container, locs in sorted(by_container.items()):
            settings = [
                ViewSettings(
                    key_name=loc.key_path[-1],
                    properties=dict(loc.data),
                    container=container,
                )
                for loc in locs
            ]
            views.append(FolderView(folder_key=container, settings=settings))

        logger.debug("read_all: %d containers, %d total sections", len(views), len(locations))
        return views

    def read_default(self) -> ViewSettings | None:
        """Return the ``FK_DefaultListViewSettingsV2`` section."""
        data = self._reader.read()
        locations = self._walker.discover(data)
        for loc in locations:
            if loc.key_path == ("FK_DefaultListViewSettingsV2",):
                return ViewSettings(
                    key_name="FK_DefaultListViewSettingsV2",
                    properties=dict(loc.data),
                    container="root",
                )
        return None

    def read_folder(self, folder_key: str) -> FolderView | None:
        """Return all view-settings sections for a specific container key."""
        data = self._reader.read()
        locations = self._walker.discover_in_folder(data, folder_key)
        if not locations:
            return None
        settings = [
            ViewSettings(
                key_name=loc.key_path[-1],
                properties=dict(loc.data),
                container=folder_key,
            )
            for loc in locations
        ]
        return FolderView(folder_key=folder_key, settings=settings)

    def apply_defaults(self, *, restart: bool = True, dry_run: bool = False) -> list[Change]:
        """Apply the desired default List View settings to the plist.

        This is the primary command for Layer A (safe path). It:
        1. Creates a ``pre-apply-defaults`` backup.
        2. Merges desired settings into ``FK_DefaultListViewSettingsV2``.
        3. Merges desired settings into every container in
           ``LIST_VIEW_CONTAINERS``.
        4. Sets global prefs (``DESIRED_GLOBAL_PREFS``).

        Returns:
            The list of :class:`Change` objects describing mutations.

        Raises:
            ApplyError: if backup, write, or verification fails.
        """
        backup = self._backup.create_backup(label="pre-apply-defaults")
        logger.info("backup created for apply-defaults: %s", backup.path.name)

        if dry_run:
            logger.info("dry-run: skipping plist write and Finder restart")
            return self._build_default_changes(dry_run=True)

        data = self._reader.read()
        changes = self._build_default_changes(data)

        try:
            self._writer.write_atomic(data)
        except Exception as exc:
            raise ApplyError(f"atomic write failed: {exc}") from exc

        # Post-write verification
        verify_reader = PlistReader(self._writer.path)
        re_data = verify_reader.read()
        re_locations = self._walker.discover(re_data)
        if len(re_locations) < 1:
            raise ApplyError("post-write verification failed: 0 sections after write")

        for change in changes:
            full_path = self._resolve_field_path(change)
            actual = self._get_nested(re_data, full_path)
            if actual != change.after:
                raise ApplyError(
                    f"post-write verification failed: {change.key_path}.{change.field} "
                    f"expected {change.after!r}, got {actual!r}"
                )

        logger.info("apply-defaults complete: %d changes applied", len(changes))
        return changes

    def apply(
        self,
        field: str,
        value: Any,
        *,
        scope: ApplyScope = ApplyScope.DEFAULT,
        restart: bool = True,
        dry_run: bool = False,
    ) -> list[Change]:
        """Apply a single field/value change to the plist.

        Raises:
            ValidationError: if field is not allowed.
            ApplyError: if backup or write fails.
        """
        from ..config import ALLOWED_FIELDS

        if field not in ALLOWED_FIELDS:
            raise ValidationError(
                f"field {field!r} is not allowed. Allowed: {', '.join(sorted(ALLOWED_FIELDS))}"
            )

        self._backup.create_backup(label="pre-apply")
        data = self._reader.read()
        locations = self._walker.discover(data)
        target_locs = self._filter_by_scope(locations, scope)

        changes: list[Change] = []
        for loc in target_locs:
            key_path = loc.key_path
            current = self._get_nested(data, key_path)
            old_val = self._get_nested(data, key_path + (field,))
            expected_type = type(current.get(field)) if isinstance(current, dict) else None

            try:
                new_val = self._coerce(value, expected_type)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"invalid value for {field}: {exc}") from exc

            if old_val == new_val:
                continue

            self._set_nested(data, key_path + (field,), new_val)
            changes.append(
                Change(
                    scope=scope.value,
                    field=field,
                    before=old_val,
                    after=new_val,
                    key_path=key_path,
                )
            )

        if not changes:
            raise ApplyError("no matching sections found for the given scope")

        if dry_run:
            logger.info("dry-run: skipping write and restart")
            return changes

        try:
            self._writer.write_atomic(data)
        except Exception as exc:
            raise ApplyError(f"atomic write failed: {exc}") from exc

        return changes

    def get_section(self, key_path: tuple[str, ...]) -> ViewSettings | None:
        """Return a single section by its dotted key path."""
        data = self._reader.read()
        locations = self._walker.discover(data)
        for loc in locations:
            if loc.key_path == key_path:
                return ViewSettings(
                    key_name=loc.key_path[-1],
                    properties=dict(loc.data),
                    container=loc.key_path[0] if loc.key_path else "root",
                )
        return None

    def sync_legacy_columns(self, data: dict[str, Any]) -> None:
        """Keep ``ListViewSettings`` (dict format) in sync with
        ``ExtendedListViewSettingsV2`` (array format) within each container.

        macOS maintains both as shadows; we must update both.
        """
        for container_key in LIST_VIEW_CONTAINERS:
            container = data.get(container_key)
            if not isinstance(container, dict):
                continue

            ext = container.get("ExtendedListViewSettingsV2")
            leg = container.get("ListViewSettings")

            if not isinstance(ext, dict) or not isinstance(leg, dict):
                continue

            ext_cols = ext.get("columns")
            leg_cols = leg.get("columns")

            if isinstance(ext_cols, list) and isinstance(leg_cols, dict):
                # Array → dict sync
                new_dict: dict[str, Any] = {}
                for idx, col in enumerate(ext_cols):
                    ident = col.get("identifier")
                    if ident is not None:
                        new_dict[ident] = {
                            "ascending": col.get("ascending"),
                            "index": idx,
                            "visible": col.get("visible"),
                            "width": col.get("width"),
                        }
                leg_cols.clear()
                leg_cols.update(new_dict)

    def _build_default_changes(
        self,
        data: dict[str, Any] | None = None,
        *,
        dry_run: bool = False,
    ) -> list[Change]:
        """Apply desired defaults into the plist tree (or build changes
        for dry-run reporting)."""
        if dry_run:
            return self._dry_run_changes()

        assert data is not None
        changes: list[Change] = []

        # --- FK_DefaultListViewSettingsV2 (root-level template) ---
        default_ls = data.setdefault("FK_DefaultListViewSettingsV2", {})
        for k, v in DESIRED_DEFAULT_LIST_VIEW.items():
            old = default_ls.get(k)
            if old != v:
                default_ls[k] = deepcopy(v)
                changes.append(
                    Change(
                        scope="default",
                        field=k,
                        before=old,
                        after=v,
                        key_path=("FK_DefaultListViewSettingsV2",),
                    )
                )

        # --- Container defaults: StandardViewSettings, etc. ---
        for container_key in LIST_VIEW_CONTAINERS:
            container = data.setdefault(container_key, {})
            for section_key, _target_fields in (
                ("ExtendedListViewSettingsV2", DESIRED_DEFAULT_LIST_VIEW),
                ("ListViewSettings", DESIRED_DEFAULT_LIST_VIEW),
            ):
                section = container.setdefault(section_key, {})

                for k, v in DESIRED_DEFAULT_LIST_VIEW.items():
                    old = section.get(k)
                    if old != v:
                        section[k] = deepcopy(v)
                        changes.append(
                            Change(
                                scope=container_key,
                                field=k,
                                before=old,
                                after=v,
                                key_path=(container_key, section_key),
                            )
                        )

        # --- Sync legacy columns from extended ---
        self.sync_legacy_columns(data)

        # --- Global prefs ---
        for k, v in DESIRED_GLOBAL_PREFS.items():
            old = data.get(k)
            if old != v:
                data[k] = v
                changes.append(
                    Change(
                        scope="global",
                        field=k,
                        before=old,
                        after=v,
                        key_path=(k,),
                    )
                )

        return changes

    def _dry_run_changes(self) -> list[Change]:
        """Build a change list describing what apply-defaults WOULD do."""
        data = self._reader.read()
        changes: list[Change] = []

        # FK_DefaultListViewSettingsV2
        target = data.get("FK_DefaultListViewSettingsV2", {})
        for k, v in DESIRED_DEFAULT_LIST_VIEW.items():
            old = target.get(k)
            if old != v:
                changes.append(
                    Change(
                        scope="default",
                        field=k,
                        before=old,
                        after=v,
                        key_path=("FK_DefaultListViewSettingsV2",),
                    )
                )

        for container_key in LIST_VIEW_CONTAINERS:
            container = data.get(container_key, {})
            for section_key in ("ExtendedListViewSettingsV2", "ListViewSettings"):
                section = container.get(section_key, {})
                for k, v in DESIRED_DEFAULT_LIST_VIEW.items():
                    old = section.get(k)
                    if old != v:
                        changes.append(
                            Change(
                                scope=container_key,
                                field=k,
                                before=old,
                                after=v,
                                key_path=(container_key, section_key),
                            )
                        )

        for k, v in DESIRED_GLOBAL_PREFS.items():
            old = data.get(k)
            if old != v:
                changes.append(
                    Change(
                        scope="global",
                        field=k,
                        before=old,
                        after=v,
                        key_path=(k,),
                    )
                )

        return changes

    def _filter_by_scope(
        self, locations: list[SectionLocation], scope: ApplyScope
    ) -> list[SectionLocation]:
        """Filter discovered sections by scope."""
        if scope == ApplyScope.ALL:
            return locations
        if scope == ApplyScope.DEFAULT:
            return [loc for loc in locations if loc.key_path == ("FK_DefaultListViewSettingsV2",)]
        scope_map = {
            ApplyScope.STANDARD: ("StandardViewSettings", "FK_StandardViewSettings"),
            ApplyScope.DESKTOP: ("DesktopViewSettings",),
            ApplyScope.ICLOUD: ("ICloudViewSettings",),
            ApplyScope.TRASH: ("TrashViewSettings",),
            ApplyScope.PACKAGE: ("PackageViewSettings",),
            ApplyScope.SEARCH_RECENTS: ("SearchRecentsViewSettings",),
            ApplyScope.MEETING_ROOM: ("MeetingRoomViewSetting",),
        }
        containers = scope_map.get(scope, ())
        return [loc for loc in locations if loc.key_path[0] in containers]

    @staticmethod
    def _get_nested(data: Any, path: tuple[str, ...]) -> Any:
        """Safely traverse a nested structure by key path."""
        current: Any = data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    @staticmethod
    def _resolve_field_path(change: Change) -> tuple[str, ...]:
        """Resolve the full key path for a change.

        For global prefs, ``key_path`` already equals ``(field,)``.
        For section-level changes, ``key_path`` points to the section
        and ``field`` is the key within it.
        """
        if change.key_path and change.key_path[-1] == change.field:
            return change.key_path
        return change.key_path + (change.field,)

    def _set_nested(self, data: Any, path: tuple[str, ...], value: Any) -> None:
        """Set a value at a nested key path, creating dicts as needed."""
        current: Any = data
        for key in path[:-1]:
            if not isinstance(current, dict):
                raise ApplyError(f"cannot traverse path {path}: non-dict at {key}")
            if key not in current:
                current[key] = {}
            current = current[key]
        if not isinstance(current, dict):
            raise ApplyError(f"cannot set path {path}: target is not a dict")
        current[path[-1]] = value

    @staticmethod
    def _coerce(value: Any, expected_type: type | None) -> Any:
        """Coerce a CLI value to the expected plist type."""
        if expected_type is bool:
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    return True
                if value.lower() in ("false", "0", "no"):
                    return False
                raise ValueError(f"cannot coerce {value!r} to bool")
            return bool(value)
        if expected_type is int:
            return int(value)
        if expected_type is float:
            return float(value)
        if expected_type is str:
            return str(value)
        return value

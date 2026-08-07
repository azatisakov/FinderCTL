from __future__ import annotations

import contextlib
import plistlib
import shutil
from pathlib import Path
from typing import Any

from .config import DESIRED_DEFAULT_LIST_VIEW
from .exceptions import (
    DSRevertibleError,
    DSStoreCorruptionError,
    DSStoreNotFoundError,
)
from .logger import get_logger
from .models import Change

logger = get_logger("dsstore")

DSSTORE_BACKUP_SUFFIX = ".finderctl.bak"
BLOB_VIEW_CODES = frozenset({b"lsvp", b"icvp", b"gvsp"})
LIST_VIEW_CODES = frozenset({b"lsvp", b"lsvC"})
WINDOW_STATE_CODE = b"bwsp"
VIEW_ROOT_CODE = b"vSrn"


class DSStoreEntry:
    """Lightweight snapshot of a ``.DS_Store`` B-tree entry."""

    __slots__ = ("filename", "code", "value")

    def __init__(self, filename: str, code: bytes, value: Any) -> None:
        self.filename = filename
        self.code = code
        self.value = value

    def __repr__(self) -> str:
        return f"DSStoreEntry(filename={self.filename!r}, code={self.code!r})"


class DSStoreReader:
    """Reads view-settings from a ``.DS_Store`` file via the B-tree.

    Uses the ``ds_store`` library for B-tree parsing. Extracts `lsvp`
    (dict), `lsvC` (binary plist), and `bwsp` records for each folder
    entry.
    """

    def __init__(self, path: Path) -> None:
        from ds_store import DSStore

        self._path = path
        self._ds = DSStore.open(str(path), "r")

    @property
    def path(self) -> Path:
        return self._path

    def entries(self) -> list[DSStoreEntry]:
        """Return all entries as lightweight dataclass objects."""
        result: list[DSStoreEntry] = []
        for entry in self._ds:
            result.append(
                DSStoreEntry(
                    filename=entry.filename,
                    code=entry.code,
                    value=entry.value,
                )
            )
        return result

    def get_list_view(self, folder: str) -> dict[str, Any] | None:
        """Return the ``lsvp`` dict for a folder, or None."""
        try:
            value = self._ds[folder]["lsvp"]
        except KeyError:
            return None
        if isinstance(value, dict):
            return value
        return None

    def get_list_view_plist(self, folder: str) -> dict[str, Any] | None:
        """Return the ``lsvC`` (binary plist) dict for a folder, or None."""
        try:
            raw = self._ds[folder]["lsvC"]
        except KeyError:
            return None
        data = bytes(raw[1]) if isinstance(raw, tuple) else bytes(raw)
        if not data or data[:6] != b"bplist":
            return None
        try:
            parsed = plistlib.loads(data)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def has_list_view(self, folder: str) -> bool:
        """True if the folder has an `lsvp` or `lsvC` record."""
        try:
            return bool(self._ds[folder]["lsvp"]) or bool(self._ds[folder]["lsvC"])
        except KeyError:
            return False

    def get_window_state(self, folder: str) -> dict[str, Any] | None:
        """Return the ``bwsp`` dict for a folder, or None."""
        try:
            value = self._ds[folder]["bwsp"]
        except KeyError:
            return None
        return value if isinstance(value, dict) else None

    def close(self) -> None:
        self._ds.close()


class DSStoreWriter:
    """Writes patched view-settings back into a ``.DS_Store`` file."""

    def __init__(self, path: Path) -> None:
        from ds_store import DSStore

        self._path = path
        mode = "r+" if path.exists() else "w+"
        self._ds = DSStore.open(str(path), mode)

    @property
    def path(self) -> Path:
        return self._path

    def set_list_view(self, folder: str, settings: dict[str, Any]) -> None:
        """Set the ``lsvp`` dict for a folder (PlistCodec handles serialization)."""
        self._ds[folder]["lsvp"] = settings

    def set_list_view_plist(self, folder: str, settings: dict[str, Any]) -> None:
        """Set the ``lsvC`` binary plist record for a folder.

        ``lsvC`` has no registered codec, so we must pass the raw
        ``(type, data)`` tuple with binary plist bytes.
        """
        payload = plistlib.dumps(settings, fmt=plistlib.FMT_BINARY)
        self._ds[folder]["lsvC"] = (b"blob", bytearray(payload))

    def set_window_state(self, folder: str, state: dict[str, Any]) -> None:
        """Set the ``bwsp`` dict for a folder (PlistCodec handles serialization)."""
        self._ds[folder]["bwsp"] = state

    def set_view_root(self, folder: str, value: int = 1) -> None:
        """Set the ``vSrn`` record (1 = List view root).

        ``vSrn`` has no registered codec, so we pass a ``(type, value)``
        tuple directly.
        """
        self._ds[folder]["vSrn"] = (b"long", value)

    def delete_record(self, folder: str, code: bytes) -> None:
        """Delete a record code for a folder (if present)."""
        with contextlib.suppress(KeyError):
            del self._ds[folder][code]

    def close(self) -> None:
        self._ds.close()

    def commit(self) -> None:
        """Flush the ds_store buffer to disk (closes the file)."""
        self._ds.close()


class DSService:
    """High-level service for enforcing List View settings in
    ``.DS_Store`` files across folder hierarchies.

    This is the **opt-in** Layer B service. It operates on folders
    with explicit user consent via the ``finderctl enforce`` command.
    """

    def __init__(self) -> None:
        columns_raw = DESIRED_DEFAULT_LIST_VIEW["columns"]
        self._target_columns: list[dict[str, Any]] = (
            columns_raw if isinstance(columns_raw, list) else []
        )
        self._target_fields: dict[str, Any] = {
            k: v for k, v in DESIRED_DEFAULT_LIST_VIEW.items() if k != "columns"
        }

    def backup_dsstore(self, path: Path) -> Path:
        """Copy a ``.DS_Store`` to ``.DS_Store.finderctl.bak``.

        Returns the backup path.
        """
        if not path.exists():
            raise DSStoreNotFoundError(f".DS_Store not found: {path}")
        backup = path.with_name(path.name + DSSTORE_BACKUP_SUFFIX)
        shutil.copy2(path, backup)
        logger.debug("backed up %s -> %s", path, backup)
        return backup

    def restore_dsstore(self, path: Path) -> None:
        """Restore a ``.DS_Store` from its ``.finderctl.bak` backup."""
        backup = path.with_name(path.name + DSSTORE_BACKUP_SUFFIX)
        if not backup.exists():
            raise DSStoreNotFoundError(f"no backup found for {path} (expected {backup})")
        tmp = path.with_name(path.name + ".restore.tmp")
        shutil.copy2(backup, tmp)
        tmp.replace(path)
        backup.unlink(missing_ok=True)
        logger.info("restored %s from backup", path)

    def enforce_folder(
        self,
        folder: Path,
        dry_run: bool = False,
    ) -> list[Change]:
        """Enforce List View settings for a single folder's ``.DS_Store``.

        Args:
            folder: The folder containing (or that should contain) a
                ``.DS_Store`` file.
            dry_run: If True, return planned changes without writing.

        Returns:
            List of :class:`Change` objects describing what changed.

        Raises:
            DSStoreCorruptionError: if the file cannot be opened.
            DSRevertibleError: if patching fails (backup is preserved).
        """
        ds_path = folder / ".DS_Store"

        if not ds_path.exists():
            logger.debug("no .DS_Store in %s -- skipping (defaults apply)", folder)
            return []

        try:
            reader = DSStoreReader(ds_path)
        except Exception as exc:
            raise DSStoreCorruptionError(f"cannot open {ds_path}: {exc}") from exc

        try:
            entries = reader.entries()
        finally:
            reader.close()
        lsvp_entries = [e for e in entries if e.code == b"lsvp" and isinstance(e.value, dict)]
        lsvC_entries = [e for e in entries if e.code == b"lsvC"]

        has_root_lsvp = any(e.filename == "." and e.code in LIST_VIEW_CODES for e in entries)

        if not lsvp_entries and not lsvC_entries:
            logger.debug("%s: no list view settings found", ds_path)
        else:
            logger.debug(
                "%s: found %d lsvp + %d lsvC entries",
                ds_path,
                len(lsvp_entries),
                len(lsvC_entries),
            )

        if dry_run:
            return self._plan_changes(entries, ds_path, has_root_lsvp)

        self.backup_dsstore(ds_path)

        try:
            writer = DSStoreWriter(ds_path)
            self._apply_patches(writer, entries)
            writer.commit()
        except Exception as exc:
            self.restore_dsstore(ds_path)
            logger.warning("skipping corrupted %s: %s", ds_path, exc)
            return []

        return self._plan_changes(entries, ds_path, has_root_lsvp)

    def _plan_changes(
        self,
        entries: list[DSStoreEntry],
        path: Path,
        has_root_lsvp: bool,
    ) -> list[Change]:
        """Build a Change list describing what WOULD change (dry-run)."""
        changes: list[Change] = []

        if not has_root_lsvp:
            changes.append(
                Change(
                    scope=path.name,
                    field="create_dot_entry",
                    before=None,
                    after="lsvp+ lsvC dot entry with List View defaults",
                    key_path=(str(path), "."),
                )
            )

        for entry in entries:
            if entry.code == b"lsvp" and isinstance(entry.value, dict):
                for k, v in self._target_fields.items():
                    old = entry.value.get(k)
                    if old != v:
                        changes.append(
                            Change(
                                scope=path.name,
                                field=f"lsvp.{k}",
                                before=old,
                                after=v,
                                key_path=(str(path), entry.filename, "lsvp"),
                            )
                        )
                old_cols = entry.value.get("columns", {})
                if isinstance(old_cols, dict):
                    new_cols = self._sync_columns(old_cols)
                    if old_cols != new_cols:
                        changes.append(
                            Change(
                                scope=path.name,
                                field="lsvp.columns",
                                before=old_cols,
                                after=new_cols,
                                key_path=(str(path), entry.filename, "lsvp"),
                            )
                        )
        return changes

    def _apply_patches(
        self,
        writer: DSStoreWriter,
        entries: list[DSStoreEntry],
    ) -> None:
        """Apply all patches to a DSStoreWriter instance.

        Patches every entry that has an ``lsvp`` or ``lsvC`` record.
        If no ``.`` (root) entry exists, creates one with defaults.
        """
        has_root = False

        for entry in entries:
            if entry.filename == ".":
                has_root = True

            if entry.code == b"lsvp" and isinstance(entry.value, dict):
                patched = dict(entry.value)
                for k, v in self._target_fields.items():
                    patched[k] = v
                if "columns" in patched and isinstance(patched["columns"], dict):
                    patched["columns"] = self._sync_columns(patched["columns"])
                writer.set_list_view(entry.filename, patched)
                writer.set_view_root(entry.filename, 1)

            if entry.code == b"lsvC":
                raw = entry.value
                data = bytes(raw) if isinstance(raw, (bytes, bytearray)) else b""
                if data[:6] == b"bplist":
                    try:
                        parsed = plistlib.loads(data)
                        if isinstance(parsed, dict):
                            for k, v in self._target_fields.items():
                                parsed[k] = v
                            if "columns" in parsed and isinstance(parsed["columns"], list):
                                parsed["columns"] = list(self._target_columns)
                            writer.set_list_view_plist(entry.filename, parsed)
                    except Exception:
                        pass

        if not has_root:
            self._create_root_entry(writer)

    def _create_root_entry(self, writer: DSStoreWriter) -> None:
        """Create a `.` entry with default List View settings."""
        lsvp: dict[str, Any] = dict(self._target_fields)
        lsvp["columns"] = {
            c["identifier"]: {
                "ascending": c["ascending"],
                "index": idx,
                "visible": c["visible"],
                "width": c["width"],
            }
            for idx, c in enumerate(self._target_columns)
        }
        writer.set_list_view(".", lsvp)
        writer.set_list_view_plist(".", dict(self._target_fields))
        writer.set_view_root(".", 1)

    def _sync_columns(self, old_columns: dict[str, Any]) -> dict[str, Any]:
        """Transform a dict of columns to match the target visibility/order.

        Preserves existing column widths if present; otherwise uses
        defaults from :data:`DESIRED_DEFAULT_LIST_VIEW`.
        """
        result: dict[str, Any] = {}
        for idx, target in enumerate(self._target_columns):
            ident = target["identifier"]
            existing = old_columns.get(ident)
            result[ident] = {
                "ascending": target["ascending"],
                "index": idx,
                "visible": target["visible"],
                "width": _preserve_width(existing, target),
            }
        return result


def _preserve_width(existing: dict[str, Any] | None, target: dict[str, Any]) -> int:
    """Preserve existing column width if reasonable, else use target."""
    if existing and isinstance(existing, dict):
        w = existing.get("width")
        if isinstance(w, (int, float)) and 20 <= w <= 2000:
            return int(w)
    return int(target["width"])

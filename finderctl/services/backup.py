from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from ..config import BACKUP_DIR, FINDER_PLIST
from ..exceptions import BackupError, PlistError
from ..infrastructure.backup_storage import BackupStorage
from ..infrastructure.plist_io import PlistReader
from ..logger import get_logger
from ..models import BackupRecord

logger = get_logger("services.backup")


class BackupService:
    """Manages the full backup lifecycle: create, verify, list, prune, export."""

    def __init__(
        self,
        finder_plist: Path = FINDER_PLIST,
        backup_dir: Path = BACKUP_DIR,
    ) -> None:
        self._plist_path = finder_plist
        self._storage = BackupStorage(backup_dir)

    @property
    def storage(self) -> BackupStorage:
        return self._storage

    def create_backup(
        self,
        *,
        label: str | None = None,
        source_timestamp: datetime | None = None,
    ) -> BackupRecord:
        """Create a verified backup of the Finder plist.

        Steps:
        1. Confirm the plist exists and is readable.
        2. Copy the file with metadata (``shutil.copy2``).
        3. Compute source + backup SHA-256 and compare.
        4. Re-read the backup via ``plistlib`` to confirm validity.
        5. Write a ``.sha256`` sidecar.

        Raises:
            BackupError: if any step fails. The partial backup is
                deleted before raising.
        """
        if not self._plist_path.exists():
            raise BackupError(f"Finder plist not found: {self._plist_path}")

        self._storage.ensure_dir()

        ts = source_timestamp or datetime.now()
        dest = self._storage.backup_path(ts, label=label)

        logger.debug("creating backup: %s → %s", self._plist_path, dest)

        source_hash = self._storage.compute_sha256(self._plist_path)

        try:
            self._storage.copy_file(self._plist_path, dest)
        except BackupError:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise

        backup_hash = self._storage.compute_sha256(dest)

        if source_hash != backup_hash:
            dest.unlink(missing_ok=True)
            raise BackupError(f"backup verification failed: SHA-256 mismatch for {dest.name}")

        # Re-read via plistlib to confirm structural validity
        reader = PlistReader(dest)
        try:
            reader.read()
        except PlistError as exc:
            dest.unlink(missing_ok=True)
            raise BackupError(f"backup plist is invalid: {exc}") from exc

        self._storage.write_sidecar(dest, backup_hash)
        logger.info("backup created: %s (sha256=%s)", dest.name, backup_hash[:12])

        return BackupRecord(
            path=dest,
            timestamp=ts,
            size_bytes=dest.stat().st_size,
            sha256=backup_hash,
            is_valid=True,
            label=label,
        )

    def list_backups(self) -> list[BackupRecord]:
        """List all backups sorted by creation time (oldest first)."""
        records: list[BackupRecord] = []
        for path in self._storage.list_backups():
            records.append(self._build_record(path))

        def _sort_key(r: BackupRecord) -> float:
            try:
                return r.path.stat().st_ctime
            except OSError:
                return r.timestamp.timestamp()

        records.sort(key=_sort_key)
        return records

    def get_latest(self) -> BackupRecord | None:
        """Return the most recent verified backup, or ``None``."""
        backups = self.list_backups()
        verified = [r for r in backups if r.is_valid]
        return verified[-1] if verified else None

    def get_latest_matching(self, label: str | None = None) -> BackupRecord | None:
        """Return the most recent verified backup matching a label."""
        backups = self.list_backups()
        filtered = [r for r in backups if r.is_valid and (label is None or r.label == label)]
        return filtered[-1] if filtered else None

    def verify_backup(self, record: BackupRecord) -> bool:
        """Re-verify a backup's SHA-256 integrity."""
        stored = self._storage.read_sidecar(record.path)
        if stored is None:
            return False
        current = self._storage.compute_sha256(record.path)
        return stored == current

    def prune(self, keep: int = 10, verify: bool = False) -> list[BackupRecord]:
        """Prune backups down to the ``keep`` most recent verified ones.

        Invalid/corrupt backups are always pruned regardless of ``keep``.
        The single most recent verified backup is never pruned.

        Returns:
            The list of pruned (deleted) backup records.
        """
        records = self.list_backups()
        valid = [r for r in records if r.is_valid]
        invalid = [r for r in records if not r.is_valid]

        if verify:
            valid = [r for r in valid if not self.verify_backup(r)] + [
                r for r in valid if self.verify_backup(r)
            ]

        pruned: list[BackupRecord] = []

        # Always prune invalid backups
        for r in invalid:
            r.path.unlink(missing_ok=True)
            self._storage.sha256_path(r.path).unlink(missing_ok=True)
            pruned.append(r)

        # Prune excess valid backups (but never the latest)
        excess = len(valid) - keep
        if excess > 0:
            to_prune = valid[:excess]
            for r in to_prune:
                r.path.unlink(missing_ok=True)
                self._storage.sha256_path(r.path).unlink(missing_ok=True)
                pruned.append(r)

        return pruned

    def export(self, record: BackupRecord, dest: Path) -> Path:
        """Copy a backup file to an external destination."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.path, dest)
        return dest

    def _build_record(self, path: Path) -> BackupRecord:
        """Construct a :class:`BackupRecord` from a backup file path."""
        try:
            ts = self._parse_timestamp(path)
        except ValueError:
            ts = datetime.now()

        stored_hash = self._storage.read_sidecar(path)
        is_valid = False
        sha = ""
        if stored_hash is not None:
            current = self._storage.compute_sha256(path)
            sha = stored_hash
            is_valid = current == stored_hash

        label = self._extract_label(path.name)
        return BackupRecord(
            path=path,
            timestamp=ts,
            size_bytes=path.stat().st_size,
            sha256=sha,
            is_valid=is_valid,
            label=label,
        )

    @staticmethod
    def _parse_timestamp(path: Path) -> datetime:
        """Extract timestamp from filename; raises ValueError if unparseable."""
        from ..utils.timestamps import parse_backup_timestamp

        ts = parse_backup_timestamp(path.name)
        if ts is None:
            raise ValueError(f"cannot parse timestamp from {path.name}")
        return ts

    @staticmethod
    def _extract_label(filename: str) -> str | None:
        """Extract the label from a backup filename.

        Filename format: ``YYYY-MM-DD_HH-MM-SS[_label[-disambiguator]]``.
        The timestamp is always 19 characters (``YYYY-MM-DD_HH-MM-SS``).
        """
        stem = Path(filename).stem
        ts_end = 19  # len("YYYY-MM-DD_HH-MM-SS")
        if len(stem) <= ts_end:
            return None
        if stem[ts_end] != "_":
            return None
        remainder = stem[ts_end + 1 :]
        # Strip disambiguator suffix: label-N -> label (N is numeric)
        if "-" in remainder:
            parts = remainder.rsplit("-", 1)
            if parts[1].isdigit():
                remainder = parts[0]
        return remainder if remainder else None

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from ..exceptions import BackupError
from ..logger import get_logger
from ..utils.timestamps import format_backup_timestamp

logger = get_logger("infrastructure.backup_storage")

SHA256_SUFFIX = ".sha256"


class BackupStorage:
    """Manages backup file naming, paths, and retention within BACKUP_DIR."""

    def __init__(self, backup_dir: Path) -> None:
        self._dir = backup_dir

    @property
    def dir(self) -> Path:
        return self._dir

    def generate_name(
        self,
        timestamp: datetime,
        label: str | None = None,
        disambiguator: int | None = None,
    ) -> str:
        """Generate a backup filename from a timestamp and optional label."""
        ts = format_backup_timestamp(timestamp)
        parts = [ts]
        if label:
            parts.append(label)
        if disambiguator is not None:
            parts.append(str(disambiguator))
        return "_".join(parts)

    def backup_path(self, timestamp: datetime, label: str | None = None) -> Path:
        """Resolve a unique backup file path, handling sub-second collisions."""
        base = self.generate_name(timestamp, label)
        candidate = self._dir / f"{base}.plist"
        counter = 1
        while candidate.exists():
            candidate = self._dir / f"{base}-{counter}.plist"
            counter += 1
        return candidate

    def sha256_path(self, backup_file: Path) -> Path:
        """Return the `.sha256` sidecar path for a backup file."""
        return backup_file.with_suffix(backup_file.suffix + SHA256_SUFFIX)

    def compute_sha256(self, path: Path) -> str:
        """Compute the SHA-256 hash of a file."""
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def write_sidecar(self, backup_file: Path, sha256: str) -> Path:
        """Write a `.sha256` sidecar file next to a backup."""
        sidecar = self.sha256_path(backup_file)
        sidecar.write_text(f"{sha256}  {backup_file.name}\n")
        return sidecar

    def read_sidecar(self, backup_file: Path) -> str | None:
        """Read and return the stored SHA-256 from a sidecar, or None."""
        sidecar = self.sha256_path(backup_file)
        if not sidecar.exists():
            return None
        content = sidecar.read_text().strip()
        return content.split()[0] if content else None

    def ensure_dir(self) -> None:
        """Create the backup directory if it does not exist."""
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_backups(self) -> list[Path]:
        """List all `.plist` backup files in the backup directory."""
        if not self._dir.exists():
            return []
        return sorted(
            self._dir.glob("*.plist"),
            key=lambda p: p.name,
        )

    def copy_file(self, src: Path, dest: Path) -> None:
        """Copy a file preserving metadata (used for plist → backup)."""
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            raise BackupError(f"failed to copy {src} → {dest}: {exc}") from exc

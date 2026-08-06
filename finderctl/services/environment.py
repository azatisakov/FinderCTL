from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import BACKUP_DIR, FINDER_PLIST, MIN_SUPPORTED_MACOS
from ..infrastructure.plist_io import PlistReader
from ..logger import get_logger
from ..models import Diagnosis, DiagnosisStatus, SystemState
from .backup import BackupService
from .discovery import PlistSectionWalker
from .finder_process import FinderProcessService

logger = get_logger("services.environment")


class EnvironmentService:
    """Provides system-state inspection and diagnostics."""

    def __init__(
        self,
        finder_plist: Path = FINDER_PLIST,
        backup_dir: Path | None = None,
        finder_process: FinderProcessService | None = None,
    ) -> None:
        self._plist_path = finder_plist
        self._backup_service = BackupService(
            finder_plist=finder_plist,
            backup_dir=backup_dir if backup_dir else BACKUP_DIR,
        )
        self._finder = finder_process or FinderProcessService()
        self._walker = PlistSectionWalker()
        self._reader = PlistReader(finder_plist)

    def get_system_state(self) -> SystemState:
        """Assemble a :class:`SystemState` snapshot of the system."""
        exists = self._plist_path.exists()
        readable = self._is_readable() if exists else False
        writable = self._is_writable() if exists else False
        modified_at = self._get_modified_time() if exists else None

        sections = 0
        backups = self._backup_service.list_backups()
        latest = None
        if backups:
            latest_sorted = sorted(backups, key=lambda b: b.timestamp, reverse=True)
            latest = latest_sorted[0]

        if readable:
            try:
                data = self._reader.read()
                sections = len(self._walker.discover(data))
            except Exception:
                sections = 0

        macos = self._finder.get_macos_version()
        finder = self._finder.get_version()

        return SystemState(
            finder_plist_path=self._plist_path,
            found=exists,
            readable=readable,
            writable=writable,
            macos_version=macos,
            finder_version=finder,
            plist_modified_at=modified_at,
            sections_discovered=sections,
            backup_count=len(backups),
            latest_backup=latest,
        )

    def diagnose(self) -> list[Diagnosis]:
        """Run diagnostic checks and return a list of results."""

        diagnoses: list[Diagnosis] = []

        # Check 1: plist exists
        if self._plist_path.exists():
            diagnoses.append(
                Diagnosis(
                    name="plist_exists",
                    status=DiagnosisStatus.OK,
                    detail=str(self._plist_path),
                )
            )
        else:
            diagnoses.append(
                Diagnosis(
                    name="plist_exists",
                    status=DiagnosisStatus.ERROR,
                    detail=f"{self._plist_path} not found",
                    repairable=False,
                )
            )
            return diagnoses

        # Check 2: plist readable
        readable = self._is_readable()
        diagnoses.append(
            Diagnosis(
                name="plist_readable",
                status=DiagnosisStatus.OK if readable else DiagnosisStatus.ERROR,
                detail="readable" if readable else "permission denied",
            )
        )

        # Check 3: plist writable
        writable = self._is_writable()
        diagnoses.append(
            Diagnosis(
                name="plist_writable",
                status=DiagnosisStatus.OK if writable else DiagnosisStatus.WARN,
                detail="writable" if writable else "not writable (apply will fail)",
                repairable=writable,
            )
        )

        # Check 4: plist valid (parseable)
        try:
            data = self._reader.read()
            sections = len(self._walker.discover(data))
            diagnoses.append(
                Diagnosis(
                    name="plist_valid",
                    status=DiagnosisStatus.OK,
                    detail=f"{sections} view-settings sections found",
                )
            )
        except Exception as exc:
            diagnoses.append(
                Diagnosis(
                    name="plist_valid",
                    status=DiagnosisStatus.ERROR,
                    detail=f"parse error: {exc}",
                    repairable=True,
                )
            )

        # Check 5: latest backup valid
        backups = self._backup_service.list_backups()
        if not backups:
            diagnoses.append(
                Diagnosis(
                    name="latest_backup_valid",
                    status=DiagnosisStatus.WARN,
                    detail="no backups exist; run 'finderctl backup'",
                    repairable=False,
                )
            )
        else:
            latest = sorted(backups, key=lambda b: b.timestamp, reverse=True)[0]
            is_valid = self._backup_service.verify_backup(latest)
            diagnoses.append(
                Diagnosis(
                    name="latest_backup_valid",
                    status=DiagnosisStatus.OK if is_valid else DiagnosisStatus.ERROR,
                    detail=f"latest: {latest.path.name} ({'valid' if is_valid else 'CORRUPT'})",
                    repairable=is_valid,
                )
            )

        # Check 6: backup directory writable
        if BACKUP_DIR.exists():
            diagnoses.append(
                Diagnosis(
                    name="backup_dir_writable",
                    status=DiagnosisStatus.OK,
                    detail=str(BACKUP_DIR),
                )
            )
        else:
            diagnoses.append(
                Diagnosis(
                    name="backup_dir_writable",
                    status=DiagnosisStatus.WARN,
                    detail=f"backup directory does not exist: {BACKUP_DIR}",
                    repairable=True,
                )
            )

        # Check 7: Finder running
        running = self._finder.is_running()
        diagnoses.append(
            Diagnosis(
                name="finder_running",
                status=DiagnosisStatus.OK if running else DiagnosisStatus.WARN,
                detail="running" if running else "not running",
                repairable=running,
            )
        )

        # Check 8: macOS version
        macos_str = self._finder.get_macos_version()
        try:
            major = int(macos_str.split(".")[0])
        except (ValueError, IndexError):
            major = 0

        if major >= MIN_SUPPORTED_MACOS[0]:
            diagnoses.append(
                Diagnosis(
                    name="macos_version",
                    status=DiagnosisStatus.OK,
                    detail=f"macOS {macos_str}",
                )
            )
        else:
            diagnoses.append(
                Diagnosis(
                    name="macos_version",
                    status=DiagnosisStatus.ERROR,
                    detail=f"macOS {macos_str} is below minimum supported version",
                    repairable=False,
                )
            )

        return diagnoses

    def _is_readable(self) -> bool:
        try:
            self._reader.read()
            return True
        except Exception:
            return False

    def _is_writable(self) -> bool:
        test_file = self._plist_path.parent / f".finderctl_write_test_{datetime.now().timestamp()}"
        try:
            test_file.write_text("test")
            test_file.unlink()
            return True
        except OSError:
            return False

    def _get_modified_time(self) -> datetime | None:
        try:
            stat = self._plist_path.stat()
            return datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            return None

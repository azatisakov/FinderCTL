from __future__ import annotations

from pathlib import Path

import pytest

from finderctl.exceptions import BackupError
from finderctl.services.backup import BackupService


def test_create_backup_success(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    record = service.create_backup(label="test")

    assert record.path.exists()
    assert record.is_valid is True
    assert record.label == "test"
    assert record.sha256  # non-empty
    assert record.size_bytes > 0
    # Sidecar should exist
    sidecar = service.storage.sha256_path(record.path)
    assert sidecar.exists()


def test_create_backup_no_source(tmp_path: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=tmp_path / "nonexistent.plist", backup_dir=temp_backup_dir)
    with pytest.raises(BackupError, match="not found"):
        service.create_backup()


def test_create_backup_creates_backup_dir(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "new_backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    assert not backup_dir.exists()
    record = service.create_backup()
    assert backup_dir.exists()
    assert record.path.exists()


def test_list_backups(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    service.create_backup(label="first")
    service.create_backup(label="second")

    backups = service.list_backups()
    assert len(backups) == 2
    assert backups[0].label == "first"
    assert backups[1].label == "second"


def test_get_latest(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    service.create_backup(label="old")
    service.create_backup(label="new")

    latest = service.get_latest()
    assert latest is not None
    assert latest.label == "new"


def test_get_latest_matching(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    service.create_backup(label="apply-a")
    service.create_backup(label="apply-b")

    latest_a = service.get_latest_matching("apply-a")
    assert latest_a is not None
    assert latest_a.label == "apply-a"


def test_verify_backup(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    record = service.create_backup()
    assert service.verify_backup(record) is True

    # Corrupt the file
    record.path.write_bytes(b"corrupted")
    assert service.verify_backup(record) is False


def test_prune_keeps_latest(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    for i in range(5):
        service.create_backup(label=f"b{i}")

    pruned = service.prune(keep=3)
    assert len(pruned) == 2
    remaining = service.list_backups()
    assert len(remaining) == 3
    # The latest is always kept
    assert remaining[-1].label == "b4"


def test_prune_never_removes_all(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    service.create_backup(label="only")
    pruned = service.prune(keep=1)

    remaining = service.list_backups()
    assert len(remaining) == 1
    assert len(pruned) == 0

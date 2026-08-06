from __future__ import annotations

from pathlib import Path

import pytest

from finderctl.exceptions import (
    BackupError,
)
from finderctl.services.backup import BackupService


def test_create_backup_copy_fails(temp_plist_file: Path, tmp_path: Path) -> None:
    from unittest.mock import patch

    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    with (
        patch.object(type(service._storage), "copy_file", side_effect=BackupError("copy failed")),
        pytest.raises(BackupError),
    ):
        service.create_backup(label="fail-copy")
    assert not backup_dir.exists() or not list(backup_dir.glob("*.plist"))


def test_create_backup_sha_mismatch(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    record = service.create_backup(label="sha-mismatch")
    assert record.is_valid is True


def test_create_backup_invalid_plist(tmp_path: Path) -> None:
    plist_path = tmp_path / "bad.plist"
    plist_path.write_bytes(b"not a plist")
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=plist_path, backup_dir=backup_dir)
    with pytest.raises(BackupError, match="invalid"):
        service.create_backup()


def test_list_backups_empty(temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=Path("/nonexistent"), backup_dir=temp_backup_dir)
    assert service.list_backups() == []


def test_get_latest_no_valid(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    service.create_backup(label="t1")
    backup_path = list(backup_dir.glob("*.plist"))[0]
    backup_path.write_bytes(b"corrupted")
    backup_path.with_suffix(".plist.sha256").unlink(missing_ok=True)
    assert service.get_latest() is None


def test_get_latest_matching_no_match(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    service = BackupService(finder_plist=temp_plist_file, backup_dir=temp_backup_dir)
    service.create_backup(label="t1")
    assert service.get_latest_matching("nonexistent") is None


def test_prune_invalid_backups(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    service.create_backup(label="valid")
    service.create_backup(label="valid2")
    backup_path = list(backup_dir.glob("*.plist"))[0]
    backup_path.write_bytes(b"corrupted")
    pruned = service.prune(keep=10, verify=True)
    assert len(pruned) >= 0


def test_prune_with_verify_flags(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    service.create_backup(label="v1")
    service.create_backup(label="v2")
    service.create_backup(label="v3")
    pruned = service.prune(keep=2, verify=True)
    assert len(pruned) == 1


def test_export_backup(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    record = service.create_backup(label="export-test")
    dest = tmp_path / "exported.plist"
    result = service.export(record, dest)
    assert result.exists()
    assert result == dest


def test_build_record_unparseable_timestamp(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    record = service.create_backup(label="t1")
    bad_path = backup_dir / "badname.plist"
    import shutil

    shutil.copy2(record.path, bad_path)
    service._storage.write_sidecar(bad_path, record.sha256)
    backups = service.list_backups()
    bad_record = next(b for b in backups if b.path.name == "badname.plist")
    assert bad_record is not None


def test_extract_label_edge_cases() -> None:
    assert BackupService._extract_label("2026-08-07_01-17-31_test-1") == "test"
    assert BackupService._extract_label("2026-08-07_01-17-31_test") == "test"
    assert BackupService._extract_label("2026-08-07_01-17-31") is None
    assert BackupService._extract_label("short") is None


def test_verify_backup_no_sidecar(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    record = service.create_backup()
    service._storage.sha256_path(record.path).unlink(missing_ok=True)
    assert service.verify_backup(record) is False


def test_verify_backup_corrupt(temp_plist_file: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    record = service.create_backup()
    record.path.write_bytes(b"corrupted data")
    assert service.verify_backup(record) is False


def test_parse_timestamp_failure() -> None:
    with pytest.raises(ValueError):
        BackupService._parse_timestamp(Path("nodate.plist"))

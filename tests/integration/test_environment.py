from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from finderctl.models import DiagnosisStatus
from finderctl.services.environment import EnvironmentService


def _make_finder(version="26.4", macos="26.6", running=True):
    svc = MagicMock()
    svc.get_version.return_value = version
    svc.get_macos_version.return_value = macos
    svc.is_running.return_value = running
    return svc


def test_get_system_state_found(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(),
    )
    state = env.get_system_state()
    assert state.found is True
    assert state.readable is True
    assert state.writable is True
    assert state.sections_discovered > 0
    assert state.latest_backup is None


def test_get_system_state_not_found(tmp_path: Path, temp_backup_dir: Path) -> None:
    env = EnvironmentService(
        finder_plist=tmp_path / "nonexistent.plist",
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(),
    )
    state = env.get_system_state()
    assert state.found is False
    assert state.readable is False
    assert state.writable is False


def test_get_system_state_with_backup(temp_plist_file: Path, tmp_path: Path) -> None:

    backup_dir = tmp_path / "backups"
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=backup_dir,
        finder_process=_make_finder(),
    )
    env._backup_service.create_backup(label="t1")
    state = env.get_system_state()
    assert state.backup_count >= 1
    assert state.latest_backup is not None
    assert state.latest_backup.label == "t1"


def test_diagnose_plist_not_found(tmp_path: Path, temp_backup_dir: Path) -> None:
    env = EnvironmentService(
        finder_plist=tmp_path / "nonexistent.plist",
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(),
    )
    diagnoses = env.diagnose()
    assert len(diagnoses) == 1
    assert diagnoses[0].status == DiagnosisStatus.ERROR
    assert diagnoses[0].name == "plist_exists"


def test_diagnose_warning_when_not_writable(temp_plist_file: Path, tmp_path: Path) -> None:
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=tmp_path / "backups",
        finder_process=_make_finder(),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(env, "_is_writable", lambda: False)
        diagnoses = env.diagnose()
    writable_diag = next(d for d in diagnoses if d.name == "plist_writable")
    assert writable_diag.status == DiagnosisStatus.WARN


def test_diagnose_no_backups(tmp_path: Path, temp_plist_file: Path) -> None:

    backup_dir = tmp_path / "empty_backups"
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=backup_dir,
        finder_process=_make_finder(),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("finderctl.services.environment.BACKUP_DIR", backup_dir)
        diagnoses = env.diagnose()
    backup_diag = next(d for d in diagnoses if d.name == "backup_dir_writable")
    assert backup_diag.status == DiagnosisStatus.WARN


def test_diagnose_finder_not_running(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(running=False),
    )
    diagnoses = env.diagnose()
    running_diag = next(d for d in diagnoses if d.name == "finder_running")
    assert running_diag.status == DiagnosisStatus.WARN


def test_diagnose_old_macos(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(macos="13.0"),
    )
    diagnoses = env.diagnose()
    macos_diag = next(d for d in diagnoses if d.name == "macos_version")
    assert macos_diag.status == DiagnosisStatus.ERROR


def test_diagnose_corrupt_plist(tmp_path: Path, temp_backup_dir: Path) -> None:
    plist_path = tmp_path / "corrupt.plist"
    plist_path.write_bytes(b"not a plist")
    env = EnvironmentService(
        finder_plist=plist_path,
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("finderctl.services.environment.BACKUP_DIR", temp_backup_dir)
        diagnoses = env.diagnose()
    valid_diag = next(d for d in diagnoses if d.name == "plist_valid")
    assert valid_diag.status == DiagnosisStatus.ERROR
    assert valid_diag.repairable is True


def test_diagnose_unparseable_macos(temp_plist_file: Path, temp_backup_dir: Path) -> None:
    env = EnvironmentService(
        finder_plist=temp_plist_file,
        backup_dir=temp_backup_dir,
        finder_process=_make_finder(macos="unknown"),
    )
    diagnoses = env.diagnose()
    macos_diag = next(d for d in diagnoses if d.name == "macos_version")
    assert macos_diag.status == DiagnosisStatus.ERROR


def test_is_writable_failure(tmp_path: Path) -> None:
    env = EnvironmentService(
        finder_plist=tmp_path / "plist.plist",
        backup_dir=tmp_path / "backups",
        finder_process=_make_finder(),
    )
    env._plist_path = tmp_path / "nonexistent_deep" / "sub" / "plist.plist"
    assert env._is_writable() is False


def test_get_modified_time_error(tmp_path: Path) -> None:
    env = EnvironmentService(
        finder_plist=tmp_path / "nonexistent.plist",
        backup_dir=tmp_path / "backups",
        finder_process=_make_finder(),
    )
    assert env._get_modified_time() is None

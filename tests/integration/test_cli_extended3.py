from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from finderctl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_config(monkeypatch, temp_plist_file: Path, temp_backup_dir: Path) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)


def test_cli_verbose_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--verbose", "status", "--json"])
    assert result.exit_code == 0


def test_cli_quiet_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--quiet", "status", "--json"])
    assert result.exit_code == 0


def test_cli_status_human_with_backup(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "latest"])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Latest:" in result.output


def test_cli_apply_bad_scope_cli(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["apply", "sortColumn", "name", "-s", "invalid-scope"])
    assert result.exit_code == 2


def test_cli_apply_backup_error(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    from finderctl.exceptions import BackupError
    from finderctl.services.settings import SettingsService

    with patch.object(SettingsService, "apply", side_effect=BackupError("backup failed")):
        result = runner.invoke(app, ["apply", "sortColumn", "name", "--no-restart", "--json"])
        assert result.exit_code == 1


def test_cli_restore_no_valid_backup_json(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    backup_dir = temp_backup_dir
    from finderctl.services.backup import BackupService

    service = BackupService(finder_plist=temp_plist_file, backup_dir=backup_dir)
    service.create_backup(label="t1")
    # Corrupt all backups so get_latest returns None
    for f in backup_dir.glob("*.plist"):
        f.write_bytes(b"corrupted")
    result = runner.invoke(app, ["restore", "--json"])
    assert result.exit_code == 1


def test_cli_clean_verify_path(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    for i in range(3):
        runner.invoke(app, ["backup", "--label", f"v{i}"])
    result = runner.invoke(app, ["clean", "--keep", "1", "--verify"])
    assert result.exit_code == 0


def test_cli_apply_no_changes_error(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    # Apply a field that won't match any scoped sections
    result = runner.invoke(app, ["apply", "sortColumn", "name", "-s", "trash", "--no-restart"])
    assert result.exit_code != 0


def test_cli_enforce_errors_json(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "-p", str(temp_plist_file), "--dry-run", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["errors"]) >= 1


def test_cli_enforce_errors_human(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "-p", str(temp_plist_file), "--dry-run"])
    assert result.exit_code == 1


def test_cli_enforce_rollback_errors_json(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "--rollback", "-p", str(temp_plist_file), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["errors"]) >= 1


def test_cli_enforce_rollback_errors_human(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "--rollback", "-p", str(temp_plist_file)])
    assert result.exit_code == 1


def test_cli_main_entry() -> None:
    import finderctl.cli as cli_module
    from finderctl.cli import app as cli_app

    assert cli_module.app is cli_app

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from finderctl.cli import app
from finderctl.exceptions import ApplyError
from finderctl.services.settings import SettingsService


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_config(monkeypatch, temp_plist_file: Path, temp_backup_dir: Path) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)


def test_cli_global_verbose_and_quiet(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--verbose", "--help"])
    assert result.exit_code == 0
    result2 = runner.invoke(app, ["--quiet", "--help"])
    assert result2.exit_code == 0


def test_cli_backup_json_output(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["backup", "--label", "json-test", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["path"]
    assert "sha256" in data
    assert data["is_valid"] is True
    assert data["label"] == "json-test"


def test_cli_backup_error_json(
    runner: CliRunner,
    monkeypatch,
    tmp_path: Path,
    temp_backup_dir: Path,
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", tmp_path / "nonexistent.plist")
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)
    result = runner.invoke(app, ["backup", "--json"])
    assert result.exit_code == 1
    assert "error" in result.output


def test_cli_restore_no_match(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "existing"])
    result = runner.invoke(app, ["restore", "nonexistent-label"])
    assert result.exit_code == 2


def test_cli_restore_invalid_backup(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "test"])
    # Corrupt the backup file
    backups = (temp_backup_dir).glob("*.plist")
    for b in backups:
        b.write_bytes(b"corrupted")
    result = runner.invoke(app, ["restore", "test"])
    assert result.exit_code == 1


def test_cli_status_no_latest_backup(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["status", "--json"])
    data = json.loads(result.output)
    assert data["latest_backup"] is None


def test_cli_apply_error_path(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)

    with patch.object(SettingsService, "apply", side_effect=ApplyError("write failed")):
        result = runner.invoke(app, ["apply", "sortColumn", "name", "--no-restart"])
        assert result.exit_code == 1


def test_cli_apply_defaults_error(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)

    from finderctl.exceptions import PlistError

    with patch(
        "finderctl.services.settings.SettingsService.apply_defaults",
        side_effect=PlistError("write failed"),
    ):
        result = runner.invoke(app, ["apply-defaults", "--no-restart"])
        assert result.exit_code == 1


def test_cli_apply_defaults_error_json(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)

    from finderctl.exceptions import PlistError

    with patch(
        "finderctl.services.settings.SettingsService.apply_defaults",
        side_effect=PlistError("write failed"),
    ):
        result = runner.invoke(app, ["apply-defaults", "--no-restart", "--json"])
        assert result.exit_code == 1


def test_cli_clean_verify(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "v1"])
    result = runner.invoke(app, ["clean", "--keep", "1", "--verify", "--json"])
    assert result.exit_code == 0


def test_cli_doctor_with_errors(
    runner: CliRunner,
    monkeypatch,
    tmp_path: Path,
    temp_backup_dir: Path,
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", tmp_path / "nonexistent.plist")
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["overall_status"] == "critical"


def test_cli_enforce_human_output(sample_dsstore: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["enforce", "--path", str(sample_dsstore.parent), "--dry-run"])
    assert result.exit_code == 0
    assert "Scanned" in result.output


def test_cli_enforce_human_with_changes(sample_dsstore: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["enforce", "--path", str(sample_dsstore.parent)])
    assert result.exit_code == 0


def test_cli_enforce_human_no_changes(tmp_path: Path) -> None:
    """Enforce on folder with no DS_Store should show 'No .DS_Store changes needed'."""
    runner = CliRunner()
    result = runner.invoke(app, ["enforce", "--path", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0
    assert "No .DS_Store changes needed." in result.output


def test_cli_enforce_errors(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "-p", str(temp_plist_file), "--dry-run"])
    assert result.exit_code == 1


def test_cli_enforce_rollback_human(sample_dsstore: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["enforce", "--path", str(sample_dsstore.parent)])
    result = runner.invoke(app, ["enforce", "--rollback", "--path", str(sample_dsstore.parent)])
    assert result.exit_code == 0


def test_cli_enforce_rollback_with_errors(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "--rollback", "-p", str(temp_plist_file)])
    assert result.exit_code == 1


def test_cli_print_changes_empty_human() -> None:
    from finderctl.cli import _print_changes

    _print_changes([], dry_run=False, json_output=False)


def test_cli_print_changes_empty_json() -> None:
    from finderctl.cli import _print_changes

    _print_changes([], dry_run=True, json_output=True)


def test_cli_print_clean_report_human() -> None:
    from finderctl.cli import _print_clean_report

    _print_clean_report([], [], keep=10, json_output=False)


def test_cli_print_clean_report_empty_human() -> None:
    from finderctl.cli import _print_clean_report

    _print_clean_report([], [], keep=10, json_output=False)

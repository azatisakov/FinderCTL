from __future__ import annotations

import json
from pathlib import Path

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


def test_cli_backup_human_output(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["backup", "--label", "test-human"])
    assert result.exit_code == 0
    assert "Backup created" in result.output


def test_cli_backup_invalid_label(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["backup", "--label", "bad label!"])
    assert result.exit_code == 2


def test_cli_backup_no_source(
    runner: CliRunner,
    monkeypatch,
    tmp_path: Path,
    temp_backup_dir: Path,
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", tmp_path / "nonexistent.plist")
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)
    result = runner.invoke(app, ["backup", "--label", "fail"], catch_exceptions=True)
    assert result.exit_code == 1


def test_cli_restore_no_backups(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["restore"])
    assert result.exit_code == 1


def test_cli_restore_with_backup(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "restore-test"])
    result = runner.invoke(app, ["restore"])
    assert result.exit_code == 0
    assert "Restoring from" in result.output


def test_cli_restore_ambiguous(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "match"])
    runner.invoke(app, ["backup", "--label", "match2"])
    result = runner.invoke(app, ["restore", "match"])
    assert result.exit_code == 2


def test_cli_status_human_output(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "FinderCTL Status" in result.output


def test_cli_apply_field(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["apply", "sortColumn", "dateModified", "--no-restart", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["changes"]) >= 1


def test_cli_apply_invalid_field(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["apply", "invalidField", "value", "--no-restart"])
    assert result.exit_code == 2


def test_cli_apply_invalid_value_type(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["apply", "calculateAllSizes", "notabool", "--no-restart"])
    assert result.exit_code == 2


def test_cli_apply_scope_all(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(
        app, ["apply", "sortColumn", "dateModified", "--scope", "all", "--no-restart"]
    )
    assert result.exit_code == 0


def test_cli_apply_no_changes(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["apply", "sortColumn", "name", "--no-restart", "--json"])
    assert result.exit_code == 1


def test_cli_apply_bad_scope(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["apply", "sortColumn", "name", "-s", "badscope"])
    assert result.exit_code == 2


def test_cli_apply_bad_scope_via_cli(runner: CliRunner, sample_plist_data) -> None:
    """The scope validation is handled by typer at the CLI level."""
    result = runner.invoke(app, ["apply", "sortColumn", "name", "-s", "badscope"])
    assert result.exit_code != 0


def test_cli_clean_real(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    for i in range(5):
        runner.invoke(app, ["backup", "--label", f"b{i}"])
    result = runner.invoke(app, ["clean", "--keep", "3"])
    assert result.exit_code == 0


def test_cli_clean_zero_keep(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "x"])
    result = runner.invoke(app, ["clean", "--keep", "0"])
    assert result.exit_code == 0


def test_cli_clean_human_output(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    runner.invoke(app, ["backup", "--label", "a"])
    result = runner.invoke(app, ["clean", "--keep", "1"])
    assert result.exit_code == 0
    assert "Kept" in result.output


def test_cli_doctor_human_output(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "FinderCTL Doctor" in result.output


def test_cli_doctor_with_fix(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["doctor", "--fix"])
    assert result.exit_code in (0, 1)


def test_cli_enforce_nonexistent_path(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    _patch_config(monkeypatch, temp_plist_file, temp_backup_dir)
    result = runner.invoke(app, ["enforce", "-p", "/nonexistent/path"])
    assert result.exit_code == 1


def test_cli_enforce_human_output(sample_dsstore: Path) -> None:
    result = CliRunner().invoke(app, ["enforce", "--path", str(sample_dsstore.parent), "--dry-run"])
    assert result.exit_code == 0
    assert "Scanned" in result.output


def test_cli_enforce_rollback(sample_dsstore: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["enforce", "--path", str(sample_dsstore.parent), "--dry-run", "--json"])
    result = runner.invoke(
        app, ["enforce", "--rollback", "--path", str(sample_dsstore.parent), "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "restored" in data


def test_cli_global_verbose(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--verbose", "--help"])
    assert result.exit_code == 0

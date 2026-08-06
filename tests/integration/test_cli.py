from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from finderctl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "FinderCTL" in result.output


def test_cli_status(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)

    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["found"] is True
    assert data["readable"] is True
    assert data["writable"] is True


def test_cli_backup(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)

    result = runner.invoke(app, ["backup", "--label", "test-cli"])
    assert result.exit_code == 0

    result2 = runner.invoke(app, ["status", "--json"])
    import json

    data = json.loads(result2.output)
    assert data["backup_count"] >= 1


def test_cli_apply_defaults_dry_run(
    runner: CliRunner, monkeypatch, temp_plist_file: Path, temp_backup_dir: Path
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)

    result = runner.invoke(app, ["apply-defaults", "--dry-run", "--json"])
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert len(data["changes"]) > 0
    sort_changes = [c for c in data["changes"] if c["field"] == "sortColumn"]
    assert len(sort_changes) >= 1
    assert sort_changes[0]["after"] == "dateModified"


def test_cli_apply_defaults_real_write(
    runner: CliRunner, monkeypatch, temp_plist_file: Path, temp_backup_dir: Path
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)

    result = runner.invoke(app, ["apply-defaults", "--json", "--no-restart"])
    assert result.exit_code == 0


def test_cli_clean_dry_run(
    runner: CliRunner, monkeypatch, temp_plist_file: Path, temp_backup_dir: Path
) -> None:
    import finderctl.cli as cli_module

    # Create some backups first
    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)

    runner.invoke(app, ["backup"])

    result = runner.invoke(app, ["clean", "--dry-run", "--json"])
    assert result.exit_code == 0


def test_cli_doctor(
    runner: CliRunner,
    monkeypatch,
    temp_plist_file: Path,
    temp_backup_dir: Path,
) -> None:
    import finderctl.cli as cli_module

    monkeypatch.setattr(cli_module, "FINDER_PLIST", temp_plist_file)
    monkeypatch.setattr(cli_module, "BACKUP_DIR", temp_backup_dir)

    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert "checks" in data
    assert len(data["checks"]) >= 1


def test_cli_enforce_dry_run(runner: CliRunner, sample_dsstore: Path) -> None:
    result = runner.invoke(
        app,
        ["enforce", "--path", str(sample_dsstore.parent), "--dry-run", "--json"],
    )
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["folders_scanned"] >= 1

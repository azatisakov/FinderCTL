from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from .config import BACKUP_DIR, FINDER_PLIST, MAX_BACKUPS
from .dsstore import DSService
from .exceptions import (
    BackupError,
    FinderProcessError,
    PlistError,
    ValidationError,
)
from .logger import configure_logging, get_logger
from .models import ApplyScope, BackupRecord, Change, DiagnosisStatus
from .services.backup import BackupService
from .services.environment import EnvironmentService
from .services.settings import SettingsService
from .utils.validation import validate_backup_label

app = typer.Typer(
    name="finderctl",
    help="FinderCTL — manage macOS Finder preferences safely",
    add_completion=False,
    no_args_is_help=True,
)

logger = get_logger("cli")


_HOME_DIR = str(Path.home())


# ─── Dependency injection ──────────────────────────────────────────


def _get_settings_service() -> SettingsService:
    return SettingsService(
        finder_plist=FINDER_PLIST,
        backup_service=BackupService(finder_plist=FINDER_PLIST, backup_dir=BACKUP_DIR),
    )


def _get_backup_service() -> BackupService:
    return BackupService(finder_plist=FINDER_PLIST, backup_dir=BACKUP_DIR)


def _get_environment_service() -> EnvironmentService:
    return EnvironmentService(finder_plist=FINDER_PLIST, backup_dir=BACKUP_DIR)


# ─── Global options ────────────────────────────────────────────────

_VERBOSE_OPT = typer.Option(
    False,
    "--verbose",
    "-v",
    help="Enable debug logging (sent to stderr).",
)
_QUIET_OPT = typer.Option(
    False,
    "--quiet",
    "-q",
    help="Suppress all but critical logging.",
)
_JSON_OPT = typer.Option(
    False,
    "--json",
    help="Emit JSON to stdout instead of human-readable text.",
)
_CONFIG_OPT = typer.Option(
    None,
    "--config",
    "-c",
    help="Path to alternate config file.",
)


@app.callback(invoke_without_command=True)
def _global_callback(
    verbose: bool = _VERBOSE_OPT,
    quiet: bool = _QUIET_OPT,
    config: str | None = _CONFIG_OPT,
) -> None:
    """Configure logging based on global flags."""
    if quiet:
        level = 50  # CRITICAL
    elif verbose:
        level = 10  # DEBUG
    else:
        level = 30  # WARNING
    configure_logging(level=level)


# ─── backup ────────────────────────────────────────────────────────


@app.command()
def backup(
    label: str | None = typer.Option(
        None,
        "--label",
        help="Human-readable tag for this backup.",
    ),
    no_verify: bool = typer.Option(
        False,
        "--no-verify",
        help="Skip SHA-256 re-verification (not recommended).",
    ),
    json_output: bool = _JSON_OPT,
) -> None:
    """Create a verified backup of the Finder plist."""
    service = _get_backup_service()
    try:
        validate_backup_label(label) if label else None
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=2) from exc

    try:
        record = service.create_backup(label=label)
    except BackupError as exc:
        logger.error("backup failed: %s", exc)
        if json_output:
            typer.echo(json.dumps({"error": str(exc)}), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "path": str(record.path),
                    "timestamp": record.timestamp.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "size_bytes": record.size_bytes,
                    "sha256": record.sha256,
                    "is_valid": record.is_valid,
                    "label": record.label,
                },
                indent=2,
            )
        )
        return

    typer.echo("✅ Backup created")
    typer.echo(f"   📄 {record.path}")
    typer.echo(f"   📏 {record.size_bytes:,} bytes")
    typer.echo(f"   🔐 SHA-256: {record.sha256[:16]}…")
    typer.echo(f"   ✅ Verified: {record.is_valid}")


# ─── restore ───────────────────────────────────────────────────────


@app.command()
def restore(
    backup: str | None = typer.Argument(
        None,
        help="Backup name prefix or label to restore from.",
    ),
    restart: bool = typer.Option(
        True, "--restart/--no-restart", help="Restart Finder after restore (default: yes)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diff without writing."),
    json_output: bool = _JSON_OPT,
) -> None:
    """Restore Finder settings from a backup."""
    # TODO: implement full backup-selection + diff logic
    service = _get_backup_service()
    backups = service.list_backups()

    if not backups:
        msg = "No backups found. Run 'finderctl backup' first."
        logger.error(msg)
        raise typer.Exit(code=1)

    if backup is None:
        chosen = service.get_latest()
    else:
        candidates = [
            b for b in backups if backup in b.path.name or (b.label and backup in b.label)
        ]
        if not candidates:
            raise typer.Exit(code=2)
        if len(candidates) > 1:
            logger.error("Ambiguous match. Matching backups:")
            for c in candidates:
                typer.echo(f"  {c.path.name}")
            raise typer.Exit(code=2)
        chosen = candidates[0]

    if chosen is None:
        if json_output:
            typer.echo(json.dumps({"error": "no valid backup found"}))
        raise typer.Exit(code=1)

    if not service.verify_backup(chosen):
        raise typer.Exit(code=1)

    typer.echo(f"Restoring from: {chosen.path.name}")
    typer.echo("(restore implementation in progress)")


# ─── status ────────────────────────────────────────────────────────


@app.command()
def status(
    json_output: bool = _JSON_OPT,
) -> None:
    """Show current Finder and backup status."""
    env = _get_environment_service()
    state = env.get_system_state()

    if json_output:
        latest = None
        if state.latest_backup:
            latest = {
                "path": str(state.latest_backup.path),
                "timestamp": state.latest_backup.timestamp.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "sha256": state.latest_backup.sha256,
                "is_valid": state.latest_backup.is_valid,
                "label": state.latest_backup.label,
            }

        typer.echo(
            json.dumps(
                {
                    "finder_plist_path": str(state.finder_plist_path),
                    "found": state.found,
                    "readable": state.readable,
                    "writable": state.writable,
                    "macos_version": state.macos_version,
                    "finder_version": state.finder_version,
                    "plist_modified_at": (
                        state.plist_modified_at.strftime("%Y-%m-%dT%H:%M:%S%z")
                        if state.plist_modified_at
                        else None
                    ),
                    "sections_discovered": state.sections_discovered,
                    "backup_count": state.backup_count,
                    "latest_backup": latest,
                },
                indent=2,
            )
        )
        return

    typer.echo("FinderCTL Status")
    typer.echo("=" * 40)
    typer.echo(f"  Plist:     {state.finder_plist_path}")
    typer.echo(f"  Found:     {'✅' if state.found else '❌'} {state.found}")
    typer.echo(f"  Readable:  {'✅' if state.readable else '❌'} {state.readable}")
    typer.echo(f"  Writable:  {'✅' if state.writable else '❌'} {state.writable}")
    typer.echo(f"  macOS:     {state.macos_version}")
    typer.echo(f"  Finder:    {state.finder_version or 'unknown'}")
    typer.echo(f"  Modified:  {state.plist_modified_at or 'N/A'}")
    typer.echo(f"  Sections:  {state.sections_discovered}")
    typer.echo(f"  Backups:   {state.backup_count}")
    if state.latest_backup:
        typer.echo(
            f"  Latest:    {state.latest_backup.path.name} "
            f"({'✅' if state.latest_backup.is_valid else '❌'})"
        )


# ─── apply ─────────────────────────────────────────────────────────


@app.command(name="apply")
def apply(
    field: str = typer.Argument(..., help="Setting field to change."),
    value: str = typer.Argument(..., help="New value (type inferred from current)."),
    scope: str = typer.Option(
        "default",
        "--scope",
        help="Scope: default|all|standard|desktop|icloud|trash|package|folder:<key>",
    ),
    no_restart: bool = typer.Option(
        False, "--no-restart", help="Do not restart Finder after applying."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing."
    ),
    json_output: bool = _JSON_OPT,
) -> None:
    """Apply a single setting to the Finder plist (always backs up first)."""
    service = _get_settings_service()

    try:
        scope_enum = ApplyScope.from_str(scope)
    except ValueError:
        raise typer.BadParameter(
            f"invalid scope '{scope}'. "
            "Valid: default, all, standard, desktop, icloud, trash, "
            "package, search-recents, meeting-room, folder:<key>"
        ) from None

    try:
        changes = service.apply(
            field=field,
            value=value,
            scope=scope_enum,
            restart=not no_restart,
            dry_run=dry_run,
        )
    except ValidationError as exc:
        logger.error("validation error: %s", exc)
        raise typer.Exit(code=2) from exc
    except (BackupError, FinderProcessError, PlistError) as exc:
        logger.error("apply failed: %s", exc)
        raise typer.Exit(code=1) from exc

    _print_changes(changes, dry_run, json_output)


# ─── apply-defaults ────────────────────────────────────────────────


@app.command(name="apply-defaults")
def apply_defaults(
    no_restart: bool = typer.Option(False, "--no-restart"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = _JSON_OPT,
) -> None:
    """Apply the full default List View configuration to the plist."""
    service = _get_settings_service()
    try:
        changes = service.apply_defaults(restart=not no_restart, dry_run=dry_run)
    except (BackupError, FinderProcessError, PlistError) as exc:
        logger.error("apply-defaults failed: %s", exc)
        raise typer.Exit(code=1) from exc

    _print_changes(changes, dry_run, json_output)


# ─── clean ─────────────────────────────────────────────────────────


@app.command()
def clean(
    keep: int = typer.Option(
        MAX_BACKUPS,
        "--keep",
        "-k",
        help=f"Keep this many most recent verified backups (default: {MAX_BACKUPS}).",
    ),
    verify: bool = typer.Option(False, "--verify", help="Re-verify every backup before pruning."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = _JSON_OPT,
) -> None:
    """Prune old and invalid backups from the backup directory."""
    service = _get_backup_service()
    if keep < 1:
        keep = 1  # never allow 0 — at least keep the latest

    if dry_run:
        backups = service.list_backups()
        valid = [b for b in backups if b.is_valid]
        if verify:
            valid = [b for b in valid if service.verify_backup(b)]
        excess = len(valid) - keep
        pruned = valid[: max(0, excess)] if excess > 0 else []
        _print_clean_report(pruned, valid, keep, json_output)
        return

    pruned = service.prune(keep=keep, verify=verify)
    remaining = service.list_backups()
    _print_clean_report(pruned, remaining, keep, json_output)


# ─── doctor ────────────────────────────────────────────────────────


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Attempt automatic repair where possible."),
    json_output: bool = _JSON_OPT,
) -> None:
    """Run diagnostics and optionally fix issues."""
    env = _get_environment_service()
    diagnoses = env.diagnose()

    if json_output:
        overall = "healthy"
        if any(d.status.value in ("error", "fixable") for d in diagnoses):
            overall = "critical"
        elif any(d.status == DiagnosisStatus.WARN for d in diagnoses):
            overall = "degraded"

        typer.echo(
            json.dumps(
                {
                    "overall_status": overall,
                    "checks": [
                        {
                            "name": d.name,
                            "status": d.status.value,
                            "detail": d.detail,
                            "repairable": d.repairable,
                        }
                        for d in diagnoses
                    ],
                    "repairs_attempted": 1 if fix else 0,
                },
                indent=2,
            )
        )
        if any(d.status.value in ("error", "fixable") for d in diagnoses):
            raise typer.Exit(code=1)
        return

    typer.echo("FinderCTL Doctor")
    typer.echo("=" * 50)
    for d in diagnoses:
        icon = {"ok": "✅", "warn": "⚠️", "error": "❌", "fixable": "🔧"}
        status_icon = icon.get(d.status.value, "?")
        typer.echo(f"  {status_icon} {d.name:30s}  {d.detail or ''}")

    has_errors = any(d.status.value in ("error", "fixable") for d in diagnoses)
    raise typer.Exit(code=1 if has_errors else 0)


# ─── enforce ───────────────────────────────────────────────────────


@app.command()
def enforce(
    paths: list[str] = typer.Option(
        [_HOME_DIR],
        "--path",
        "-p",
        help="Directories to scan (default: ~).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing."
    ),
    rollback: bool = typer.Option(
        False, "--rollback", help="Restore .DS_Store files from FinderCTL backups."
    ),
    json_output: bool = _JSON_OPT,
) -> None:
    """Enforce List View settings across existing .DS_Store files (opt-in)."""
    if rollback:
        _rollback_dsstore(paths, json_output)
        return

    _enforce_dsstore(paths, dry_run, json_output)


# ─── helpers ────────────────────────────────────────────────────


def _parse_scope(scope: str) -> ApplyScope:
    return ApplyScope.from_str(scope)


def _print_changes(changes: list[Change], dry_run: bool, json_output: bool) -> None:
    if json_output:
        import json

        typer.echo(
            json.dumps(
                {
                    "dry_run": dry_run,
                    "changes": [
                        {
                            "scope": c.scope,
                            "field": c.field,
                            "before": str(c.before),
                            "after": str(c.after),
                            "key_path": list(c.key_path),
                        }
                        for c in changes
                    ],
                },
                indent=2,
            )
        )
        return

    if not changes:
        typer.echo("No changes needed.")
        return

    for c in changes:
        preview = "DRY-RUN " if dry_run else "    "
        typer.echo(f"  {preview} {c.scope}.{c.field}: {c.before!r} → {c.after!r}")

    typer.echo(
        f"\n  {len(changes)} change(s) applied."
        if not dry_run
        else f"\n  {len(changes)} change(s) would be applied (dry-run)."
    )


def _print_clean_report(
    pruned: list[BackupRecord], remaining: list[BackupRecord], keep: int, json_output: bool
) -> None:

    if json_output:
        import json

        typer.echo(
            json.dumps(
                {
                    "pruned": len(pruned),
                    "kept": len(remaining),
                    "keep_target": keep,
                    "remaining": [str(b.path.name) for b in remaining],
                },
                indent=2,
            )
        )
        return

    if pruned:
        typer.echo(f"Pruned {len(pruned)} backup(s):")
        for b in pruned:
            typer.echo(f"  🗑  {b.path.name}")
    else:
        typer.echo("No backups to prune.")
    typer.echo(f"\nKept {len(remaining)} backup(s).")


def _enforce_dsstore(paths: list[str], dry_run: bool, json_output: bool) -> None:
    """Enforce List View settings across .DS_Store files in given paths."""
    service = DSService()
    all_changes: list[Change] = []
    folders_scanned = 0
    errors: list[str] = []

    for raw_path in paths:
        folder = Path(raw_path).expanduser()
        if not folder.is_dir():
            errors.append(f"not a directory: {folder}")
            continue

        for root, _dirnames, filenames in os.walk(folder):
            root_path = Path(root)
            if ".DS_Store" in filenames:
                folders_scanned += 1
                try:
                    changes = service.enforce_folder(root_path, dry_run=dry_run)
                    all_changes.extend(changes)
                except Exception as exc:
                    errors.append(f"{root_path}: {exc}")

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "dry_run": dry_run,
                    "folders_scanned": folders_scanned,
                    "changes": [
                        {
                            "scope": c.scope,
                            "field": c.field,
                            "before": str(c.before),
                            "after": str(c.after),
                            "key_path": list(c.key_path),
                        }
                        for c in all_changes
                    ],
                    "errors": errors,
                },
                indent=2,
            )
        )
        return

    if all_changes:
        for c in all_changes:
            preview = "DRY-RUN " if dry_run else "    "
            typer.echo(f"  {preview} {c.scope}.{c.field}: {c.before!r} → {c.after!r}")
    else:
        typer.echo("No .DS_Store changes needed.")

    typer.echo(
        f"\n  Scanned {folders_scanned} folders, "
        f"{len(all_changes)} change(s)"
        f"{' would be applied (dry-run)' if dry_run else ' applied'}."
    )

    if errors:
        typer.echo(f"\n  {len(errors)} error(s):")
        for err in errors:
            typer.echo(f"    ❌ {err}")
        raise typer.Exit(code=1)


def _rollback_dsstore(paths: list[str], json_output: bool) -> None:
    """Restore .DS_Store files from FinderCTL backups in given paths."""
    service = DSService()
    restored = 0
    errors: list[str] = []

    for raw_path in paths:
        folder = Path(raw_path).expanduser()
        if not folder.is_dir():
            errors.append(f"not a directory: {folder}")
            continue

        for root, _dirnames, filenames in os.walk(folder):
            root_path = Path(root)
            if ".DS_Store" in filenames:
                try:
                    service.restore_dsstore(root_path / ".DS_Store")
                    restored += 1
                except Exception as exc:
                    errors.append(f"{root_path}: {exc}")

    if json_output:
        typer.echo(json.dumps({"restored": restored, "errors": errors}, indent=2))
        return

    typer.echo(f"Restored {restored} .DS_Store file(s).")
    if errors:
        for err in errors:
            typer.echo(f"  ❌ {err}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

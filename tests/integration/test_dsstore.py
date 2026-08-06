from __future__ import annotations

from pathlib import Path

import pytest

from finderctl.dsstore import DSService, DSStoreReader
from finderctl.exceptions import DSStoreNotFoundError


def test_dsstore_reader_reads_lsvp(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    lsvp = reader.get_list_view(".")
    assert lsvp is not None
    assert lsvp["sortColumn"] == "name"
    assert lsvp["calculateAllSizes"] is False
    assert "columns" in lsvp
    assert isinstance(lsvp["columns"], dict)
    reader.close()


def test_dsstore_reader_has_list_view(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    assert reader.has_list_view(".") is True
    reader.close()


def test_dsstore_reader_entries(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    entries = reader.entries()
    assert len(entries) >= 2
    codes = {e.code for e in entries}
    assert b"lsvp" in codes
    assert b"vSrn" in codes
    reader.close()


def test_dsstore_reader_empty_dsstore(empty_dsstore: Path) -> None:
    reader = DSStoreReader(empty_dsstore)
    assert reader.has_list_view(".") is False
    assert reader.get_list_view(".") is None
    reader.close()


def test_dsstore_enforce_dry_run_detects_sort_column(sample_dsstore: Path) -> None:
    service = DSService()
    changes = service.enforce_folder(Path(sample_dsstore.parent), dry_run=True)
    assert len(changes) > 0
    sort_changes = [c for c in changes if "sortColumn" in c.field]
    assert len(sort_changes) >= 1
    assert sort_changes[0].before == "name"
    assert sort_changes[0].after == "dateModified"


def test_dsstore_enforce_dry_run_detects_columns(sample_dsstore: Path) -> None:
    service = DSService()
    changes = service.enforce_folder(Path(sample_dsstore.parent), dry_run=True)
    col_changes = [c for c in changes if "columns" in c.field]
    assert len(col_changes) >= 1


def test_dsstore_enforce_dry_run_detects_calculate_all_sizes(
    sample_dsstore: Path,
) -> None:
    service = DSService()
    changes = service.enforce_folder(Path(sample_dsstore.parent), dry_run=True)
    sizes_changes = [c for c in changes if "calculateAllSizes" in c.field]
    assert len(sizes_changes) >= 1
    assert sizes_changes[0].before is False
    assert sizes_changes[0].after is True


def test_dsstore_enforce_dry_run_empty_folder(empty_dsstore: Path) -> None:
    service = DSService()
    changes = service.enforce_folder(Path(empty_dsstore.parent), dry_run=True)
    # Should report that a . entry would be created
    create_changes = [c for c in changes if "create" in c.field]
    assert len(create_changes) >= 1


def test_dsstore_enforce_creates_backup(sample_dsstore: Path) -> None:
    service = DSService()
    original_bytes = sample_dsstore.read_bytes()

    service.enforce_folder(Path(sample_dsstore.parent), dry_run=False)

    backup_path = sample_dsstore.with_name(sample_dsstore.name + ".finderctl.bak")
    assert backup_path.exists()
    assert backup_path.read_bytes() == original_bytes


def test_dsstore_enforce_modifies_file(sample_dsstore: Path) -> None:
    service = DSService()
    original_bytes = sample_dsstore.read_bytes()

    service.enforce_folder(Path(sample_dsstore.parent), dry_run=False)

    new_bytes = sample_dsstore.read_bytes()
    assert new_bytes != original_bytes

    # Verify the changes were applied
    reader = DSStoreReader(sample_dsstore)
    lsvp = reader.get_list_view(".")
    assert lsvp is not None
    assert lsvp["sortColumn"] == "dateModified"
    assert lsvp["calculateAllSizes"] is True
    reader.close()


def test_dsstore_enforce_rollback(sample_dsstore: Path) -> None:
    service = DSService()
    original_bytes = sample_dsstore.read_bytes()

    service.enforce_folder(Path(sample_dsstore.parent), dry_run=False)
    assert sample_dsstore.read_bytes() != original_bytes

    service.restore_dsstore(sample_dsstore)
    assert sample_dsstore.read_bytes() == original_bytes


def test_dsstore_enforce_nonexistent_folder(tmp_path: Path) -> None:
    service = DSService()
    changes = service.enforce_folder(tmp_path, dry_run=True)
    assert len(changes) == 0


def test_dsstore_backup_nonexistent(tmp_path: Path) -> None:
    service = DSService()
    with pytest.raises(DSStoreNotFoundError):
        service.backup_dsstore(tmp_path / ".DS_Store")


def test_dsstore_restore_no_backup(tmp_path: Path) -> None:
    service = DSService()
    ds_path = tmp_path / ".DS_Store"
    ds_path.write_text("dummy")
    with pytest.raises(DSStoreNotFoundError):
        service.restore_dsstore(ds_path)


def test_dsstore_columns_synced(sample_dsstore: Path) -> None:
    service = DSService()
    service.enforce_folder(Path(sample_dsstore.parent), dry_run=False)

    reader = DSStoreReader(sample_dsstore)
    lsvp = reader.get_list_view(".")
    assert lsvp is not None

    columns = lsvp["columns"]
    assert isinstance(columns, dict)
    # dateModified should be visible
    assert columns["dateModified"]["visible"] is True
    # dateAdded should be... let's check it exists in target columns
    assert "kind" in columns
    assert columns["kind"]["visible"] is True
    reader.close()

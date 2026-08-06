from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from finderctl.dsstore import (
    DSService,
    DSStoreEntry,
    DSStoreReader,
    DSStoreWriter,
)
from finderctl.exceptions import (
    DSRevertibleError,
    DSStoreCorruptionError,
    DSStoreNotFoundError,
)


def test_dsstore_entry_repr() -> None:
    e = DSStoreEntry("folder", b"lsvp", {"a": 1})
    assert "folder" in repr(e)
    assert "lsvp" in repr(e)


def test_dsstore_reader_get_list_view_plist_returns_none(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    assert reader.get_list_view_plist(".") is None
    reader.close()


def test_dsstore_reader_get_list_view_not_dict(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    result = reader.get_list_view(".")
    assert isinstance(result, dict)
    reader.close()


def test_dsstore_reader_get_window_state(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    state = reader.get_window_state(".")
    assert state is None
    reader.close()


def test_dsstore_reader_has_list_view_false(empty_dsstore: Path) -> None:
    reader = DSStoreReader(empty_dsstore)
    assert reader.has_list_view(".") is False
    reader.close()


def test_dsstore_reader_entries_full(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    entries = reader.entries()
    codes = {e.code for e in entries}
    assert b"lsvp" in codes
    assert b"vSrn" in codes
    for e in entries:
        assert e.filename
    reader.close()


def test_dsstore_writer_path_property(sample_dsstore: Path) -> None:
    writer = DSStoreWriter(sample_dsstore)
    assert writer.path == sample_dsstore
    writer.close()


def test_dsstore_writer_set_window_state(tmp_path: Path) -> None:
    ds_path = tmp_path / ".DS_Store"
    writer = DSStoreWriter(ds_path)
    writer.set_window_state(".", {"ShowStatusBar": True})
    writer.commit()
    reader = DSStoreReader(ds_path)
    assert reader.get_window_state(".") == {"ShowStatusBar": True}
    reader.close()


def test_dsstore_writer_set_view_root(tmp_path: Path) -> None:
    ds_path = tmp_path / ".DS_Store"
    writer = DSStoreWriter(ds_path)
    writer.set_view_root(".", 1)
    writer.commit()
    reader = DSStoreReader(ds_path)
    entries = reader.entries()
    vSrn = [e for e in entries if e.code == b"vSrn"]
    assert len(vSrn) == 1
    reader.close()


def test_dsstore_writer_delete_record(tmp_path: Path) -> None:
    ds_path = tmp_path / ".DS_Store"
    writer = DSStoreWriter(ds_path)
    writer.set_window_state(".", {"ShowStatusBar": True})
    writer.delete_record(".", b"bwsp")
    writer.commit()
    reader = DSStoreReader(ds_path)
    assert reader.get_window_state(".") is None
    reader.close()


def test_dsstore_writer_delete_nonexistent_no_error(tmp_path: Path) -> None:
    ds_path = tmp_path / ".DS_Store"
    writer = DSStoreWriter(ds_path)
    writer.delete_record(".", b"nonexistent")
    writer.close()


def test_dsstore_writer_new_file_mode(tmp_path: Path) -> None:
    ds_path = tmp_path / ".DS_Store"
    assert not ds_path.exists()
    writer = DSStoreWriter(ds_path)
    writer.set_window_state(".", {"ShowStatusBar": True})
    writer.commit()
    assert ds_path.exists()
    reader = DSStoreReader(ds_path)
    assert reader.get_window_state(".") == {"ShowStatusBar": True}
    reader.close()


def test_dssservice_backup_dsstore_nonexistent(tmp_path: Path) -> None:
    service = DSService()
    with pytest.raises(DSStoreNotFoundError):
        service.backup_dsstore(tmp_path / "missing.DS_Store")


def test_dssservice_restore_no_backup(tmp_path: Path) -> None:
    service = DSService()
    ds_path = tmp_path / ".DS_Store"
    ds_path.write_bytes(b"data")
    with pytest.raises(DSStoreNotFoundError):
        service.restore_dsstore(ds_path)


def test_dssservice_enforce_folder_not_exists(tmp_path: Path) -> None:
    service = DSService()
    changes = service.enforce_folder(tmp_path, dry_run=True)
    assert changes == []


def test_dssservice_enforce_corruption_error(tmp_path: Path) -> None:
    ds_path = tmp_path / ".DS_Store"
    ds_path.write_bytes(b"\x00\x00\x00\x00")
    service = DSService()
    with pytest.raises(DSStoreCorruptionError):
        service.enforce_folder(tmp_path, dry_run=True)


def test_dssservice_enforce_revertible_error(sample_dsstore: Path) -> None:
    """Force a write failure to trigger DSRevertibleError."""

    service = DSService()
    with patch("finderctl.dsstore.DSStoreWriter") as mock_cls:
        mock_writer = mock_cls.return_value
        mock_writer.commit.side_effect = RuntimeError("disk full")
        with pytest.raises(DSRevertibleError, match="failed to patch"):
            service.enforce_folder(Path(sample_dsstore.parent), dry_run=False)


def test_dssservice_create_root_entry_creates_lsvp(empty_dsstore: Path) -> None:
    """enforce on an empty DS_Store should report changes (root entry needed)."""
    service = DSService()
    changes = service.enforce_folder(Path(empty_dsstore.parent), dry_run=False)
    assert len(changes) > 0


def test_dssservice_sync_columns_width_preservation(tmp_path: Path) -> None:
    """Test that existing column widths are preserved."""
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["lsvp"] = {
        "sortColumn": "dateModified",
        "calculateAllSizes": True,
        "columns": {
            "name": {"ascending": False, "visible": True, "width": 500, "index": 0},
        },
        "viewOptionsVersion": 1,
    }
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    service = DSService()
    service.enforce_folder(tmp_path, dry_run=False)

    reader = DSStoreReader(ds_path)
    lsvp = reader.get_list_view(".")
    assert lsvp is not None
    name_col = lsvp["columns"].get("name", {})
    assert name_col.get("width") == 500
    reader.close()


def test_dssservice_sync_columns_width_uses_target(tmp_path: Path) -> None:
    """Test that out-of-range widths use target default."""
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["lsvp"] = {
        "sortColumn": "name",
        "calculateAllSizes": False,
        "columns": {},
        "viewOptionsVersion": 1,
    }
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    service = DSService()
    service.enforce_folder(tmp_path, dry_run=False)

    reader = DSStoreReader(ds_path)
    lsvp = reader.get_list_view(".")
    assert lsvp is not None
    name_col = lsvp["columns"].get("name", {})
    assert name_col.get("width") == 187
    reader.close()


def test_dssservice_get_list_view_plist(sample_dsstore: Path) -> None:
    """Verify get_list_view_plist returns None for dict-only entries."""
    reader = DSStoreReader(sample_dsstore)
    assert reader.get_list_view_plist(".") is None
    reader.close()


def test_dssservice_lsvC_patch(tmp_path: Path) -> None:
    """Test patching a file that has lsvC binary plist entries."""
    import plistlib

    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    lsv_c_data = plistlib.dumps(
        {"sortColumn": "name", "calculateAllSizes": False}, fmt=plistlib.FMT_BINARY
    )
    store["."]["lsvC"] = (b"blob", bytearray(lsv_c_data))
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    original_bytes = ds_path.read_bytes()

    service = DSService()
    service.enforce_folder(tmp_path, dry_run=False)
    new_bytes = ds_path.read_bytes()
    assert new_bytes != original_bytes

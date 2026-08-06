from __future__ import annotations

from pathlib import Path

from finderctl.dsstore import DSService, DSStoreReader


def test_dsstore_reader_path_property(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    assert reader.path == sample_dsstore
    reader.close()


def test_dsstore_reader_get_list_view_none_when_not_dict(tmp_path: Path) -> None:
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["lsvp"] = (b"blob", bytearray(b"not a dict"))
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    reader = DSStoreReader(ds_path)
    assert reader.get_list_view(".") is None
    reader.close()


def test_dsstore_reader_get_list_view_plist_valid(sample_dsstore: Path) -> None:
    """get_list_view_plist should return None when no lsvC exists."""
    reader = DSStoreReader(sample_dsstore)
    assert reader.get_list_view_plist(".") is None
    reader.close()


def test_dsstore_reader_get_list_view_plist_with_data(tmp_path: Path) -> None:
    import plistlib

    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    payload = plistlib.dumps({"sortColumn": "name"}, fmt=plistlib.FMT_BINARY)
    store["."]["lsvC"] = (b"blob", bytearray(payload))
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    reader = DSStoreReader(ds_path)
    result = reader.get_list_view_plist(".")
    assert result is not None
    assert result["sortColumn"] == "name"
    reader.close()


def test_dsstore_reader_get_list_view_plist_invalid_bytes(tmp_path: Path) -> None:
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["lsvC"] = (b"blob", bytearray(b"notbplist"))
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    reader = DSStoreReader(ds_path)
    assert reader.get_list_view_plist(".") is None
    reader.close()


def test_dsstore_reader_get_window_state(tmp_path: Path) -> None:
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["bwsp"] = {"ShowStatusBar": True}
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    reader = DSStoreReader(ds_path)
    assert reader.get_window_state(".") == {"ShowStatusBar": True}
    reader.close()


def test_dsstore_reader_get_window_state_not_dict(tmp_path: Path) -> None:
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["bwsp"] = (b"blob", bytearray(b"notdict"))
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    reader = DSStoreReader(ds_path)
    assert reader.get_window_state(".") is None
    reader.close()


def test_dsstore_writer_has_list_view_true(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    assert reader.has_list_view(".") is True
    reader.close()


def test_dssservice_get_list_view_plist(sample_dsstore: Path) -> None:
    reader = DSStoreReader(sample_dsstore)
    assert reader.get_list_view_plist(".") is None
    reader.close()


def test_dssservice_create_root_entry_dry_run_empty_folder(empty_dsstore: Path) -> None:
    """enforce_folder on empty_dsstore should report create change in dry-run."""
    service = DSService()
    changes = service.enforce_folder(Path(empty_dsstore.parent), dry_run=True)
    create_changes = [c for c in changes if "create" in c.field]
    assert len(create_changes) >= 1


def test_dssservice_preserve_width_in_range(tmp_path: Path) -> None:
    """Width in 20-2000 range is preserved."""
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    store = DSStore.open(str(ds_path), "w+")
    store["."]["lsvp"] = {
        "sortColumn": "name",
        "calculateAllSizes": False,
        "columns": {
            "name": {"ascending": False, "visible": True, "width": 100, "index": 0},
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
    assert lsvp["columns"]["name"]["width"] == 100
    reader.close()


def test_dssservice_columns_already_correct_no_change(tmp_path: Path) -> None:
    """If columns already match target exactly, no column change is reported."""
    from ds_store import DSStore

    ds_path = tmp_path / ".DS_Store"
    service = DSService()
    # Build the exact target columns dict
    target_cols = service._sync_columns({})
    store = DSStore.open(str(ds_path), "w+")
    store["."]["lsvp"] = {
        "sortColumn": "dateModified",
        "calculateAllSizes": True,
        "columns": target_cols,
        "viewOptionsVersion": 1,
    }
    store["."]["vSrn"] = (b"long", 1)
    store.close()

    changes = service.enforce_folder(tmp_path, dry_run=True)
    col_changes = [c for c in changes if "columns" in c.field]
    assert len(col_changes) == 0

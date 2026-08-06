from __future__ import annotations

from pathlib import Path

from finderctl.plist import discover_sections, read_plist, write_plist


def test_read_plist(temp_plist_file: Path) -> None:
    data = read_plist(temp_plist_file)
    assert "FK_DefaultListViewSettingsV2" in data
    assert data["NewWindowTarget"] == "PfHm"


def test_write_plist_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "out.plist"
    data = {"key": "value", "num": 42, "flag": True}
    write_plist(path, data)
    assert path.exists()
    read_back = read_plist(path)
    assert read_back == data


def test_discover_sections(temp_plist_file: Path) -> None:
    data = read_plist(temp_plist_file)
    locations = discover_sections(data)
    names = {loc.key_path[-1] for loc in locations}
    assert "FK_DefaultListViewSettingsV2" in names


def test_write_plist_atomic(tmp_path: Path) -> None:
    path = tmp_path / "atomic.plist"
    write_plist(path, {"a": 1})
    assert not (path.with_suffix(".plist.tmp")).exists()
    assert path.exists()

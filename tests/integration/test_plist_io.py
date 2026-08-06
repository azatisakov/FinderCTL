from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from finderctl.exceptions import PlistNotFoundError, PlistParseError, PlistPermissionError
from finderctl.infrastructure.plist_io import PlistReader, PlistWriter


def test_read_valid_plist(temp_plist_file: Path) -> None:
    reader = PlistReader(temp_plist_file)
    data = reader.read()
    assert "FK_DefaultListViewSettingsV2" in data
    assert data["NewWindowTarget"] == "PfHm"


def test_read_nonexistent_raises(temp_plist_file: Path) -> None:
    reader = PlistReader(temp_plist_file.parent / "nonexistent.plist")
    with pytest.raises(PlistNotFoundError):
        reader.read()


def test_write_atomic_replaces_file(temp_plist_file: Path) -> None:
    writer = PlistWriter(temp_plist_file)
    reader = PlistReader(temp_plist_file)

    data = reader.read()
    data["NewWindowTarget"] = "PfDesk"
    writer.write_atomic(data)

    reader2 = PlistReader(temp_plist_file)
    data2 = reader2.read()
    assert data2["NewWindowTarget"] == "PfDesk"


def test_write_atomic_preserves_existing_keys(temp_plist_file: Path) -> None:
    writer = PlistWriter(temp_plist_file)
    original = PlistReader(temp_plist_file).read()

    writer.write_atomic(original)
    re_read = PlistReader(temp_plist_file).read()
    assert set(re_read.keys()) == set(original.keys())


def test_write_atomic_is_atomic_on_failure(temp_plist_file: Path) -> None:
    """If serialization fails, the original file should be untouched."""
    writer = PlistWriter(temp_plist_file)
    original_bytes = temp_plist_file.read_bytes()

    bad_data: dict = {"unsupported": object()}  # not plist-serializable

    with pytest.raises(PlistParseError):
        writer.write_atomic(bad_data)

    assert temp_plist_file.read_bytes() == original_bytes


def test_write_bytes_atomic_replaces_file(temp_plist_file: Path) -> None:
    writer = PlistWriter(temp_plist_file)
    new_bytes = b"\x00\x05\x16\x07\x00\x00\x00\x00DEADBEEF"
    writer.write_bytes_atomic(new_bytes)
    assert temp_plist_file.read_bytes() == new_bytes
    assert not temp_plist_file.with_suffix(".plist.tmp").exists()


def test_write_bytes_atomic_permission_error(tmp_path: Path) -> None:
    path = tmp_path / "out.plist"
    path.write_bytes(b"hello")
    writer = PlistWriter(path)
    with (
        patch.object(Path, "open", side_effect=PermissionError("denied")),
        pytest.raises((PlistPermissionError, PlistParseError)),
    ):
        writer.write_bytes_atomic(b"data")


def test_read_corrupt_plist(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.plist"
    path.write_bytes(b"not a plist at all")
    reader = PlistReader(path)
    with pytest.raises(PlistParseError):
        reader.read()


def test_write_atomic_permission_error(tmp_path: Path) -> None:
    path = tmp_path / "protected.plist"
    path.write_bytes(b"\x00\x00\x00\x00")
    writer = PlistWriter(path)
    with (
        patch.object(Path, "open", side_effect=PermissionError("denied")),
        pytest.raises((PlistPermissionError, PlistParseError)),
    ):
        writer.write_atomic({"key": "value"})


def test_write_atomic_opens_in_same_directory(tmp_path: Path) -> None:
    writer = PlistWriter(tmp_path / "out.plist")
    writer.write_atomic({"a": 1})
    assert (tmp_path / "out.plist").exists()


def test_plist_reader_permission_error(tmp_path: Path) -> None:
    path = tmp_path / "protected.plist"
    path.write_bytes(b"\x00\x00\x00\x00")
    path.chmod(0o000)
    try:
        reader = PlistReader(path)
        with pytest.raises((PlistPermissionError, PlistParseError)):
            reader.read()
    finally:
        path.chmod(0o644)

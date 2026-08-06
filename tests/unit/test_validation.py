from __future__ import annotations

import pytest

from finderctl.utils.validation import (
    sanitize_scope_folder,
    validate_backup_label,
    validate_folder_path,
)


def test_validate_backup_label_none() -> None:
    assert validate_backup_label(None) is None


def test_validate_backup_label_valid() -> None:
    assert validate_backup_label("pre-apply-defaults") == "pre-apply-defaults"
    assert validate_backup_label("test-backup_1") == "test-backup_1"


def test_validate_backup_label_invalid_chars() -> None:
    with pytest.raises(ValueError):
        validate_backup_label("test.backup")  # . not allowed
    with pytest.raises(ValueError):
        validate_backup_label("test/backup")  # / not allowed
    with pytest.raises(ValueError):
        validate_backup_label("test backup")  # space not allowed


def test_validate_backup_label_too_long() -> None:
    long_label = "a" * 65
    with pytest.raises(ValueError):
        validate_backup_label(long_label)


def test_validate_folder_path_relative(tmp_path) -> None:
    import os

    os.chdir(tmp_path)
    result = validate_folder_path("relative/path")
    assert result.is_absolute()


def test_validate_folder_path_absolute() -> None:
    result = validate_folder_path("/Users/test")
    assert result == __import__("pathlib").Path("/Users/test")


def test_sanitize_scope_folder_valid() -> None:
    assert sanitize_scope_folder("folder:Documents") == "Documents"
    assert sanitize_scope_folder("folder:test_folder") == "test_folder"


def test_sanitize_scope_folder_invalid() -> None:
    with pytest.raises(ValueError):
        sanitize_scope_folder("Documents")  # missing "folder:" prefix
    with pytest.raises(ValueError):
        sanitize_scope_folder("folder:invalid name")  # space not allowed


def test_sanitize_scope_folder_bad_chars() -> None:
    with pytest.raises(ValueError):
        sanitize_scope_folder("folder:hello world")  # space
    with pytest.raises(ValueError):
        sanitize_scope_folder("folder:hello/world")  # slash

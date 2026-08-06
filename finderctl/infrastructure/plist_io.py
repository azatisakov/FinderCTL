from __future__ import annotations

import contextlib
import os
import plistlib
from pathlib import Path
from typing import Any

from ..exceptions import (
    PlistNotFoundError,
    PlistParseError,
    PlistPermissionError,
)
from ..logger import get_logger

logger = get_logger("infrastructure.plist_io")


class PlistReader:
    """Reads a plist file from disk using ``plistlib``."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> dict[str, Any]:
        """Load and return the plist as a dict.

        Raises:
            PlistNotFoundError: if the file does not exist.
            PlistPermissionError: if the file is not readable.
            PlistParseError: if the file is corrupt or malformed.
        """
        if not self._path.exists():
            raise PlistNotFoundError(f"plist not found: {self._path}")

        try:
            with self._path.open("rb") as fh:
                result = plistlib.load(fh)
            return result if isinstance(result, dict) else dict(result)
        except PermissionError as exc:
            raise PlistPermissionError(
                f"cannot read plist (permission denied): {self._path}"
            ) from exc
        except (plistlib.InvalidFileException, ValueError) as exc:
            raise PlistParseError(f"plist is corrupt or malformed: {self._path}") from exc
        except OSError as exc:
            raise PlistParseError(f"cannot read plist: {self._path} ({exc})") from exc


class PlistWriter:
    """Writes a plist file atomically (temp file + ``os.replace``)."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path

    @property
    def path(self) -> Path:
        return self._path

    def write_atomic(self, data: dict[str, Any]) -> None:
        """Serialize ``data`` to binary plist and atomically replace the target.

        The temp file is created in the same directory to guarantee
        same-filesystem ``os.replace`` semantics.

        Raises:
            PlistPermissionError: if the file is not writable.
            PlistParseError: if serialization or I/O fails.
        """
        try:
            payload = plistlib.dumps(data, fmt=plistlib.FMT_BINARY)
        except (TypeError, ValueError) as exc:
            raise PlistParseError(f"cannot serialize plist: {exc}") from exc

        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with tmp.open("wb") as fh:
                fh.write(payload)
                fh.flush()
                os_fsync(fh.fileno())
            tmp.replace(self._path)
            _fsync_parent(self._path)
        except PermissionError as exc:
            raise PlistPermissionError(
                f"cannot write plist (permission denied): {self._path}"
            ) from exc
        except OSError as exc:
            raise PlistParseError(f"cannot write plist: {self._path} ({exc})") from exc
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def write_bytes_atomic(self, data: bytes) -> None:
        """Write raw bytes atomically (used for restore from backup copy)."""
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with tmp.open("wb") as fh:
                fh.write(data)
                fh.flush()
                os_fsync(fh.fileno())
            tmp.replace(self._path)
            _fsync_parent(self._path)
        except PermissionError as exc:
            raise PlistPermissionError(
                f"cannot write plist (permission denied): {self._path}"
            ) from exc
        except OSError as exc:
            raise PlistParseError(f"cannot write plist: {self._path} ({exc})") from exc
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


def os_fsync(fd: int) -> None:
    """Wrap ``os.fsync`` for durability."""
    with contextlib.suppress(OSError):
        os.fsync(fd)


def _fsync_parent(path: Path) -> None:
    """Best-effort fsync of the parent directory."""
    parent = path.parent
    with contextlib.suppress(OSError):
        fd = os.open(str(parent), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)

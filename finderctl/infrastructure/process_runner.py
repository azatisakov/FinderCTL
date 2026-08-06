from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ..exceptions import FinderProcessError
from ..logger import get_logger

logger = get_logger("infrastructure.process_runner")


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Immutable result of a subprocess execution."""

    returncode: int
    stdout: str
    stderr: str


class SubprocessRunner:
    """Thin wrapper around ``subprocess.run`` with structured results."""

    def run(
        self,
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = False,
    ) -> ProcessResult:
        """Execute a command and return a ``ProcessResult``.

        Raises:
            FinderProcessError: if the command times out or fails (when
                ``check`` is True).
        """
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        except subprocess.TimeoutExpired as exc:
            raise FinderProcessError(
                f"command timed out after {timeout}s: {' '.join(cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            raise FinderProcessError(f"command not found: {cmd[0]}") from exc
        except subprocess.CalledProcessError as exc:
            if check:
                raise FinderProcessError(
                    f"command failed ({exc.returncode}): {exc.stderr.strip()}"
                ) from exc
            return ProcessResult(
                returncode=exc.returncode,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )

        return ProcessResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

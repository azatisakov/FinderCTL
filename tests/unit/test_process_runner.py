from __future__ import annotations

import pytest

from finderctl.exceptions import FinderProcessError
from finderctl.infrastructure.process_runner import ProcessResult, SubprocessRunner


def test_run_success() -> None:
    runner = SubprocessRunner()
    result = runner.run(["true"])
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_run_stdout_captured() -> None:
    runner = SubprocessRunner()
    result = runner.run(["sh", "-c", "echo hello"])
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_run_nonzero_without_check() -> None:
    runner = SubprocessRunner()
    result = runner.run(["sh", "-c", "echo oops 1>&2; exit 3"], check=False)
    assert result.returncode == 3
    assert "oops" in result.stderr


def test_run_timeout_raises() -> None:
    runner = SubprocessRunner()
    with pytest.raises(FinderProcessError, match="timed out"):
        runner.run(["sleep", "10"], timeout=0.05)


def test_run_file_not_found() -> None:
    runner = SubprocessRunner()
    with pytest.raises(FinderProcessError, match="command not found"):
        runner.run(["nonexistent-command-xyz"])


def test_run_called_process_error_with_check() -> None:
    runner = SubprocessRunner()
    with pytest.raises(FinderProcessError, match="command failed"):
        runner.run(["sh", "-c", "exit 1"], check=True)


def test_run_called_process_error_without_check() -> None:
    runner = SubprocessRunner()
    result = runner.run(["sh", "-c", "echo err 1>&2; exit 1"], check=False)
    assert result.returncode == 1
    assert "err" in result.stderr


def test_process_result_immutable() -> None:
    import dataclasses

    result = ProcessResult(returncode=0, stdout="x", stderr="y")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.returncode = 1

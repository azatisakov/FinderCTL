from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from finderctl.infrastructure.process_runner import ProcessResult, SubprocessRunner
from finderctl.services.finder_process import (
    FinderProcessService,
    FinderRestartError,
)


def make_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> ProcessResult:
    return ProcessResult(returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def mock_runner() -> MagicMock:
    r = MagicMock(spec=SubprocessRunner)
    return r


def test_is_running_true(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(returncode=0, stdout="1234")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.is_running() is True


def test_is_running_false(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(returncode=1, stdout="")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.is_running() is False


def test_is_running_no_stdout(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(returncode=0, stdout="   ")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.is_running() is False


def test_get_version_success(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(stdout="26.4")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.get_version() == "26.4"


def test_get_version_no_output(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(stdout="")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.get_version() is None


def test_get_macos_version_success(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(stdout="26.6.1")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.get_macos_version() == "26.6.1"


def test_get_macos_version_failure(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(returncode=1, stdout="")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.get_macos_version() == "unknown"


def test_restart_not_running(mock_runner: MagicMock) -> None:
    mock_runner.run.side_effect = [
        make_result(returncode=1, stdout=""),
    ]
    svc = FinderProcessService(runner=mock_runner)
    svc.restart()
    mock_runner.run.assert_called_once()


def test_restart_kills_finder(mock_runner: MagicMock) -> None:
    mock_runner.run.side_effect = [
        make_result(returncode=0, stdout="1234"),
        make_result(returncode=0),
    ]
    svc = FinderProcessService(runner=mock_runner)
    svc.restart()


def test_restart_killall_fails(mock_runner: MagicMock) -> None:
    mock_runner.run.side_effect = [
        make_result(returncode=0, stdout="1234"),
        make_result(returncode=1, stderr="no finder"),
    ]
    svc = FinderProcessService(runner=mock_runner)
    with pytest.raises(FinderRestartError, match="killall"):
        svc.restart()


def test_wait_for_relaunch_success(mock_runner: MagicMock) -> None:
    mock_runner.run.side_effect = [
        make_result(returncode=1, stdout=""),
        make_result(returncode=0, stdout="5678"),
    ]
    svc = FinderProcessService(runner=mock_runner)
    assert svc.wait_for_relaunch(timeout=5) is True


def test_wait_for_relaunch_timeout(mock_runner: MagicMock) -> None:
    mock_runner.run.return_value = make_result(returncode=1, stdout="")
    svc = FinderProcessService(runner=mock_runner)
    assert svc.wait_for_relaunch(timeout=0.3) is False

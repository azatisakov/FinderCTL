from __future__ import annotations

from ..infrastructure.process_runner import SubprocessRunner
from ..logger import get_logger

logger = get_logger("services.finder_process")


class FinderProcessService:
    """Manages Finder process detection, restart, and version probing."""

    def __init__(self, runner: SubprocessRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def is_running(self) -> bool:
        """Return True if the Finder process is currently running."""
        result = self._runner.run(["pgrep", "-x", "Finder"], check=False)
        if result.returncode == 0 and result.stdout.strip():
            logger.debug("Finder is running (pid(s): %s)", result.stdout.strip())
            return True
        logger.debug("Finder is not running")
        return False

    def get_version(self) -> str | None:
        """Return the Finder bundle version, or None if undetected."""
        result = self._runner.run(
            [
                "defaults",
                "read",
                "/System/Library/CoreServices/Finder.app/Contents/Info.plist",
                "CFBundleShortVersionString",
            ],
            check=False,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            if version:
                logger.debug("Finder version: %s", version)
                return version
        logger.warning("could not determine Finder version")
        return None

    def get_macos_version(self) -> str:
        """Return the macOS product version string."""
        result = self._runner.run(["sw_vers", "-productVersion"], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        logger.warning("could not determine macOS version")
        return "unknown"

    def restart(self) -> None:
        """Restart the Finder process via ``killall Finder``.

        This forces Finder to reload its plist from disk, flushing all
        in-memory caches.
        """
        if not self.is_running():
            logger.info("Finder not running; skipping restart")
            return

        logger.info("restarting Finder")
        result = self._runner.run(["killall", "Finder"], check=False)
        if result.returncode != 0:
            raise FinderRestartError(f"killall Finder failed: {result.stderr.strip()}")
        logger.info("Finder killed; waiting for relaunch")

    def wait_for_relaunch(self, timeout: float = 30.0) -> bool:
        """Poll until Finder reappears or timeout expires.

        Returns:
            True if Finder is running, False if it didn't relaunch in time.
        """
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_running():
                logger.info("Finder relaunched successfully")
                return True
            time.sleep(0.25)

        logger.warning("Finder did not relaunch within %.1fs", timeout)
        return False


class FinderRestartError(Exception):
    """Raised when Finder cannot be restarted."""

from __future__ import annotations

from typing import Any

from ..config import SEARCH_KEYS
from ..exceptions import DiscoveryError
from ..logger import get_logger
from ..models import SectionLocation

logger = get_logger("services.discovery")


class PlistSectionWalker:
    """Recursively discovers all view-settings sections in a plist tree.

    The walker traverses any nested combination of ``dict``, ``list``,
    and scalar values, yielding a :class:`SectionLocation` whenever a
    key in :data:`~finderctl.config.SEARCH_KEYS` is encountered.

    This is a **pure function** — it never mutates the input tree and
    performs no I/O.
    """

    def __init__(self, search_keys: tuple[str, ...] = SEARCH_KEYS) -> None:
        self._search_keys = frozenset(search_keys)

    def discover(self, data: Any) -> list[SectionLocation]:
        """Discover all sections in a plist-loaded tree.

        Args:
            data: The root object from ``plistlib.load()`` (typically
                a ``dict``).

        Returns:
            A list of :class:`SectionLocation` objects, one per
            matched key, in tree-traversal order.

        Raises:
            DiscoveryError: if a search-key node is found with a
                non-dict value (invalid plist structure).
        """
        results: list[SectionLocation] = []
        self._walk(data, (), results)
        logger.debug("discovered %d view-settings sections", len(results))
        return results

    def discover_in_folder(self, data: Any, folder_key: str) -> list[SectionLocation]:
        """Discover sections within a specific top-level folder key.

        If ``folder_key`` does not exist at the root, returns an empty
        list rather than raising.
        """
        if not isinstance(data, dict):
            return []
        subtree = data.get(folder_key)
        if subtree is None:
            return []
        if not isinstance(subtree, dict):
            raise DiscoveryError(
                f"expected dict for section '{folder_key}', got {type(subtree).__name__}"
            )
        results: list[SectionLocation] = []
        self._walk(subtree, (folder_key,), results)
        return results

    def _walk(
        self,
        node: Any,
        key_path: tuple[str, ...],
        results: list[SectionLocation],
    ) -> None:
        """Recursively walk the tree, collecting matching sections."""
        if isinstance(node, dict):
            for key, value in node.items():
                current_path = key_path + (key,)
                if key in self._search_keys:
                    if not isinstance(value, dict):
                        raise DiscoveryError(
                            f"section '{key}' at path {current_path} "
                            f"has non-dict value ({type(value).__name__})"
                        )
                    results.append(SectionLocation(key_path=current_path, data=value))
                self._walk(value, current_path, results)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                indexed_path = key_path + (f"[{index}]",)
                self._walk(item, indexed_path, results)

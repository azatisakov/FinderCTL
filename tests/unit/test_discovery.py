from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from finderctl.exceptions import DiscoveryError
from finderctl.services.discovery import PlistSectionWalker


@pytest.fixture
def walker() -> PlistSectionWalker:
    return PlistSectionWalker()


def test_discover_finds_top_level_sections(
    walker: PlistSectionWalker, sample_plist_data: dict
) -> None:
    locations = walker.discover(sample_plist_data)
    section_names = {loc.key_path[-1] for loc in locations}
    assert "FK_DefaultListViewSettingsV2" in section_names
    assert "ExtendedListViewSettingsV2" in section_names or "ListViewSettings" in section_names


def test_discover_nested_sections(walker: PlistSectionWalker, sample_plist_data: dict) -> None:
    locations = walker.discover(sample_plist_data)
    standard_paths = [loc.key_path for loc in locations if "StandardViewSettings" in loc.key_path]
    assert len(standard_paths) > 0
    # Should have paths like ("StandardViewSettings", "ExtendedListViewSettingsV2")
    nested = [p for p in standard_paths if len(p) >= 2]
    assert len(nested) > 0


def test_discover_in_folder(walker: PlistSectionWalker, sample_plist_data: dict) -> None:
    locations = walker.discover_in_folder(sample_plist_data, "StandardViewSettings")
    assert len(locations) > 0
    for loc in locations:
        assert loc.key_path[0] == "StandardViewSettings"


def test_discover_in_folder_not_found(walker: PlistSectionWalker, sample_plist_data: dict) -> None:
    locations = walker.discover_in_folder(sample_plist_data, "NonExistentKey")
    assert locations == []


def test_discover_does_not_mutate_input(
    walker: PlistSectionWalker, sample_plist_data: dict
) -> None:
    import copy

    data_copy = copy.deepcopy(sample_plist_data)
    walker.discover(sample_plist_data)
    # Input should not be modified
    assert sample_plist_data == data_copy


def test_discover_empty_dict(walker: PlistSectionWalker) -> None:
    assert walker.discover({}) == []


def test_discover_no_matches(walker: PlistSectionWalker) -> None:
    data = {"some_key": {"value": 1}, "another": [1, 2, 3]}
    assert walker.discover(data) == []


def test_discover_finds_in_lists(walker: PlistSectionWalker) -> None:
    data = {
        "items": [
            {"ListViewSettings": {"sortColumn": "name"}},
            {"ExtendedListViewSettingsV2": {"sortColumn": "name"}},
        ]
    }
    locations = walker.discover(data)
    assert len(locations) == 2


@given(
    data=st.recursive(
        st.dictionaries(
            st.text(min_size=1, max_size=50),
            st.one_of(
                st.none(),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.text(),
                st.booleans(),
            ),
            min_size=0,
            max_size=10,
        ),
        lambda children: st.one_of(
            children,
            st.lists(children, min_size=0, max_size=5),
        ),
        max_leaves=50,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_discover_is_consistent_on_random_data(data: dict) -> None:
    """Walker should not crash on any random nested structure."""
    w = PlistSectionWalker()
    try:
        locations = w.discover(data)
        for loc in locations:
            assert isinstance(loc.key_path, tuple)
            assert isinstance(loc.data, dict)
    except DiscoveryError:
        pass
    except Exception as exc:
        pytest.fail(f"Walker crashed on random data: {exc}")


@given(
    sections=st.lists(
        st.sampled_from(["ListViewSettings", "ExtendedListViewSettingsV2"]),
        min_size=1,
        max_size=5,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_discover_finds_all_sections_in_deep_nesting(sections: list[str]) -> None:
    """Walker should find all sections even when deeply nested."""
    nested: dict[str, Any] = {}
    current = nested
    for section in sections[:-1]:
        current[section] = {}
        current = current[section]
    current[sections[-1]] = {"sortColumn": "name"}

    w = PlistSectionWalker()
    locations = w.discover(nested)
    found_names = [loc.key_path[-1] for loc in locations]
    for section in sections:
        assert section in found_names

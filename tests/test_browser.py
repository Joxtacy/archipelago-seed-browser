"""Unit tests for the non-UI helpers in :mod:`seed_browser.browser`.

Tests that exercise Kivy widgets are out of scope here — UI is
verified manually per PLAN.md §8.
"""

from __future__ import annotations

from pathlib import Path

from seed_browser.browser import sort_seeds
from seed_browser.scanner import Seed


def _seed(
    name: str,
    *,
    mtime: float,
    size: int,
    slots: int,
    last_hosted: float | None = None,
) -> Seed:
    return Seed(
        path=Path(f"/tmp/{name}"),
        mtime=mtime,
        size_bytes=size,
        slots=[(i, f"P{i}", "Game") for i in range(1, slots + 1)],
        has_save=last_hosted is not None,
        last_hosted=last_hosted,
    )


def test_sort_seeds_by_date_desc_is_default_order() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=20, slots=2)
    c = _seed("c", mtime=3.0, size=30, slots=3)
    assert [s.path.name for s in sort_seeds([a, b, c], key="date", desc=True)] == [
        "c",
        "b",
        "a",
    ]


def test_sort_seeds_by_size_asc() -> None:
    a = _seed("a", mtime=1.0, size=300, slots=1)
    b = _seed("b", mtime=2.0, size=100, slots=2)
    c = _seed("c", mtime=3.0, size=200, slots=3)
    assert [s.path.name for s in sort_seeds([a, b, c], key="size", desc=False)] == [
        "b",
        "c",
        "a",
    ]


def test_sort_seeds_by_slots_desc() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=10, slots=5)
    c = _seed("c", mtime=3.0, size=10, slots=3)
    assert [s.path.name for s in sort_seeds([a, b, c], key="slots", desc=True)] == [
        "b",
        "c",
        "a",
    ]


def test_sort_seeds_hosted_desc_puts_most_recent_first_unhosted_last() -> None:
    """Hosted seeds sort by ``last_hosted`` descending; unhosted ones
    trail at the bottom regardless of direction."""
    a = _seed("a-never", mtime=5.0, size=10, slots=1)  # never hosted
    b = _seed("b-old", mtime=1.0, size=10, slots=1, last_hosted=100.0)
    c = _seed("c-recent", mtime=2.0, size=10, slots=1, last_hosted=300.0)
    d = _seed("d-mid", mtime=3.0, size=10, slots=1, last_hosted=200.0)
    assert [s.path.name for s in sort_seeds([a, b, c, d], key="hosted", desc=True)] == [
        "c-recent",
        "d-mid",
        "b-old",
        "a-never",
    ]


def test_sort_seeds_hosted_asc_still_pins_unhosted_to_the_bottom() -> None:
    """Direction flip reverses hosted block but leaves unhosted at the
    end — never-hosted seeds aren't sortable by hosted time and would
    only confuse users at the top."""
    a = _seed("a-never", mtime=5.0, size=10, slots=1)
    b = _seed("b-old", mtime=1.0, size=10, slots=1, last_hosted=100.0)
    c = _seed("c-recent", mtime=2.0, size=10, slots=1, last_hosted=300.0)
    assert [s.path.name for s in sort_seeds([a, b, c], key="hosted", desc=False)] == [
        "b-old",
        "c-recent",
        "a-never",
    ]


def test_sort_seeds_hosted_unhosted_block_ordered_by_mtime_desc() -> None:
    """Within the unhosted block, fall back to descending generation
    time so the most recently *generated* unhosted seed is at the top
    of the trailing block."""
    a = _seed("a-newer", mtime=10.0, size=10, slots=1)
    b = _seed("b-older", mtime=5.0, size=10, slots=1)
    c = _seed("c-hosted", mtime=1.0, size=10, slots=1, last_hosted=100.0)
    assert [s.path.name for s in sort_seeds([a, b, c], key="hosted", desc=True)] == [
        "c-hosted",
        "a-newer",
        "b-older",
    ]


def test_sort_seeds_does_not_mutate_input() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=20, slots=2)
    original = [a, b]
    sort_seeds(original, key="size", desc=True)
    assert original == [a, b]

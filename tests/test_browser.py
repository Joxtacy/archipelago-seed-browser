"""Unit tests for the non-UI helpers in :mod:`seed_browser.browser`.

Tests that exercise Kivy widgets are out of scope here — UI is
verified manually per PLAN.md §8.
"""

from __future__ import annotations

from pathlib import Path

from seed_browser.browser import sort_seeds
from seed_browser.scanner import Seed


def _seed(name: str, *, mtime: float, size: int, slots: int) -> Seed:
    return Seed(
        path=Path(f"/tmp/{name}"),
        mtime=mtime,
        size_bytes=size,
        slots=[(i, f"P{i}", "Game") for i in range(1, slots + 1)],
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


def test_sort_seeds_does_not_mutate_input() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=20, slots=2)
    original = [a, b]
    sort_seeds(original, key="size", desc=True)
    assert original == [a, b]

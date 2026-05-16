"""Unit tests for the non-UI helpers in :mod:`seed_browser.browser`.

Tests that exercise Kivy widgets are out of scope here — UI is
verified manually per PLAN.md §8.
"""

from __future__ import annotations

from pathlib import Path

from seed_browser.browser import (
    _format_seed_row,
    _format_version,
    filter_seeds,
    sort_seeds,
)
from seed_browser.scanner import Seed


def _seed(
    name: str,
    *,
    mtime: float,
    size: int,
    slots: int,
    last_hosted: float | None = None,
    game: str = "Game",
) -> Seed:
    return Seed(
        path=Path(f"/tmp/{name}"),
        mtime=mtime,
        size_bytes=size,
        slots=[(i, f"P{i}", game) for i in range(1, slots + 1)],
        games=[(game, slots)] if slots else [],
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


def test_format_version_renders_dotted_string() -> None:
    assert _format_version((0, 6, 7)) == "0.6.7"


def test_format_version_handles_missing() -> None:
    assert _format_version(None) is None


def test_format_seed_row_does_not_include_generator_version() -> None:
    """Generator version lives in the expanded panel only; the
    collapsed row stays compact."""
    seed = Seed(
        path=Path("/tmp/AP_42.zip"),
        mtime=1_700_000_000.0,
        size_bytes=34_500,
        slots=[(1, "P1", "Jigsaw"), (2, "P2", "Minecraft")],
        games=[("Jigsaw", 1), ("Minecraft", 1)],
        generator_version=(0, 6, 7),
    )
    label = _format_seed_row(seed)
    assert "AP " not in label
    assert "0.6.7" not in label
    assert "2 slots" in label


def test_sort_seeds_by_game_uses_first_listed_game_case_insensitive() -> None:
    """Sort by the headlining (first-seen) game. Case-folding so
    differently-capitalized game names cluster."""
    a = _seed("a", mtime=1.0, size=10, slots=1, game="Minecraft")
    b = _seed("b", mtime=2.0, size=10, slots=1, game="archipelago")
    c = _seed("c", mtime=3.0, size=10, slots=1, game="Jigsaw")
    assert [s.path.name for s in sort_seeds([a, b, c], key="game", desc=False)] == [
        "b",
        "c",
        "a",
    ]


def test_sort_seeds_by_game_desc_reverses_the_block() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1, game="Minecraft")
    b = _seed("b", mtime=2.0, size=10, slots=1, game="Jigsaw")
    assert [s.path.name for s in sort_seeds([a, b], key="game", desc=True)] == [
        "a",
        "b",
    ]


def test_sort_seeds_by_game_trails_seeds_without_decoded_games() -> None:
    """Error / unscanned seeds (empty games list) have nothing to sort
    by; they fall to the end regardless of direction."""
    no_game = Seed(path=Path("/tmp/no-game"), mtime=5.0, size_bytes=10)
    a = _seed("a", mtime=1.0, size=10, slots=1, game="Minecraft")
    assert [s.path.name for s in sort_seeds([no_game, a], key="game", desc=True)] == [
        "a",
        "no-game",
    ]
    assert [s.path.name for s in sort_seeds([no_game, a], key="game", desc=False)] == [
        "a",
        "no-game",
    ]


def test_filter_seeds_empty_query_returns_full_list() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=10, slots=1)
    assert filter_seeds([a, b], "") == [a, b]
    assert filter_seeds([a, b], "   ") == [a, b]


def test_filter_seeds_matches_filename_case_insensitive() -> None:
    a = Seed(path=Path("/tmp/AP_55176.zip"), mtime=1.0, size_bytes=10)
    b = Seed(path=Path("/tmp/AP_60686.zip"), mtime=2.0, size_bytes=10)
    assert filter_seeds([a, b], "55176") == [a]
    assert filter_seeds([a, b], "AP_") == [a, b]


def test_filter_seeds_matches_game_name() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1, game="Minecraft")
    b = _seed("b", mtime=2.0, size=10, slots=1, game="Jigsaw")
    assert filter_seeds([a, b], "mine") == [a]
    assert filter_seeds([a, b], "JIG") == [b]


def test_filter_seeds_matches_slot_or_player_name() -> None:
    a = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slots=[(1, "Joxtacy", "Minecraft")],
        games=[("Minecraft", 1)],
    )
    b = Seed(
        path=Path("/tmp/b"),
        mtime=2.0,
        size_bytes=10,
        slots=[(1, "BobAP", "Minecraft")],
        games=[("Minecraft", 1)],
    )
    assert filter_seeds([a, b], "jox") == [a]
    assert filter_seeds([a, b], "bob") == [b]


def test_filter_seeds_returns_empty_when_nothing_matches() -> None:
    a = _seed("AP_55.zip", mtime=1.0, size=10, slots=1, game="Minecraft")
    assert filter_seeds([a], "nothing-this-rare") == []


def test_sort_seeds_does_not_mutate_input() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=20, slots=2)
    original = [a, b]
    sort_seeds(original, key="size", desc=True)
    assert original == [a, b]

"""Unit tests for the non-UI helpers in :mod:`seed_browser.browser`.

Tests that exercise Kivy widgets are out of scope here — UI is
verified manually per PLAN.md §8.
"""

from __future__ import annotations

from pathlib import Path

from seed_browser.browser import (
    _format_seed_footer_lines,
    _format_seed_row,
    _format_slot_progress,
    _format_version,
    filter_by_state,
    filter_seeds,
    seed_state,
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


def test_format_seed_row_strips_size_spoiler_and_hosted_timestamp() -> None:
    """Collapsed row stays compact: date, slot count, games, and a
    bare 'hosted' marker. Size, spoiler, and the hosted timestamp move
    to the expanded footer to avoid wrapping on multi-game seeds."""
    seed = Seed(
        path=Path("/tmp/AP_42.zip"),
        mtime=1_700_000_000.0,
        size_bytes=34_500,
        slots=[(1, "P1", "Jigsaw"), (2, "P2", "Minecraft")],
        games=[("Jigsaw", 1), ("Minecraft", 1)],
        generator_version=(0, 6, 7),
        has_spoiler=True,
        has_save=True,
        last_hosted=1_700_000_000.0,
    )
    label = _format_seed_row(seed)
    assert "2 slots" in label
    assert "Jigsaw" in label
    assert "hosted" in label
    # Things that moved to the footer:
    assert "KB" not in label
    assert "(spoiler)" not in label
    # Bare 'hosted' is fine; the inline 'hosted YYYY-MM-DD HH:MM'
    # timestamp moved to the footer.
    assert "hosted 2" not in label
    assert "AP " not in label  # generator version still in footer only


def test_format_seed_footer_splits_into_three_lines_when_all_known() -> None:
    """Full metadata seed renders three footer lines: filename+size,
    AP versions, last-hosted timestamp. Spoiler is intentionally
    omitted (button signals it)."""
    seed = Seed(
        path=Path("/tmp/AP_42.zip"),
        mtime=1_700_000_000.0,
        size_bytes=34_500,
        slots=[(1, "P1", "Jigsaw")],
        games=[("Jigsaw", 1)],
        generator_version=(0, 6, 7),
        min_server_version=(0, 5, 0),
        has_spoiler=True,
        has_save=True,
        last_hosted=1_700_000_000.0,
    )
    lines = _format_seed_footer_lines(seed)
    assert len(lines) == 3
    assert lines[0].startswith("AP_42.zip")
    assert "KB" in lines[0]
    assert "AP 0.6.7" in lines[1]
    assert "AP 0.5.0" in lines[1]
    assert "last hosted" in lines[2]
    # Spoiler is intentionally not in any footer line.
    assert not any("spoiler" in line for line in lines)


def test_format_seed_footer_minimal_for_unhosted_unsigned_seed() -> None:
    """When metadata is unknown, footer is a single line: filename + size."""
    seed = Seed(path=Path("/tmp/AP_42.zip"), mtime=1.0, size_bytes=1024)
    assert _format_seed_footer_lines(seed) == ["AP_42.zip  ·  1.0 KB"]


def test_format_seed_footer_omits_version_line_when_unknown() -> None:
    """A hosted seed whose multidata didn't decode still shows the
    last-hosted line — it just doesn't have an AP-version line in the
    middle."""
    seed = Seed(
        path=Path("/tmp/AP_42.zip"),
        mtime=1.0,
        size_bytes=10,
        has_save=True,
        last_hosted=1_700_000_000.0,
    )
    lines = _format_seed_footer_lines(seed)
    assert len(lines) == 2
    assert lines[0].startswith("AP_42.zip")
    assert "last hosted" in lines[1]


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


def test_format_slot_progress_empty_when_no_save_data() -> None:
    seed = Seed(path=Path("/tmp/a"), mtime=1.0, size_bytes=10, slot_totals={1: 87})
    # We know the total but the seed hasn't been hosted — nothing to
    # display per-slot.
    assert _format_slot_progress(seed, 1) == ""


def test_format_slot_progress_shows_zero_n_for_unplayed_slot_in_hosted_seed() -> None:
    """Once a seed has been hosted, every slot with a known total
    surfaces '0/N checks' even if the slot's client never connected —
    keeps the per-slot display consistent across the whole seed."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        has_save=True,
        slot_totals={1: 87, 2: 50},
        slot_checked={1: 12},  # only slot 1 has any saved progress
    )
    assert _format_slot_progress(seed, 1) == "  ·  12/87 checks"
    assert _format_slot_progress(seed, 2) == "  ·  0/50 checks"


def test_format_slot_progress_renders_fraction_when_both_known() -> None:
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_totals={1: 87},
        slot_checked={1: 12},
    )
    assert _format_slot_progress(seed, 1) == "  ·  12/87 checks"


def test_format_slot_progress_omits_total_when_unknown() -> None:
    """Total comes from multidata, checked from the save. If multidata
    decode failed but a save still exists, fall back to just the count."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_checked={1: 5},
    )
    assert _format_slot_progress(seed, 1) == "  ·  5 checks"


def test_format_slot_progress_appends_done_marker_on_completion() -> None:
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_totals={1: 87},
        slot_checked={1: 87},
        slot_complete={1: True},
    )
    assert _format_slot_progress(seed, 1) == "  ·  87/87 checks  ·  done"


def test_format_slot_progress_done_without_check_counts() -> None:
    """A slot can report goal status even if location_checks is empty
    (e.g. game completion that isn't location-driven)."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_complete={1: True},
    )
    assert _format_slot_progress(seed, 1) == "  ·  done"


def test_sort_seeds_does_not_mutate_input() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=20, slots=2)
    original = [a, b]
    sort_seeds(original, key="size", desc=True)
    assert original == [a, b]


def test_seed_state_no_save_is_untouched() -> None:
    seed = Seed(path=Path("/tmp/a"), mtime=1.0, size_bytes=10)
    assert seed_state(seed) == "untouched"


def test_seed_state_save_without_completion_is_in_progress() -> None:
    """A hosted seed where no player has reached the goal is still in
    flight, even if checks are zero (just started, paused, etc.)."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_types={1: "player", 2: "player"},
        slot_complete={1: False, 2: False},
        has_save=True,
        last_hosted=100.0,
    )
    assert seed_state(seed) == "in_progress"


def test_seed_state_all_player_slots_complete_is_complete() -> None:
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_types={1: "player", 2: "player"},
        slot_complete={1: True, 2: True},
        has_save=True,
        last_hosted=100.0,
    )
    assert seed_state(seed) == "complete"


def test_seed_state_ignores_non_player_slots_for_completion() -> None:
    """Group / spectator slots don't have a goal to reach, so they
    shouldn't gate the 'complete' classification."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_types={1: "player", 2: "group", 3: "spectator"},
        slot_complete={1: True},  # group/spectator never report goal
        has_save=True,
        last_hosted=100.0,
    )
    assert seed_state(seed) == "complete"


def test_seed_state_hosted_with_no_player_slots_stays_in_progress() -> None:
    """Spectator/group-only seeds have no completion signal — calling
    them 'complete' would be a lie, so they stay 'in_progress'."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_types={1: "spectator"},
        has_save=True,
        last_hosted=100.0,
    )
    assert seed_state(seed) == "in_progress"


def test_seed_state_partial_completion_is_in_progress() -> None:
    """Multiple players, only some done → still in progress. 'Complete'
    means everyone finished."""
    seed = Seed(
        path=Path("/tmp/a"),
        mtime=1.0,
        size_bytes=10,
        slot_types={1: "player", 2: "player"},
        slot_complete={1: True, 2: False},
        has_save=True,
        last_hosted=100.0,
    )
    assert seed_state(seed) == "in_progress"


def test_filter_by_state_all_returns_full_copy() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)
    b = _seed("b", mtime=2.0, size=20, slots=1, last_hosted=100.0)
    seeds = [a, b]
    result = filter_by_state(seeds, "all")
    assert result == seeds
    assert result is not seeds  # fresh list, not aliased


def test_filter_by_state_untouched_excludes_hosted_seeds() -> None:
    a = _seed("a", mtime=1.0, size=10, slots=1)  # untouched
    b = _seed("b", mtime=2.0, size=20, slots=1, last_hosted=100.0)  # hosted
    assert [s.path.name for s in filter_by_state([a, b], "untouched")] == ["a"]


def test_filter_by_state_complete_picks_only_finished_seeds() -> None:
    done = Seed(
        path=Path("/tmp/done"),
        mtime=1.0,
        size_bytes=10,
        slot_types={1: "player"},
        slot_complete={1: True},
        has_save=True,
        last_hosted=100.0,
    )
    in_flight = Seed(
        path=Path("/tmp/wip"),
        mtime=2.0,
        size_bytes=10,
        slot_types={1: "player"},
        has_save=True,
        last_hosted=100.0,
    )
    untouched = Seed(path=Path("/tmp/raw"), mtime=3.0, size_bytes=10)
    assert [s.path.name for s in filter_by_state(
        [done, in_flight, untouched], "complete"
    )] == ["done"]


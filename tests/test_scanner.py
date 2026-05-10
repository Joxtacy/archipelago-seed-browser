"""Unit tests for :mod:`seed_browser.scanner`.

Tests that need AP's restricted unpickler are gated on
``ARCHIPELAGO_SRC`` being set (see ``conftest.py``); they're skipped
otherwise so the suite stays runnable without an AP checkout.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from seed_browser.scanner import (
    Seed,
    _collapse_games,
    scan_directory,
    scan_seed,
)


def _write_seed_zip(
    path: Path,
    seed_id: str,
    *,
    multidata_blob: bytes | None = b"\x00\x00",
    spoiler: bool = True,
    patch_files: tuple[tuple[int, str, str], ...] = (),
) -> None:
    """Build a fixture AP_*.zip with controllable contents."""
    with zipfile.ZipFile(path, "w") as zf:
        if multidata_blob is not None:
            zf.writestr(f"AP_{seed_id}.archipelago", multidata_blob)
        if spoiler:
            zf.writestr(f"AP_{seed_id}_Spoiler.txt", "spoiler content")
        for slot, player, suffix in patch_files:
            zf.writestr(f"AP_{seed_id}_P{slot}_{player}.{suffix}", b"patch")


def test_scan_seed_reports_namelist_flags(tmp_path: Path) -> None:
    """Both spoiler and multidata presence are reflected on Seed even when
    multidata decode fails (we still know the file is there)."""
    p = tmp_path / "AP_12345.zip"
    _write_seed_zip(p, "12345", multidata_blob=b"")  # empty blob → decode fails
    seed = scan_seed(p)
    assert seed.has_spoiler is True
    assert seed.has_archipelago_file is True
    assert seed.error  # decode failed → error recorded
    assert seed.slots == []
    assert seed.games == []


def test_scan_seed_missing_spoiler(tmp_path: Path) -> None:
    p = tmp_path / "AP_67890.zip"
    _write_seed_zip(p, "67890", multidata_blob=None, spoiler=False)
    seed = scan_seed(p)
    assert seed.has_spoiler is False
    assert seed.has_archipelago_file is False


def test_scan_seed_corrupt_zip(tmp_path: Path) -> None:
    p = tmp_path / "AP_99999.zip"
    p.write_bytes(b"not a zip")
    seed = scan_seed(p)
    assert seed.error is not None
    assert "corrupt zip" in seed.error
    # Even on error, file metadata is recorded so the row can display
    # something useful (filename, size, mtime).
    assert seed.size_bytes == len(b"not a zip")


def test_scan_directory_sorts_by_mtime_desc(tmp_path: Path) -> None:
    old = tmp_path / "AP_111.zip"
    new = tmp_path / "AP_222.zip"
    _write_seed_zip(old, "111")
    _write_seed_zip(new, "222")
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    seeds = scan_directory(tmp_path)
    assert [s.path.name for s in seeds] == ["AP_222.zip", "AP_111.zip"]


def test_scan_directory_filters_non_seed_files(tmp_path: Path) -> None:
    _write_seed_zip(tmp_path / "AP_42.zip", "42")
    (tmp_path / "not_a_seed.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # empty zip
    (tmp_path / "AP_42.archipelago").write_bytes(b"\x00")  # raw multidata file
    (tmp_path / "random.txt").write_text("hi")
    seeds = scan_directory(tmp_path)
    assert [s.path.name for s in seeds] == ["AP_42.zip"]


def test_scan_directory_missing_folder(tmp_path: Path) -> None:
    """Listing a nonexistent dir returns an empty list, not a crash."""
    seeds = scan_directory(tmp_path / "does-not-exist")
    assert seeds == []


def test_collapse_games_preserves_first_seen_order() -> None:
    slots = [
        (1, "A", "Minecraft"),
        (2, "B", "Jigsaw"),
        (3, "C", "Minecraft"),
    ]
    assert _collapse_games(slots) == [("Minecraft", 2), ("Jigsaw", 1)]


# --- Multidata integration tests (require AP source on path) ---


@pytest.mark.skipif(
    not os.environ.get("ARCHIPELAGO_SRC"),
    reason="ARCHIPELAGO_SRC unset — skipping multidata decode tests",
)
def test_scan_real_seeds_from_output_dir() -> None:
    """Sanity check against real seeds in the user's output folder, if present.

    Disabled by default; enable by setting both ARCHIPELAGO_SRC (so AP's
    Utils is importable) and AP_OUTPUT_DIR (so we know where to look).
    """
    pytest.importorskip("Utils")
    out = os.environ.get(
        "AP_OUTPUT_DIR",
        str(Path.home() / "Library" / "Application Support" / "Archipelago" / "output"),
    )
    out_path = Path(out)
    if not out_path.is_dir():
        pytest.skip(f"AP output dir not found: {out_path}")
    seeds = scan_directory(out_path)
    if not seeds:
        pytest.skip(f"No seeds in {out_path}")
    assert all(isinstance(s, Seed) for s in seeds)
    decoded = [s for s in seeds if s.has_archipelago_file and s.error is None]
    assert decoded, "no seed decoded its multidata successfully"
    for s in decoded:
        assert s.slots, f"{s.path.name}: empty slots despite has_archipelago_file"
        assert s.games, f"{s.path.name}: empty games despite slots"

"""Unit tests for :mod:`seed_browser.scanner`.

Tests that need AP's restricted unpickler are gated on
``ARCHIPELAGO_SRC`` being set (see ``conftest.py``); they're skipped
otherwise so the suite stays runnable without an AP checkout.
"""

from __future__ import annotations

import datetime
import os
import zipfile
from pathlib import Path

import pytest

from seed_browser.scanner import (
    Seed,
    _coerce_version,
    _collapse_games,
    _extract_slot_patches,
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


def _write_seed_with_zip_date(
    path: Path,
    seed_id: str,
    date_time: tuple[int, int, int, int, int, int],
) -> None:
    """Like ``_write_seed_zip`` but stamps the ``.archipelago`` entry's
    ``date_time`` explicitly so mtime-based assertions are deterministic
    (scanner reads the zip entry mtime, not the filesystem mtime)."""
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo(filename=f"AP_{seed_id}.archipelago")
        info.date_time = date_time
        zf.writestr(info, b"\x00\x00")


def test_scan_directory_sorts_by_mtime_desc(tmp_path: Path) -> None:
    old = tmp_path / "AP_111.zip"
    new = tmp_path / "AP_222.zip"
    _write_seed_with_zip_date(old, "111", (2020, 1, 1, 0, 0, 0))
    _write_seed_with_zip_date(new, "222", (2024, 6, 1, 12, 0, 0))
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


def test_scan_seed_prefers_zip_entry_mtime_over_filesystem(tmp_path: Path) -> None:
    """A seed's reported mtime should reflect when AP generated it, not
    when the zip happened to land on disk. The zip entry's ``date_time``
    is the authoritative source; the filesystem mtime is the fallback.
    """
    import zipfile as _zipfile  # local alias so we can construct a ZipInfo

    p = tmp_path / "AP_42.zip"
    info = _zipfile.ZipInfo(filename="AP_42.archipelago")
    info.date_time = (2024, 1, 15, 12, 30, 0)  # well before the filesystem mtime below
    with _zipfile.ZipFile(p, "w") as zf:
        zf.writestr(info, b"\x00\x00")  # decode will fail but mtime is still read

    # Far-future filesystem mtime that the scanner must ignore.
    os.utime(p, (3_000_000_000, 3_000_000_000))

    seed = scan_seed(p)
    expected = datetime.datetime(2024, 1, 15, 12, 30, 0).timestamp()
    assert seed.mtime == expected
    assert seed.mtime != 3_000_000_000.0


def test_scan_seed_detects_apsave_sibling(tmp_path: Path) -> None:
    """A sibling ``<id>.apsave`` is the signal that the seed has been
    hosted; its mtime is the last-hosted time."""
    p = tmp_path / "AP_50000.zip"
    _write_seed_zip(p, "50000")
    save = tmp_path / "AP_50000.apsave"
    save.write_bytes(b"fake-save-content")
    os.utime(save, (1_750_000_000, 1_750_000_000))
    seed = scan_seed(p)
    assert seed.has_save is True
    assert seed.last_hosted == 1_750_000_000.0


def test_scan_seed_without_apsave_reports_unhosted(tmp_path: Path) -> None:
    p = tmp_path / "AP_50001.zip"
    _write_seed_zip(p, "50001")
    seed = scan_seed(p)
    assert seed.has_save is False
    assert seed.last_hosted is None


def test_scan_seed_marks_hosted_even_when_save_decode_fails(tmp_path: Path) -> None:
    """A corrupt ``.apsave`` is still a 'this seed has been hosted'
    signal — the existence of the file tells us MultiServer ran. We
    just can't fill tier 3-4 (per-slot progress / completion)."""
    p = tmp_path / "AP_60000.zip"
    _write_seed_zip(p, "60000")
    save = tmp_path / "AP_60000.apsave"
    save.write_bytes(b"definitely not a zlib stream")
    seed = scan_seed(p)
    assert seed.has_save is True
    assert seed.last_hosted is not None
    assert seed.slot_checked == {}
    assert seed.slot_complete == {}


def test_scan_seed_falls_back_to_filesystem_mtime_when_no_archipelago(
    tmp_path: Path,
) -> None:
    """Without a ``.archipelago`` entry there's no zip-internal date to
    trust, so we keep ``path.stat().st_mtime``."""
    p = tmp_path / "AP_99.zip"
    _write_seed_zip(p, "99", multidata_blob=None, spoiler=False)
    os.utime(p, (1_700_000_000, 1_700_000_000))
    seed = scan_seed(p)
    assert seed.mtime == 1_700_000_000.0


def test_extract_slot_patches_picks_up_per_slot_suffixes() -> None:
    """Patch entries match ``AP_<seed_id>_P<slot>_<player>.<suffix>``;
    spoiler and multidata entries don't have the ``_P<digit>_`` and must
    be skipped."""
    names = [
        "AP_12345.archipelago",
        "AP_12345_Spoiler.txt",
        "AP_12345_P1_Jox.apmc",
        "AP_12345_P3_Bob.aplttp",
    ]
    assert _extract_slot_patches(names) == {1: ".apmc", 3: ".aplttp"}


def test_extract_slot_patches_handles_dotted_player_names() -> None:
    """Player names may contain dots — the regex uses a non-greedy
    final-segment match for the suffix."""
    assert _extract_slot_patches(["AP_99_P2_A.B.C.apmc"]) == {2: ".apmc"}


def test_extract_slot_patches_skips_non_seed_files() -> None:
    """Names without the ``AP_<digits>_P<digit>`` prefix are not patches."""
    assert _extract_slot_patches(["random.txt", "AP_99.archipelago"]) == {}


def test_scan_seed_extracts_slot_patches_even_when_multidata_fails(tmp_path: Path) -> None:
    """Patches come from the namelist, not the multidata blob. Decode
    failure must not erase the patch mapping."""
    p = tmp_path / "AP_30000.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("AP_30000.archipelago", b"")  # decode will fail
        zf.writestr("AP_30000_P1_Jox.apmc", b"patch")
    seed = scan_seed(p)
    assert seed.error  # multidata decode failed
    assert seed.slot_patches == {1: ".apmc"}  # but patches still surfaced


def test_coerce_version_round_trips_a_three_tuple() -> None:
    assert _coerce_version((0, 6, 7)) == (0, 6, 7)


def test_coerce_version_returns_none_for_garbage() -> None:
    assert _coerce_version(None) is None
    assert _coerce_version("not-a-tuple") is None
    assert _coerce_version((1, 2)) is None  # wrong shape


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

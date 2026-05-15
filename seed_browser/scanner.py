"""Seed-zip introspection.

For each ``AP_<id>.zip`` we read:

- the namelist (cheap) — spoiler presence, multidata presence
- the ``.archipelago`` multidata blob (authoritative) — ``slot_info``,
  decoded via AP's :func:`Utils.restricted_loads`

Multidata is authoritative because patch filenames only cover ROM-based
slots; server-only slots (e.g. ChecksFinder, Jigsaw) leave no entry in
the namelist.
"""

from __future__ import annotations

import datetime
import logging
import re
import zipfile
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_SEED_FILE_RE = re.compile(r"^AP_\d+\.zip$")
_MAX_MULTIDATA_FORMAT = 3


@dataclass(slots=True)
class Seed:
    path: Path
    mtime: float
    size_bytes: int
    games: list[tuple[str, int]] = field(default_factory=list)
    """``[(game_name, count), ...]`` preserving first-seen order."""
    slots: list[tuple[int, str, str]] = field(default_factory=list)
    """``[(slot_num, slot_name, game_name), ...]`` sorted by slot number."""
    has_spoiler: bool = False
    has_archipelago_file: bool = False
    error: str | None = None


def scan_seed(path: Path) -> Seed:
    """Open *path* and return a populated :class:`Seed`.

    On any failure the ``error`` field is set and the rest is left at
    defaults — callers must not assume slots/games are populated.
    """
    try:
        stat = path.stat()
    except OSError as e:
        return Seed(path=path, mtime=0.0, size_bytes=0, error=str(e))

    seed = Seed(path=path, mtime=stat.st_mtime, size_bytes=stat.st_size)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            seed.has_spoiler = any(n.endswith("_Spoiler.txt") for n in names)
            archipelago_name = next((n for n in names if n.endswith(".archipelago")), None)
            seed.has_archipelago_file = archipelago_name is not None
            if archipelago_name is not None:
                # The zip entry's date_time is set by AP at generation
                # (Main.py:387 calls zf.write() which copies the temp
                # file's mtime). Prefer it over the filesystem mtime,
                # which gets clobbered when seeds are copied/synced.
                seed.mtime = _zip_entry_mtime(zf.getinfo(archipelago_name))
                slot_info = _decode_slot_info(zf.read(archipelago_name))
                seed.slots = [
                    (slot_num, slot_name, game)
                    for slot_num, (slot_name, game) in sorted(slot_info.items())
                ]
                seed.games = _collapse_games(seed.slots)
    except zipfile.BadZipFile as e:
        seed.error = f"corrupt zip: {e}"
    except (OSError, ValueError, KeyError) as e:
        seed.error = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001  # never crash the launcher
        logger.exception("unexpected scan error for %s", path)
        seed.error = f"{type(e).__name__}: {e}"
    return seed


def scan_directory(folder: Path) -> list[Seed]:
    """Return seeds in *folder* sorted by mtime descending.

    Non-``AP_<id>.zip`` files are skipped. Unreadable folders yield an
    empty list (logged at warning).
    """
    try:
        entries = list(folder.iterdir())
    except OSError as e:
        logger.warning("cannot list %s: %s", folder, e)
        return []
    seeds = [scan_seed(p) for p in entries if p.is_file() and _SEED_FILE_RE.match(p.name)]
    seeds.sort(key=lambda s: s.mtime, reverse=True)
    return seeds


def _decode_slot_info(blob: bytes) -> dict[int, tuple[str, str]]:
    """Return ``{slot_num: (slot_name, game_name)}`` from a multidata blob.

    Format: byte 0 = format version (≤3), bytes 1: = zlib-compressed
    pickle. We delegate to :func:`Utils.restricted_loads` so unpickle is
    sandboxed to AP's known whitelist.
    """
    if not blob:
        raise ValueError("empty multidata")
    if blob[0] > _MAX_MULTIDATA_FORMAT:
        raise ValueError(f"incompatible multidata format version: {blob[0]}")
    from Utils import restricted_loads

    payload = restricted_loads(zlib.decompress(blob[1:]))
    slot_info = payload.get("slot_info", {})
    return {int(slot): (ns.name, ns.game) for slot, ns in slot_info.items()}


def _zip_entry_mtime(info: zipfile.ZipInfo) -> float:
    """Convert a zip entry's ``date_time`` tuple to a POSIX timestamp.

    Zip dates have 2-second resolution and no timezone — they're written
    in the generating machine's local time. We interpret them in the
    reader's local time, which is correct for the common single-user
    case and harmless for sort ordering even across timezones.
    """
    return datetime.datetime(*info.date_time).timestamp()


def _collapse_games(slots: list[tuple[int, str, str]]) -> list[tuple[str, int]]:
    counts: OrderedDict[str, int] = OrderedDict()
    for _, _, game in slots:
        counts[game] = counts.get(game, 0) + 1
    return list(counts.items())

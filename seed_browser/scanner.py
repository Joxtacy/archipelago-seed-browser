"""Seed-zip introspection.

For each ``AP_<id>.zip`` we read:

- the namelist (cheap) — spoiler presence, multidata presence, per-slot
  patch files (e.g. ``AP_<id>_P3_Jox.apmc`` → slot 3 has an ``.apmc``)
- the ``.archipelago`` multidata blob (authoritative) — ``slot_info``,
  generator version, minimum server version, decoded via AP's
  :func:`Utils.restricted_loads`

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
_PATCH_FILE_RE = re.compile(r"^AP_\d+_P(\d+)_.+\.([^.]+)$")
_MAX_MULTIDATA_FORMAT = 3

# NetworkSlot.type is a SlotType IntEnum from AP's NetUtils:
# spectator=0, player=1, group=2. Mapping the int value rather than
# importing the enum keeps us decoupled from AP's import path.
_SLOT_TYPE_NAMES: dict[int, str] = {0: "spectator", 1: "player", 2: "group"}


@dataclass(slots=True)
class Seed:
    path: Path
    mtime: float
    size_bytes: int
    games: list[tuple[str, int]] = field(default_factory=list)
    """``[(game_name, count), ...]`` preserving first-seen order."""
    slots: list[tuple[int, str, str]] = field(default_factory=list)
    """``[(slot_num, slot_name, game_name), ...]`` sorted by slot number."""
    slot_types: dict[int, str] = field(default_factory=dict)
    """``{slot_num: 'player' | 'group' | 'spectator'}`` keyed by slot number."""
    slot_patches: dict[int, str] = field(default_factory=dict)
    """``{slot_num: '.apmc'}`` — patch suffix per slot inferred from the
    zip namelist. Absent entries mean the slot is server-only or its
    patch file is missing from the zip."""
    generator_version: tuple[int, int, int] | None = None
    """AP version that generated this seed (``payload['version']``)."""
    min_server_version: tuple[int, int, int] | None = None
    """Minimum AP version required to host this seed
    (``payload['minimum_versions']['server']``)."""
    has_spoiler: bool = False
    has_archipelago_file: bool = False
    has_save: bool = False
    """Set when a sibling ``<seed_id>.apsave`` exists, i.e. the seed has
    been hosted at least once."""
    last_hosted: float | None = None
    """POSIX timestamp of the sibling ``.apsave``'s mtime (= the last
    time the server shut down and flushed state). ``None`` when the
    seed has never been hosted."""
    error: str | None = None


@dataclass(slots=True)
class _MultidataInfo:
    """Internal: what we extract from a successfully decoded multidata blob."""
    slot_info: dict[int, tuple[str, str, int]]
    """``{slot_num: (slot_name, game, slot_type_int)}``"""
    version: tuple[int, int, int] | None
    min_server_version: tuple[int, int, int] | None


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
            seed.slot_patches = _extract_slot_patches(names)
            archipelago_name = next((n for n in names if n.endswith(".archipelago")), None)
            seed.has_archipelago_file = archipelago_name is not None
            if archipelago_name is not None:
                # The zip entry's date_time is set by AP at generation
                # (Main.py:387 calls zf.write() which copies the temp
                # file's mtime). Prefer it over the filesystem mtime,
                # which gets clobbered when seeds are copied/synced.
                seed.mtime = _zip_entry_mtime(zf.getinfo(archipelago_name))
                info = _decode_multidata(zf.read(archipelago_name))
                seed.slots = [
                    (slot_num, slot_name, game)
                    for slot_num, (slot_name, game, _type) in sorted(info.slot_info.items())
                ]
                seed.slot_types = {
                    slot_num: _SLOT_TYPE_NAMES.get(t, "unknown")
                    for slot_num, (_n, _g, t) in info.slot_info.items()
                }
                seed.games = _collapse_games(seed.slots)
                seed.generator_version = info.version
                seed.min_server_version = info.min_server_version
    except zipfile.BadZipFile as e:
        seed.error = f"corrupt zip: {e}"
    except (OSError, ValueError, KeyError) as e:
        seed.error = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001  # never crash the launcher
        logger.exception("unexpected scan error for %s", path)
        seed.error = f"{type(e).__name__}: {e}"

    _populate_save_info(seed)
    return seed


def _populate_save_info(seed: Seed) -> None:
    """Detect a sibling ``<seed_id>.apsave`` written by MultiServer at
    ``MultiServer.py:613`` and populate ``has_save`` / ``last_hosted``.

    Stat failures (permissions, weird FS) are non-fatal — we just leave
    the fields at their defaults.
    """
    save_path = seed.path.with_suffix(".apsave")
    try:
        save_stat = save_path.stat()
    except FileNotFoundError:
        return
    except OSError as e:
        logger.warning("cannot stat %s: %s", save_path, e)
        return
    seed.has_save = True
    seed.last_hosted = save_stat.st_mtime


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


def _extract_slot_patches(names: list[str]) -> dict[int, str]:
    """Pull ``{slot_num: '.suffix'}`` out of patch filenames in the
    namelist. Filenames follow ``AP_<seed_id>_P<slot>_<player>.<suffix>``
    (Main.py:382, NOTES §3.5). Non-patch entries (spoiler, multidata)
    don't have ``_P<digit>`` and are skipped by the regex.
    """
    out: dict[int, str] = {}
    for name in names:
        m = _PATCH_FILE_RE.match(name)
        if m:
            out[int(m.group(1))] = f".{m.group(2)}"
    return out


def _decode_multidata(blob: bytes) -> _MultidataInfo:
    """Decode the ``.archipelago`` multidata blob.

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
    slot_info = {
        int(slot): (ns.name, ns.game, int(ns.type))
        for slot, ns in payload.get("slot_info", {}).items()
    }
    version = _coerce_version(payload.get("version"))
    minimum_versions = payload.get("minimum_versions") or {}
    return _MultidataInfo(
        slot_info=slot_info,
        version=version,
        min_server_version=_coerce_version(minimum_versions.get("server")),
    )


def _coerce_version(value: object) -> tuple[int, int, int] | None:
    """Best-effort cast of a ``(major, minor, build)``-ish triple to a
    plain int tuple. Returns ``None`` for anything that doesn't unpack
    cleanly — versions are display-only, not safety-critical."""
    if value is None:
        return None
    try:
        major, minor, build = value
        return (int(major), int(minor), int(build))
    except (TypeError, ValueError):
        return None


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

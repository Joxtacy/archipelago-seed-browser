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

# NetUtils.ClientStatus.CLIENT_GOAL — the slot has reached its goal.
# Hardcoded to keep us decoupled from AP's import path.
_CLIENT_STATUS_GOAL = 30


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
    slot_totals: dict[int, int] = field(default_factory=dict)
    """``{slot_num: total_locations}`` — total checks per slot from the
    multidata's ``locations`` map."""
    slot_checked: dict[int, int] = field(default_factory=dict)
    """``{slot_num: checked_count}`` — locations the player has
    checked, decoded from the sibling ``.apsave``. Empty when the seed
    hasn't been hosted, or when save decode fails."""
    slot_complete: dict[int, bool] = field(default_factory=dict)
    """``{slot_num: True}`` for slots that reported
    ``ClientStatus.CLIENT_GOAL`` (30) in the save. Absent / False means
    the slot hasn't reached its goal (or no save exists)."""
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
    _file_mtime: float = 0.0
    """Filesystem mtime of the seed zip at scan time. Used by
    :func:`scan_directory` to validate cache entries — distinct from
    :attr:`mtime`, which prefers the zip-internal date_time."""


@dataclass(slots=True)
class _MultidataInfo:
    """Internal: what we extract from a successfully decoded multidata blob."""

    slot_info: dict[int, tuple[str, str, int]]
    """``{slot_num: (slot_name, game, slot_type_int)}``"""
    version: tuple[int, int, int] | None
    min_server_version: tuple[int, int, int] | None
    slot_totals: dict[int, int]
    """``{slot_num: total_locations}``"""


def scan_seed(path: Path) -> Seed:
    """Open *path* and return a populated :class:`Seed`.

    On any failure the ``error`` field is set and the rest is left at
    defaults — callers must not assume slots/games are populated.
    """
    try:
        stat = path.stat()
    except OSError as e:
        return Seed(path=path, mtime=0.0, size_bytes=0, error=str(e))

    seed = Seed(
        path=path,
        mtime=stat.st_mtime,
        size_bytes=stat.st_size,
        _file_mtime=stat.st_mtime,
    )
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
                seed.slot_totals = info.slot_totals
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
    ``MultiServer.py:613`` and populate ``has_save`` / ``last_hosted``,
    plus tiers 3-4 (per-slot progress + completion) when the save can
    be decoded.

    All failures are non-fatal: ``has_save`` is set as soon as the file
    exists, the rest stay at their defaults if decode fails. The save
    schema is internal AP state — log on failure and move on.
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

    try:
        save_data = _decode_save(save_path)
    except (OSError, zlib.error, ValueError, KeyError, AttributeError):
        logger.warning("cannot decode save %s", save_path, exc_info=True)
        return
    except Exception:  # noqa: BLE001  # never crash the launcher
        logger.exception("unexpected error decoding save %s", save_path)
        return

    # Multi-team support isn't worth the UI complexity at this tier;
    # take team 0 (the common case for solo and single-machine play).
    location_checks = save_data.get("location_checks", {}) or {}
    for key, checks in location_checks.items():
        team, slot = key
        if team == 0:
            seed.slot_checked[int(slot)] = len(checks)
    client_game_state = save_data.get("client_game_state", {}) or {}
    for key, status in client_game_state.items():
        team, slot = key
        if team == 0:
            seed.slot_complete[int(slot)] = int(status) == _CLIENT_STATUS_GOAL


def _decode_save(path: Path) -> dict:
    """Decode ``<seed_id>.apsave`` — zlib-compressed pickle written by
    ``MultiServer._save``. Delegates to AP's ``restricted_loads`` so
    the unpickler stays sandboxed to AP's known class whitelist.
    """
    from Utils import restricted_loads

    with open(path, "rb") as f:
        raw = f.read()
    payload = restricted_loads(zlib.decompress(raw))
    if not isinstance(payload, dict):
        raise ValueError(f"save payload is not a dict (got {type(payload).__name__})")
    return payload


def scan_directory(
    folder: Path,
    cache: dict[Path, Seed] | None = None,
    *,
    workers: int = 1,
) -> list[Seed]:
    """Return seeds in *folder* sorted by mtime descending.

    Non-``AP_<id>.zip`` files are skipped. Unreadable folders yield an
    empty list (logged at warning).

    When *cache* is supplied (typically the previous scan's result keyed
    by ``Seed.path``), entries whose zip mtime and ``.apsave`` mtime
    both match the cached values are reused verbatim — the expensive
    multidata + save decode is skipped. Re-decoding only happens when
    something actually changed on disk.

    When *workers* > 1 the cache-miss scans run on a thread pool. The
    bulk of per-seed cost is zip I/O + zlib decompression, both of
    which release the GIL, so threading scales well even though the
    pickle decode itself doesn't.
    """
    try:
        entries = list(folder.iterdir())
    except OSError as e:
        logger.warning("cannot list %s: %s", folder, e)
        return []

    candidates = [p for p in entries if p.is_file() and _SEED_FILE_RE.match(p.name)]

    if workers <= 1 or len(candidates) <= 1:
        seeds = [_scan_with_cache(p, cache) for p in candidates]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as ex:
            seeds = list(ex.map(lambda p: _scan_with_cache(p, cache), candidates))

    seeds.sort(key=lambda s: s.mtime, reverse=True)
    return seeds


def _scan_with_cache(path: Path, cache: dict[Path, Seed] | None) -> Seed:
    """Return a cached :class:`Seed` for *path* when the on-disk mtimes
    match, otherwise delegate to :func:`scan_seed`.

    The save's mtime is read separately from the zip's because the two
    files change independently — the zip is written once at generation,
    the ``.apsave`` is rewritten every time MultiServer flushes.
    """
    if cache is None:
        return scan_seed(path)
    cached = cache.get(path)
    if cached is None:
        return scan_seed(path)
    try:
        file_mtime = path.stat().st_mtime
    except OSError:
        return scan_seed(path)
    if cached._file_mtime != file_mtime:
        return scan_seed(path)
    save_path = path.with_suffix(".apsave")
    try:
        save_mtime: float | None = save_path.stat().st_mtime
    except FileNotFoundError:
        save_mtime = None
    except OSError:
        return scan_seed(path)
    if cached.last_hosted != save_mtime:
        return scan_seed(path)
    return cached


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
    # locations: dict[slot_num, dict[location_id, ...]] — verified
    # against a real seed. Slot-keyed (not team-keyed) at the multidata
    # level; teams come in via the save file's location_checks.
    locations = payload.get("locations") or {}
    slot_totals = {int(slot): len(inner) for slot, inner in locations.items()}
    return _MultidataInfo(
        slot_info=slot_info,
        version=version,
        min_server_version=_coerce_version(minimum_versions.get("server")),
        slot_totals=slot_totals,
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

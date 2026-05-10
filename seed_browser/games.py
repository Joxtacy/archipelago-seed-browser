"""Patch-suffix → game-name resolution.

Reads :data:`worlds.Files.AutoPatchRegister.file_endings` — the registry
populated at AP import time mapping `patch_file_ending` to the patch
handler class, whose ``game`` attribute names the world. v1 doesn't
strictly need this map (multidata's ``slot_info`` is authoritative for
displaying seed contents), but it's a thin shim other code can consume
later (e.g. per-slot patch extraction).
"""

from __future__ import annotations

import threading

_cache: dict[str, str] | None = None
_lock = threading.Lock()


def build_extension_map() -> dict[str, str]:
    """Return ``{".aplttp": "A Link to the Past", ...}``.

    Cached after the first call; use :func:`refresh` to invalidate.
    """
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _build()
    return _cache


def refresh() -> None:
    """Drop the cache so the next call re-walks the registry."""
    global _cache
    with _lock:
        _cache = None


def _build() -> dict[str, str]:
    from worlds.Files import AutoPatchRegister

    return {
        ending: handler.game
        for ending, handler in AutoPatchRegister.file_endings.items()
        if getattr(handler, "game", None)
    }

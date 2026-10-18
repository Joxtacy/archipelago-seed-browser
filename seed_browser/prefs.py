"""Persisted view preferences (sort + state filter) across launches.

Stored as a small JSON file in AP's user directory rather than via
``Utils.persistent_store``: that helper caches the whole YAML per
process and rewrites it wholesale, so the launcher (running alongside
us) and the Seed Browser would clobber each other's keys — e.g. a sort
click here could silently revert launcher favourites edited meanwhile.

Loading never raises: missing, unreadable, or invalid values fall back
to defaults field by field.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PREFS_FILENAME = "seed_browser.json"

_SORT_KEYS = ("date", "size", "slots", "hosted", "game")
_STATE_FILTERS = ("all", "untouched", "in_progress", "complete")


@dataclass(slots=True)
class ViewPrefs:
    sort_key: str = "date"
    sort_desc: bool = True
    state_filter: str = "all"


def default_prefs_path() -> Path | None:
    """``<AP user dir>/seed_browser.json``, or ``None`` without AP."""
    try:
        from Utils import user_path
    except ImportError:
        return None
    return Path(user_path(PREFS_FILENAME))


def load_prefs(path: Path | None) -> ViewPrefs:
    prefs = ViewPrefs()
    if path is None:
        return prefs
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return prefs
    except (OSError, ValueError) as e:
        logger.warning("ignoring unreadable prefs %s: %s", path, e)
        return prefs
    if not isinstance(raw, dict):
        return prefs
    if raw.get("sort_key") in _SORT_KEYS:
        prefs.sort_key = raw["sort_key"]
    if isinstance(raw.get("sort_desc"), bool):
        prefs.sort_desc = raw["sort_desc"]
    if raw.get("state_filter") in _STATE_FILTERS:
        prefs.state_filter = raw["state_filter"]
    return prefs


def save_prefs(path: Path | None, prefs: ViewPrefs) -> None:
    """Write *prefs* atomically (temp file + ``os.replace``) so a crash
    mid-write can't leave a truncated file. Failures are logged, not
    raised — losing a sort preference must never break the UI."""
    if path is None:
        return
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(asdict(prefs), indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("could not save prefs to %s: %s", path, e)

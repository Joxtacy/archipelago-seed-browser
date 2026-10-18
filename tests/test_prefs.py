"""Tests for :mod:`seed_browser.prefs` — persisted sort/filter choices."""

from __future__ import annotations

import json
from pathlib import Path

from seed_browser import browser
from seed_browser.prefs import (
    _SORT_KEYS,
    _STATE_FILTERS,
    ViewPrefs,
    load_prefs,
    save_prefs,
)


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "seed_browser.json"
    prefs = ViewPrefs(sort_key="game", sort_desc=False, state_filter="complete")
    save_prefs(path, prefs)
    assert load_prefs(path) == prefs
    assert not (tmp_path / "seed_browser.json.tmp").exists()


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_prefs(tmp_path / "nope.json") == ViewPrefs()


def test_no_path_gives_defaults_and_save_is_noop() -> None:
    assert load_prefs(None) == ViewPrefs()
    save_prefs(None, ViewPrefs())


def test_corrupt_file_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "seed_browser.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_prefs(path) == ViewPrefs()


def test_invalid_fields_fall_back_individually(tmp_path: Path) -> None:
    path = tmp_path / "seed_browser.json"
    path.write_text(
        json.dumps({"sort_key": "bogus", "sort_desc": False, "state_filter": 7}),
        encoding="utf-8",
    )
    assert load_prefs(path) == ViewPrefs(sort_key="date", sort_desc=False, state_filter="all")


def test_save_failure_does_not_raise(tmp_path: Path) -> None:
    save_prefs(tmp_path / "missing_dir" / "seed_browser.json", ViewPrefs())


def test_allowed_values_match_browser_options() -> None:
    assert set(_SORT_KEYS) == set(browser._SORT_LABELS)
    assert set(_STATE_FILTERS) == set(browser._STATE_LABELS)

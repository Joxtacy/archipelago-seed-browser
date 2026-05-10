"""Unit tests for :mod:`seed_browser.games`.

Gated on AP being importable since ``build_extension_map`` walks
:data:`worlds.Files.AutoPatchRegister.file_endings`.
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    not os.environ.get("ARCHIPELAGO_SRC"),
    reason="ARCHIPELAGO_SRC unset",
)
def test_build_extension_map_returns_known_suffixes() -> None:
    pytest.importorskip("worlds.Files")
    from seed_browser import games

    games.refresh()
    m = games.build_extension_map()
    # Every value must be a non-empty string and every key a leading-dot suffix.
    assert all(isinstance(v, str) and v for v in m.values())
    assert all(k.startswith(".") and len(k) > 1 for k in m)
    # Built-in AP worlds we expect to ship a patch handler:
    assert m.get(".aplttp") == "A Link to the Past"


@pytest.mark.skipif(
    not os.environ.get("ARCHIPELAGO_SRC"),
    reason="ARCHIPELAGO_SRC unset",
)
def test_build_extension_map_is_cached() -> None:
    pytest.importorskip("worlds.Files")
    from seed_browser import games

    games.refresh()
    first = games.build_extension_map()
    second = games.build_extension_map()
    assert first is second  # same object reference → cache hit
